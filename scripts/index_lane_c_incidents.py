"""Isolated authenticated-backend-ready Lane C SOURCE OBSERVATION index.

This is a regulator-source record index, NOT a universal physical facility
registry. It contains no insurer site assignments, inference or risk scoring.
Never publish the SQLite file or query responses in public GitHub CI artifacts.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import gzip
import json
import re
from pathlib import Path
import sqlite3

try:
    from scripts.build_industrial_incidents import digest
    from scripts.build_csb_incidents import validate_csb
    from scripts.build_nrc_enriched import validate as validate_nrc
except ModuleNotFoundError:  # direct python scripts/index_lane_c_incidents.py
    from build_industrial_incidents import digest
    from build_csb_incidents import validate_csb
    from build_nrc_enriched import validate as validate_nrc

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE source_incidents (
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    publisher_native_id TEXT NOT NULL,
    source_vintage TEXT NOT NULL,
    incident_date TEXT,
    city TEXT,
    state TEXT,
    latitude REAL,
    longitude REAL,
    evidence_status TEXT NOT NULL,
    site_link_status TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_json TEXT NOT NULL,
    PRIMARY KEY(source,source_id),
    CHECK(site_link_status = 'candidate_only_not_matched'),
    CHECK(latitude IS NULL OR (latitude BETWEEN -90 AND 90)),
    CHECK(longitude IS NULL OR (longitude BETWEEN -180 AND 180))
) WITHOUT ROWID;
CREATE INDEX source_incidents_date ON source_incidents(source,incident_date);
CREATE INDEX source_incidents_state ON source_incidents(source,state);
CREATE INDEX source_incidents_geo ON source_incidents(source,latitude,longitude);
"""

CONFIG = {
    "nrc": {
        "source":"USCG NRC annual source report",
        "validate":validate_nrc,
        "id":"source_id", "native_id":"source_id", "vintage":"year",
        "city":"incident_city", "state":"incident_state",
        "lat":"latitude", "lon":"longitude", "evidence":"report_status",
        "site":"site_link_status", "url":"source_document",
    },
    "csb": {
        "source":"CSB release reported event",
        "validate":validate_csb,
        "id":"source_id", "native_id":"original_number", "vintage":"release",
        "city":"incident_city", "state":"incident_state",
        "lat":None, "lon":None, "evidence":"evidence_status",
        "site":"site_link_status", "url":"source_document",
    }
}

def config_for_source(key, manifest=None):
    if key in CONFIG:
        config = CONFIG[key]
    elif re.fullmatch(r"nrc_20[0-9]{2}",key):
        config = CONFIG["nrc"]
        if manifest and int(key[4:]) != int(manifest["year"]):
            raise ValueError("Annual NRC source namespace and manifest vintage disagree")
    else:
        raise ValueError("Unknown publisher source or annual NRC namespace")
    return config

def _float_or_none(s, low, high):
    if s is None or s == "":
        return None
    x = float(s)
    if not low <= x <= high:
        raise ValueError("Invalid publisher coordinate in normalized data")
    return x

def index_sources(database, source_inputs, audit_path):
    """Source inputs: list[(source, gz_path, source_manifest_path)]."""
    database, audit_path = Path(database), Path(audit_path)
    database.parent.mkdir(parents=True, exist_ok=True)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    if database.exists():
        raise ValueError("Index target exists: refuse to overwrite without explicit deletion")
    summaries = {}
    try:
        conn = sqlite3.connect(database)
        with conn:
            conn.executescript(SCHEMA)
            for key, source_path, manifest_path in source_inputs:
                if key in summaries:
                    raise ValueError("Duplicate source index requested")
                manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
                cfg = config_for_source(key,manifest)
                cfg["validate"](source_path, manifest)
                inserted, geocoded, min_date, max_date = 0, 0, None, None
                with gzip.open(source_path, "rt", encoding="utf-8", newline="") as fh:
                    for row in csv.DictReader(fh):
                        incident_date = row["incident_date"] or None
                        lat = _float_or_none(row.get(cfg["lat"]) if cfg["lat"] else "", -90, 90)
                        lon = _float_or_none(row.get(cfg["lon"]) if cfg["lon"] else "", -180, 180)
                        if (lat is None) != (lon is None):
                            raise ValueError("Partially geocoded source row")
                        if row[cfg["site"]] != "candidate_only_not_matched":
                            raise ValueError("Unexpected insured property inference")
                        conn.execute("""INSERT INTO source_incidents (
                            source,source_id,publisher_native_id,source_vintage,incident_date,
                            city,state,latitude,longitude,evidence_status,site_link_status,
                            source_url,source_json
                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                            key, row[cfg["id"]], row[cfg["native_id"]],
                            str(manifest[cfg["vintage"]]), incident_date,
                            row.get(cfg["city"]) or "", row.get(cfg["state"]) or "",
                            lat, lon, row[cfg["evidence"]], row[cfg["site"]],
                            row[cfg["url"]], json.dumps(row, ensure_ascii=False, sort_keys=True)
                        ))
                        inserted += 1
                        geocoded += lat is not None
                        if incident_date:
                            min_date = min(min_date, incident_date) if min_date else incident_date
                            max_date = max(max_date, incident_date) if max_date else incident_date
                expected = manifest["accepted_rows"]
                if inserted != expected:
                    raise ValueError("Source index count does not match real normalized manifest")
                if (key == "nrc" or key.startswith("nrc_")) and geocoded != manifest["coordinate_records"]:
                    raise ValueError("NRC coordinate index count differs from source")
                if key == "csb" and geocoded != 0:
                    raise ValueError("CSB source should not have inferred coordinates")
                summaries[key] = {
                    "raw_sha256": manifest["raw_sha256"],
                    "normalized_sha256": manifest["normalized_sha256"],
                    "source_vintage": str(manifest[cfg["vintage"]]),
                    "downloaded_rows": manifest.get("raw_data_rows",manifest.get("nrc_reports")),
                    "accepted_rows": expected,
                    "rejected_rows": manifest["rejected_rows"],
                    "indexed_rows_ephemeral": inserted,
                    "coordinates_indexed": geocoded,
                    "first_incident_date": min_date,
                    "last_incident_date": max_date,
                    "source_id_scope": ("release-scoped" if key == "csb" else "annual native SEQNOS")
                }
            integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
            if integrity != "ok":
                raise ValueError("Source index SQLite integrity failure: " + str(integrity))
            actual = conn.execute("SELECT source,COUNT(*),COUNT(DISTINCT source_id) FROM source_incidents GROUP BY source").fetchall()
            for key, count, unique in actual:
                if count != unique or count != summaries[key]["accepted_rows"]:
                    raise ValueError("Source index identity count mismatch")
            # Query each source via real SQL index and confirm exact source IDs.
            for key in summaries:
                record = conn.execute("SELECT source_id,evidence_status,site_link_status FROM source_incidents WHERE source=? LIMIT 1", (key,)).fetchone()
                if not record or record[2] != "candidate_only_not_matched":
                    raise ValueError("Source query/evidence state test failed")
        conn.close()
        report = {
            "state": "INDEXED_EPHEMERAL_CI_NOT_DEPLOYED",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "quick_check": "ok", "sources": summaries,
            "total_indexed_ephemeral": sum(x["indexed_rows_ephemeral"] for x in summaries.values()),
            "indexed_persistent_production": 0,
            "deployed_in_app": 0,
            "physical_sites_linked_and_corrob": 0,
            "caveat": "Source-only sqlite produced on disposable runner; not a persistent authenticated backend or live app. Do not publish SQLite with row-level source data."
        }
        audit_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return report
    except BaseException:
        database.unlink(missing_ok=True)
        raise

def search_source(db_path, *, source, state=None, since=None, page=1, page_size=50):
    if not 1 <= page_size <= 200 or page < 1:
        raise ValueError("Unsupported paging")
    config_for_source(source)
    with sqlite3.connect(db_path) as conn:
        where = ["source=?"]
        params = [source]
        if state is not None:
            where.append("state=?"); params.append(state)
        if since is not None:
            where.append("incident_date>=?"); params.append(since)
        clause = " AND ".join(where)
        count = conn.execute(f"SELECT COUNT(*) FROM source_incidents WHERE {clause}", params).fetchone()[0]
        rows = conn.execute(f"SELECT source,source_id,source_vintage,incident_date,city,state,evidence_status FROM source_incidents WHERE {clause} ORDER BY incident_date DESC,source_id LIMIT ? OFFSET ?", [*params,page_size,(page-1)*page_size]).fetchall()
    return {"total":count,"page":page,"page_size":page_size,"items":[dict(zip(("source","source_id","source_vintage","incident_date","city","state","evidence_status"),r)) for r in rows]}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--audit",type=Path,required=True)
    p.add_argument("--nrc",type=Path,required=True)
    p.add_argument("--nrc-manifest",type=Path,required=True)
    p.add_argument("--csb",type=Path,required=True)
    p.add_argument("--csb-manifest",type=Path,required=True)
    a = p.parse_args()
    print(json.dumps(index_sources(a.db,[
        ("nrc",a.nrc,a.nrc_manifest),("csb",a.csb,a.csb_manifest)
    ],a.audit),indent=2))

if __name__ == "__main__":
    main()
