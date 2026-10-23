"""NOAA IncidentNews selected spill-response records, segregated from insured property.

IncidentNews records are SELECTED NOAA OR&R response-support incidents.
They are not a USCG NRC release census, attributed building damages, actual
released gallons, private loss runs or insurance claims.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .intelligence import is_reviewed_site_coordinate
from .match import haversine_km

TABLES = """
CREATE TABLE IF NOT EXISTS incidentnews_incidents (
  incident_id TEXT PRIMARY KEY,
  notification_date TEXT,
  name TEXT NOT NULL,
  location TEXT,
  latitude REAL,
  longitude REAL,
  threat TEXT NOT NULL,
  tags TEXT,
  commodity TEXT,
  potential_release_gallons_max REAL,
  response_posts INTEGER,
  measure_skim INTEGER,
  measure_shore INTEGER,
  measure_bio INTEGER,
  measure_disperse INTEGER,
  measure_burn INTEGER,
  description TEXT,
  publisher_url TEXT NOT NULL,
  coordinate_semantics TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_incidentnews_date
  ON incidentnews_incidents(notification_date DESC);
CREATE INDEX IF NOT EXISTS idx_incidentnews_threat_date
  ON incidentnews_incidents(threat,notification_date DESC);
CREATE INDEX IF NOT EXISTS idx_incidentnews_lat_lon
  ON incidentnews_incidents(latitude,longitude);
CREATE TABLE IF NOT EXISTS incidentnews_imports (
  id INTEGER PRIMARY KEY CHECK(id=1),
  records INTEGER NOT NULL,
  coordinate_records INTEGER NOT NULL,
  retrieved_at TEXT NOT NULL,
  source_url TEXT NOT NULL,
  original_sha256 TEXT NOT NULL,
  normalized_sha256 TEXT NOT NULL,
  imported_at TEXT NOT NULL
);
"""


def initialize_incidentnews(conn):
    conn.executescript(TABLES)


def _sha(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as data:
        for chunk in iter(lambda:data.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_rows(path, *, yield_db_rows=True):
    from scripts.build_noaa_incidentnews import COLUMNS
    with gzip.open(path,"rt",encoding="utf-8",newline="") as handle:
        rdr=csv.DictReader(handle)
        if tuple(rdr.fieldnames or ()) != COLUMNS:
            raise ValueError("IncidentNews normalized schema mismatch")
        for r in rdr:
            if yield_db_rows:
                yield (
                    r["incident_id"], r["notification_date"], r["name"], r["location"],
                    float(r["latitude"]) if r["latitude"] else None,
                    float(r["longitude"]) if r["longitude"] else None,
                    r["threat"], r["tags"], r["commodity"],
                    float(r["potential_release_gallons_max"])
                    if r["potential_release_gallons_max"] else None,
                    int(r["response_posts"]) if r["response_posts"] else None,
                    *(int(r[x]) if r[x] else None for x in (
                        "measure_skim","measure_shore","measure_bio",
                        "measure_disperse","measure_burn")),
                    r["description"], r["publisher_url"], r["coordinate_semantics"],
                )
            else:
                yield r


def validate_manifest(conn, manifest):
    """Compare exact indexed source counts and publisher SHA to source manifest."""
    if manifest.get("schema_version")!="1.0" or \
            manifest.get("publisher")!="NOAA Office of Response and Restoration IncidentNews" or \
            manifest.get("complete_publisher_snapshot") is not True:
        raise ValueError("Unrecognized or incomplete IncidentNews source manifest")
    records=conn.execute("SELECT COUNT(*) FROM incidentnews_incidents").fetchone()[0]
    geo=conn.execute("""SELECT COUNT(*) FROM incidentnews_incidents
              WHERE latitude IS NOT NULL AND longitude IS NOT NULL""").fetchone()[0]
    counts={r[0]:r[1] for r in conn.execute(
        "SELECT threat,COUNT(*) FROM incidentnews_incidents GROUP BY threat")}
    imported=conn.execute("SELECT * FROM incidentnews_imports WHERE id=1").fetchone()
    if (not imported or records<=0 or records != manifest.get("records") or
        geo != manifest.get("coordinate_records") or
        counts != manifest.get("threat_counts") or
        imported["records"]!=records or imported["coordinate_records"]!=geo or
        imported["original_sha256"]!=manifest.get("original_sha256") or
        imported["normalized_sha256"]!=manifest.get("normalized_sha256")):
        raise ValueError("IncidentNews imported snapshot differs from source provenance")
    return {"state":"ready_partial","source":"NOAA IncidentNews Selected Spills",
            "records":records,"coordinate_records":geo,
            "threat_counts":counts,"retrieved_at":imported["retrieved_at"],
            "earliest_notification_date":manifest.get("earliest_notification_date"),
            "latest_notification_date":manifest.get("latest_notification_date"),
            "scope":"Selected coastal/spill response cases; not all reported spills or attributed insured sites"}


def import_incidentnews(conn, normalized_path, manifest_path):
    """Complete-snapshot atomic replacement, never per-site loss attribution."""
    from scripts.build_noaa_incidentnews import COLUMNS, validate
    normalized_path=Path(normalized_path)
    manifest=json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if manifest.get("normalized_columns")!=list(COLUMNS) or \
            manifest.get("source_url")!="https://incidentnews.noaa.gov/raw/incidents.csv" or \
            manifest.get("complete_publisher_snapshot") is not True:
        raise ValueError("IncidentNews source scope or columns mismatch")
    if _sha(normalized_path)!=manifest.get("normalized_sha256"):
        raise ValueError("IncidentNews source checksum mismatch")
    validate(normalized_path,manifest)
    initialize_incidentnews(conn)
    when=datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        with conn:
            conn.execute("DELETE FROM incidentnews_incidents")
            conn.executemany("INSERT INTO incidentnews_incidents VALUES ("+
                             ",".join("?" for _ in range(19))+")",
                             _normalized_rows(normalized_path))
            conn.execute("DELETE FROM incidentnews_imports")
            conn.execute("""INSERT INTO incidentnews_imports
              (id,records,coordinate_records,retrieved_at,source_url,original_sha256,
               normalized_sha256,imported_at) VALUES(1,?,?,?,?,?,?,?)""",
               (manifest["records"],manifest["coordinate_records"],
                manifest["retrieved_at"],manifest["source_url"],
                manifest["original_sha256"],manifest["normalized_sha256"],when))
            outcome=validate_manifest(conn,manifest)
    except Exception:
        conn.rollback()
        raise
    return outcome


def status(conn):
    has=conn.execute("""SELECT 1 FROM sqlite_master WHERE type='table'
                        AND name='incidentnews_imports'""").fetchone()
    if not has:
        return {"state":"not_imported","records":None,
                "source":"NOAA IncidentNews Selected Spills",
                "scope":"Selected NOAA OR&R coastal/spill scientific response reports"}
    row=conn.execute("SELECT * FROM incidentnews_imports WHERE id=1").fetchone()
    if row is None:
        return {"state":"not_imported","records":None,
                "source":"NOAA IncidentNews Selected Spills"}
    return {"state":"imported_private_backend","source":"NOAA IncidentNews Selected Spills",
            "records":row["records"],"coordinate_records":row["coordinate_records"],
            "retrieved_at":row["retrieved_at"],
            "scope":"Selected NOAA OR&R response reports, not nationwide spill census"}


def search(conn, *, q="", threat="", from_date="", to_date="", limit=50, offset=0):
    if not 1<=int(limit)<=100 or not 0<=int(offset)<=100000:
        raise ValueError("Invalid IncidentNews pagination")
    wheres=[]
    args=[]
    if threat:
        if threat not in ("Oil","Chemical","Other","Unspecified"):
            raise ValueError("Unknown IncidentNews threat category")
        wheres.append("threat=?");args.append(threat)
    if from_date:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}",from_date):
            raise ValueError("Invalid start date")
        wheres.append("notification_date>=?");args.append(from_date)
    if to_date:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}",to_date):
            raise ValueError("Invalid end date")
        wheres.append("notification_date<=?");args.append(to_date)
    query=str(q or "").strip()[:110]
    if query:
        # Small curated response catalog, not a full nationwide NRC dump.
        # Escape LIKE metacharacters so analyst input is literal and bounded.
        like="%"+query.replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%"
        wheres.append("""(name LIKE ? ESCAPE '\\' OR
                         location LIKE ? ESCAPE '\\' OR
                         commodity LIKE ? ESCAPE '\\')""")
        args.extend((like,like,like))
    clause=" WHERE "+" AND ".join(wheres) if wheres else ""
    total=conn.execute("SELECT COUNT(*) FROM incidentnews_incidents"+clause,args).fetchone()[0]
    rows=conn.execute("SELECT * FROM incidentnews_incidents"+clause+
       " ORDER BY notification_date DESC,incident_id DESC LIMIT ? OFFSET ?",
       args+[int(limit),int(offset)]).fetchall()
    return {"items":[dict(row) for row in rows],"total":total,"limit":int(limit),
            "offset":int(offset),"source_scope":"Selective NOAA OR&R reports; no verified property loss"}


def nearby_reviewed_site(workspace, index, facility_id, *, radius_km=20, limit=40):
    """Return geographic *candidates* only for an independently reviewed site."""
    if not 1<=radius_km<=100 or not 1<=limit<=100:
        raise ValueError("Radius and limit outside supported range")
    site=workspace.execute(
        "SELECT id,latitude,longitude FROM facilities WHERE id=?",(facility_id,)).fetchone()
    if site is None:
        raise ValueError("Unknown research facility")
    review=workspace.execute(
        "SELECT * FROM location_reviews WHERE facility_id=?",(facility_id,)).fetchone()
    if not is_reviewed_site_coordinate(site,review):
        return {"facility_id":facility_id,"status":"unassessed_location",
                "items":[],"total_nearby":None,
                "caveat":"Independently verified current property coordinates required"}
    lat,lon=float(site["latitude"]),float(site["longitude"])
    delta=radius_km/109+0.05
    # Geographic bounding box overinclusive by design; exact haversine below.
    # Longitude wrap is rare for coastal cases; exclude polar imprecision.
    if abs(lat)>=89.0:
        raise ValueError("Polar proximity screening not supported")
    dlon=min(180.,radius_km/(111*max(0.001,__import__("math").cos(
         __import__("math").radians(lat))))+0.05)
    lo,hi=lon-dlon,lon+dlon
    if lo<-180 or hi>180:
        lon_filter="(longitude>=? OR longitude<=?)"
        lon_args=[lo+360,hi] if lo<-180 else [lo,hi-360]
    else:
        lon_filter="longitude BETWEEN ? AND ?"
        lon_args=[lo,hi]
    rows=index.execute("SELECT * FROM incidentnews_incidents WHERE latitude BETWEEN ? AND ? AND "+
          lon_filter+" LIMIT 25001",[max(-90.,lat-delta),min(90.,lat+delta),*lon_args]).fetchall()
    if len(rows)>25000:
        return {"facility_id":facility_id,"status":"partial_scan_limit",
                "total_nearby":None,"items":[],
                "caveat":"Source candidate scan limit hit; unable to draw an absence conclusion"}
    matched=[]
    for row in rows:
        km=haversine_km(lat,lon,row["latitude"],row["longitude"])
        if km<=radius_km:
            item=dict(row);item["distance_km"]=round(km,2)
            matched.append(item)
    matched.sort(key=lambda x:(x["notification_date"],x["incident_id"]),reverse=True)
    return {"facility_id":facility_id,"status":"proximity_candidates_only",
            "total_nearby":len(matched),"items":matched[:limit],
            "display_truncated":len(matched)>limit,"radius_km":radius_km,
            "caveat":"NOAA IncidentNews coordinates may be approximate; proximity is not verified site damage, actual spilled volume, insured loss or policy exposure"}
