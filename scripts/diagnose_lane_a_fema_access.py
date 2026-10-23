"""Bounded FEMA transport diagnostics with real native source IDs when reachable.

No site mapping or geometry-validated flood polygon claims are made here.
"""
import argparse
import hashlib
import json
import pathlib
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

FEMA = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28"
FEMA_LEGACY = "https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer/28"


def native_source_key(attr):
    df, area, oid = attr.get("DFIRM_ID"), attr.get("FLD_AR_ID"), attr.get("OBJECTID")
    if df and area:
        return "dfirm:" + str(df) + ":fld_ar:" + str(area)
    if oid is not None:
        return "service_objectid:" + str(oid)
    return None


def request_strategy(base, params, method):
    url = base.rstrip("/") + "/query"
    form = urllib.parse.urlencode(params).encode("ascii")
    if method == "GET":
        url += "?" + form.decode("ascii")
        body = None
    else:
        body = form
    request = urllib.request.Request(
        url, data=body, method=method,
        headers={"Accept": "application/json",
                 "User-Agent": "FacilityRisk-FEMA-source-QA/1.0",
                 "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(request, timeout=16) as response:
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("Transport reply larger than 2MB diagnostic limit")
        actual_url = response.geturl()
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("error"):
        raise ValueError("ArcGIS returned query error: " + str(data.get("error") if isinstance(data, dict) else type(data))[:500])
    if not isinstance(data.get("features"), list):
        raise ValueError("ArcGIS query missing features list")
    return data, raw, actual_url


def run(out_dir, requester=request_strategy, strategies=None):
    output = pathlib.Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "raw").mkdir(exist_ok=True)
    db = sqlite3.connect(output / "fema-attribute-only.sqlite")
    db.executescript("""
      CREATE TABLE IF NOT EXISTS fema_attribute_samples(
        strategy TEXT NOT NULL, source_service TEXT NOT NULL,
        source_key TEXT NOT NULL, native_attributes_json TEXT NOT NULL,
        response_sha256 TEXT NOT NULL,
        PRIMARY KEY(strategy,source_key)
      );
      CREATE INDEX IF NOT EXISTS native_ref ON fema_attribute_samples(source_key);
    """)
    point_params = {
        "f": "json", "geometry": "-90.082,29.948",
        "geometryType": "esriGeometryPoint", "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "OBJECTID,DFIRM_ID,FLD_AR_ID,FLD_ZONE,SFHA_TF,SOURCE_CIT",
        "returnGeometry": "false", "resultRecordCount": "10",
    }
    minimal_params = {
        "f": "json", "where": "1=1", "outFields": "OBJECTID,DFIRM_ID,FLD_AR_ID",
        "returnGeometry": "false", "resultRecordCount": "1",
    }
    if strategies is None:
        strategies = (
            ("direct_minimal_get", FEMA, minimal_params, "GET"),
            ("direct_point_get", FEMA, point_params, "GET"),
            ("direct_point_post", FEMA, point_params, "POST"),
            ("legacy_point_get", FEMA_LEGACY, point_params, "GET"),
        )
    m = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "FEMA official query transport diagnostics, attribute-only, NO geometry/site validation",
        "site_matches": 0, "source_complete": False, "strategies": [],
        "total_raw_observations": 0, "total_accepted_observations": 0,
        "total_rejected_observations": 0,
    }
    for name, service, params, method in strategies:
        result = {"strategy": name, "method": method, "source_service": service,
                  "point_is_geographic_probe": True, "return_geometry": False,
                  "state": "PROBED", "raw_count": None, "accepted": None,
                  "rejected": None}
        try:
            doc, raw, url = requester(service, params, method)
            digest = hashlib.sha256(raw).hexdigest()
            rawfile = name + ".json"
            (output / "raw" / rawfile).write_bytes(raw)
            result.update({"source_url": url, "response_sha256": digest,
                           "raw_file": rawfile, "downloaded_bytes": len(raw)})
            results, rejects = [], []
            for index, f in enumerate(doc["features"]):
                attr = f.get("attributes") if isinstance(f, dict) else None
                key = native_source_key(attr) if isinstance(attr, dict) else None
                if not key:
                    rejects.append({"index": index, "reason": "no_native_id"})
                    continue
                if key in {x["key"] for x in results}:
                    rejects.append({"index": index, "reason": "duplicate_source_id"})
                    continue
                results.append({"key": key, "attrs": attr})
            result.update({"raw_count": len(doc["features"]), "accepted": len(results),
                           "rejected": len(rejects), "rejections": rejects,
                           "state": "STAGED_ATTRIBUTES_ONLY"})
            for entry in results:
                db.execute("INSERT INTO fema_attribute_samples VALUES (?,?,?,?,?)", (
                    name, service, entry["key"],
                    json.dumps(entry["attrs"], sort_keys=True, separators=(",", ":")),
                    digest,
                ))
            m["total_raw_observations"] += result["raw_count"]
            m["total_accepted_observations"] += result["accepted"]
            m["total_rejected_observations"] += result["rejected"]
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            result.update({"error_type": type(exc).__name__, "error": str(exc)[:500]})
        m["strategies"].append(result)
    db.commit()
    m["indexed_observations"] = db.execute("SELECT COUNT(*) FROM fema_attribute_samples").fetchone()[0]
    m["distinct_native_keys"] = db.execute("SELECT COUNT(DISTINCT source_key) FROM fema_attribute_samples").fetchone()[0]
    m["sqlite_quick_check"] = db.execute("PRAGMA quick_check").fetchone()[0]
    db.close()
    m["source_sample_reconciled"] = (
        m["total_raw_observations"] == m["total_accepted_observations"] + m["total_rejected_observations"]
        and m["indexed_observations"] == m["total_accepted_observations"]
        and m["sqlite_quick_check"] == "ok"
    )
    m["official_attribute_ingestion_succeeded"] = (
        m["source_sample_reconciled"] and m["total_accepted_observations"] > 0
        and any(x["state"] == "STAGED_ATTRIBUTES_ONLY" for x in m["strategies"])
    )
    (output / "manifest.json").write_text(json.dumps(m, indent=2, sort_keys=True) + "\n")
    return m


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", default="data/lane_a/fema_transport")
    a = p.parse_args(argv)
    m = run(a.output_dir)
    print("LANE_A_FEMA_TRANSPORT=" + json.dumps({
        "official_attribute_ingestion_succeeded": m["official_attribute_ingestion_succeeded"],
        "source_sample_reconciled": m["source_sample_reconciled"],
        "raw": m["total_raw_observations"],
        "accepted": m["total_accepted_observations"],
        "rejected": m["total_rejected_observations"],
        "indexed": m["indexed_observations"],
        "strategies": [{"name": x["strategy"], "status": x["state"],
                        "accepted": x["accepted"], "error": x.get("error")}
                       for x in m["strategies"]],
    }, sort_keys=True))
    return 0 if m["official_attribute_ingestion_succeeded"] else 2


if __name__ == "__main__":
    sys.exit(main())
