"""Private, read-only NOAA Storm Events catalog and location-review-gated context.

An event in this table is a regional NWS-reported occurrence, NOT an insured
site incident, property loss, hazard footprint, flood-zone designation or claim.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path

from .intelligence import is_reviewed_site_coordinate
from .match import haversine_km

SCHEMA = """
CREATE TABLE IF NOT EXISTS noaa_storm_events (
  event_id TEXT PRIMARY KEY,
  episode_id TEXT,
  source_year INTEGER NOT NULL,
  begin_date TEXT NOT NULL,
  state TEXT NOT NULL,
  county_zone TEXT,
  event_type TEXT NOT NULL,
  begin_latitude REAL,
  begin_longitude REAL,
  end_latitude REAL,
  end_longitude REAL,
  damage_property_reported TEXT,
  injuries_direct INTEGER,
  deaths_direct INTEGER,
  source_url TEXT NOT NULL,
  coordinate_semantics TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_noaa_state_date ON noaa_storm_events(state,begin_date DESC);
CREATE INDEX IF NOT EXISTS idx_noaa_year_type ON noaa_storm_events(source_year,event_type);
CREATE INDEX IF NOT EXISTS idx_noaa_lat_lon ON noaa_storm_events(begin_latitude,begin_longitude);
CREATE TABLE IF NOT EXISTS noaa_storm_imports (
  source_year INTEGER PRIMARY KEY,
  records INTEGER NOT NULL,
  point_coordinates INTEGER NOT NULL,
  source_url TEXT NOT NULL,
  source_file TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  normalized_sha256 TEXT NOT NULL,
  retrieved_vintage TEXT NOT NULL,
  imported_at TEXT NOT NULL
);
"""

FIELDS = (
    "event_id", "episode_id", "year", "begin_date", "state", "county_zone",
    "event_type", "begin_latitude", "begin_longitude", "end_latitude",
    "end_longitude", "damage_property_reported", "injuries_direct",
    "deaths_direct", "source_url", "coordinate_semantics",
)


def initialize_storm_events(conn):
    conn.executescript(SCHEMA)


def _hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scan(path, expected):
    years = {part["year"]: 0 for part in expected["partitions"]}
    geo = {y: 0 for y in years}
    seen = set()
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("NOAA normalized data schema mismatch")
        for row in reader:
            y = int(row["year"])
            if y not in years or int(row["begin_date"][:4]) != y:
                raise ValueError("NOAA row outside manifest years")
            if row["event_id"] in seen:
                raise ValueError("Repeated NOAA event identifier across years")
            seen.add(row["event_id"])
            years[y] += 1
            if row["begin_latitude"] and row["begin_longitude"]:
                geo[y] += 1
    for part in expected["partitions"]:
        if years[part["year"]] != part["event_records"] or geo[part["year"]] != part["point_coordinates_reported"]:
            raise ValueError("NOAA partition counts do not match source manifest")
    if sum(years.values()) != expected["total_events"]:
        raise ValueError("NOAA total source rows do not match source manifest")
    return years


def _float(raw, lo, hi):
    if not raw:
        return None
    n = float(raw)
    if not math.isfinite(n) or not lo <= n <= hi:
        raise ValueError("Invalid NOAA normalized coordinates")
    return n


def _int(raw):
    return int(raw) if raw not in (None, "") else None


def _rows(path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("NOAA normalized schema changed mid-import")
        for r in reader:
            yield (
                r["event_id"], r["episode_id"], int(r["year"]), r["begin_date"],
                r["state"], r["county_zone"], r["event_type"],
                _float(r["begin_latitude"], -90, 90),
                _float(r["begin_longitude"], -180, 180),
                _float(r["end_latitude"], -90, 90),
                _float(r["end_longitude"], -180, 180),
                r["damage_property_reported"], _int(r["injuries_direct"]),
                _int(r["deaths_direct"]), r["source_url"], r["coordinate_semantics"],
            )


def import_noaa_storm_events(conn, normalized_path, manifest_path):
    """Atomic replacement of *complete* year partitions only.

    A failed hash, schema, row count, or duplicate check does not replace a
    previous valid year. This is an explicit private import, not a Pages job.
    """
    normalized_path = Path(normalized_path)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "1.0" or manifest.get("publisher") != "NOAA NCEI Storm Events Details":
        raise ValueError("Unexpected NOAA data manifest")
    if manifest.get("complete_requested_years") is not True:
        raise ValueError("Partial NOAA source snapshots cannot overwrite complete years")
    parts = manifest.get("partitions")
    if not parts or len(parts) != len({p.get("year") for p in parts}):
        raise ValueError("Duplicate or missing NOAA yearly source partitions")
    years = {p["year"] for p in parts}
    if sorted(years) != sorted(manifest.get("requested_years", [])):
        raise ValueError("NOAA manifest year selection mismatch")
    digest = _hash(normalized_path)
    if digest != manifest.get("normalized_sha256"):
        raise ValueError("NOAA normalized archive checksum mismatch")
    _scan(normalized_path, manifest)
    initialize_storm_events(conn)
    imported_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    count = 0
    try:
        with conn:
            conn.executemany("DELETE FROM noaa_storm_events WHERE source_year=?", ((y,) for y in years))
            conn.executemany("""INSERT INTO noaa_storm_events VALUES
                  (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", _rows(normalized_path))
            for part in parts:
                conn.execute("""INSERT INTO noaa_storm_imports
                  (source_year,records,point_coordinates,source_url,source_file,
                   source_sha256,normalized_sha256,retrieved_vintage,imported_at)
                  VALUES(?,?,?,?,?,?,?,?,?)
                  ON CONFLICT(source_year) DO UPDATE SET
                    records=excluded.records,point_coordinates=excluded.point_coordinates,
                    source_url=excluded.source_url,source_file=excluded.source_file,
                    source_sha256=excluded.source_sha256,normalized_sha256=excluded.normalized_sha256,
                    retrieved_vintage=excluded.retrieved_vintage,imported_at=excluded.imported_at""",
                    (part["year"], part["event_records"], part["point_coordinates_reported"],
                     part["source_url"], part["source_file"], part["original_archive_sha256"],
                     digest, manifest["generated_at"], imported_at))
            count = conn.execute("SELECT COUNT(*) FROM noaa_storm_events WHERE source_year IN (" +
                                 ",".join("?" for _ in years) + ")", tuple(sorted(years))).fetchone()[0]
            if count != manifest["total_events"]:
                raise ValueError("NOAA database rows do not match validated source")
    except Exception:
        conn.rollback()
        raise
    return {
        "state": "imported_private_backend", "rows_imported_for_requested_years": count,
        "source_years": sorted(years), "imported_at": imported_at,
        "coordinate_records": sum(p["point_coordinates_reported"] for p in parts),
        "notice": "Regional NOAA source reports; no site-specific attribution or insured loss is asserted",
    }


def status(conn):
    initialize_storm_events(conn)
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM noaa_storm_imports ORDER BY source_year DESC")]
    return {
        "source": "NOAA Storm Events Details",
        "state": "imported_private_backend" if rows else "not_imported",
        "source_years": [x["source_year"] for x in rows],
        "records": sum(x["records"] for x in rows),
        "coordinate_records": sum(x["point_coordinates"] for x in rows),
        "partitions": rows,
        "caveat": "NOAA event records and approximate points are not independently verified property losses",
    }


def search(conn, *, year=None, state="", event_type="", limit=50, offset=0):
    if not 1 <= limit <= 100 or offset < 0:
        raise ValueError("Invalid NOAA pagination")
    where = []
    args = []
    if year:
        if not 1950 <= int(year) <= 2100:
            raise ValueError("Invalid NOAA source year")
        where.append("source_year=?")
        args.append(int(year))
    if state:
        where.append("state=?")
        args.append(state.upper()[:90])
    if event_type:
        where.append("event_type=?")
        args.append(event_type[:100])
    clause = " WHERE " + " AND ".join(where) if where else ""
    total = conn.execute("SELECT COUNT(*) FROM noaa_storm_events" + clause, args).fetchone()[0]
    records = [dict(r) for r in conn.execute(
        "SELECT * FROM noaa_storm_events" + clause +
        " ORDER BY begin_date DESC,event_id LIMIT ? OFFSET ?", args+[limit, offset])]
    return {"items": records, "total": total, "limit": limit, "offset": offset,
            "source_scope": "Regional event records, not facility-associated verified damage"}


def nearby_reviewed_facility(conn, facility_id, *, radius_km=50, limit=50, year=None,
                             events_conn=None):
    """Proximity candidates are only returned for an approved CURRENT site point."""
    if not 1 <= radius_km <= 100 or not 1 <= limit <= 100:
        raise ValueError("Radius or limit outside accepted range")
    facility = conn.execute(
        "SELECT id,latitude,longitude FROM facilities WHERE id=?", (facility_id,)).fetchone()
    if facility is None:
        raise ValueError("Unknown research facility")
    review = conn.execute("SELECT * FROM location_reviews WHERE facility_id=?", (facility_id,)).fetchone()
    if not is_reviewed_site_coordinate(facility, review):
        return {
            "facility_id": facility_id, "status": "unassessed_location",
            "total_nearby": None, "items": [],
            "caveat": "Requires independently reviewed current property coordinates",
        }
    if year and not 1950 <= int(year) <= 2100:
        raise ValueError("Invalid NOAA year")
    lat, lon = float(facility["latitude"]), float(facility["longitude"])
    delta_lat = radius_km / 110.0 + 0.02
    delta_lon = min(180.0, radius_km/(111*max(0.000001, math.cos(math.radians(
        min(89.9999, abs(lat) + delta_lat))))) + 0.02)
    where = ["begin_latitude BETWEEN ? AND ?"]
    args = [max(-90.0, lat-delta_lat), min(90.0, lat+delta_lat)]
    if delta_lon < 180:
        lo, hi = lon-delta_lon, lon+delta_lon
        if lo < -180:
            where.append("(begin_longitude >= ? OR begin_longitude <= ?)")
            args.extend([lo+360, hi])
        elif hi > 180:
            where.append("(begin_longitude >= ? OR begin_longitude <= ?)")
            args.extend([lo, hi-360])
        else:
            where.append("begin_longitude BETWEEN ? AND ?")
            args.extend([lo, hi])
    if year:
        where.append("source_year=?")
        args.append(int(year))
    clause = " AND ".join(where)
    # Prevent unbounded scans: disclose truncation rather than pretending coverage.
    scanned = 0
    matched = []
    for r in (events_conn or conn).execute(
        "SELECT * FROM noaa_storm_events WHERE " + clause +
        " ORDER BY begin_date DESC,event_id LIMIT 30001", args):
        scanned += 1
        if scanned > 30000:
            break
        distance = haversine_km(lat, lon, r["begin_latitude"], r["begin_longitude"])
        if distance <= radius_km:
            item = dict(r)
            item["distance_km"] = round(distance, 2)
            matched.append(item)
    matched.sort(key=lambda x: (x["begin_date"], x["event_id"]), reverse=True)
    truncated = scanned > 30000
    return {
        "facility_id": facility_id,
        "status": "partial_scan_limit" if truncated else "proximity_candidates_only",
        "total_nearby": None if truncated else len(matched),
        "items": matched[:limit],
        "display_truncated": len(matched) > limit or truncated,
        "radius_km": radius_km, "verified_point": {"lat": lat, "lon": lon},
        "caveat": ("NOAA source positions can be missing/coarse and do not define event "
                   "footprints. Nearby means contextual candidates only: no facility damage, "
                   "insured losses, policy payouts or low-risk assertion."),
    }
