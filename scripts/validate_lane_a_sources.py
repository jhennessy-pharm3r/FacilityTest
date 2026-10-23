"""Live, non-exhaustive official FEMA NFHL + USDA WHP 2023 source QA.

Geographic probes are NOT insured locations or verified facility coordinates.
Original responses and an isolated, source-only SQLite sample are staged in CI.
"""
import argparse
import hashlib
import json
import math
import pathlib
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

FEMA = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28"
WHP = "https://imagery.geoplatform.gov/iipp/rest/services/Fire_Aviation/USFS_EDW_RMRS_WildfireHazardPotentialContinuous/ImageServer"
WHP_LEGACY = "https://apps.fs.usda.gov/arcx/rest/services/RDW_Wildfire/RMRS_WildfireHazardPotential_2023/MapServer"
# Geographic test windows, NOT candidate physical facilities or site coordinates.
FLOOD_WINDOWS = (
    ("new_orleans", (-90.084, 29.946, -90.080, 29.950)),
    ("houston", (-95.375, 29.758, -95.371, 29.762)),
    ("sacramento", (-121.502, 38.579, -121.498, 38.583)),
)
WILDFIRE_POINTS = (
    ("tahoe", (-120.04, 39.18)),
    ("boise", (-116.17, 43.60)),
    ("denver", (-105.30, 39.64)),
)


def fetch_json(base, operation, params, timeout=35):
    url = base.rstrip("/") + ("/" + operation.lstrip("/") if operation else "") + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": "FacilityRisk-LaneA-Validation/1.1",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read(10_000_001)
        if len(raw) > 10_000_000:
            raise ValueError("Official response exceeds 10MB sample safety limit")
        actual_url = response.geturl()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Expected ArcGIS JSON object")
    if payload.get("error"):
        raise ValueError("ArcGIS error: " + json.dumps(payload["error"], sort_keys=True)[:900])
    return payload, raw, actual_url


def fetch_capture(base, operation, params, path, fetch=fetch_json):
    """Return (payload, receipt); error receipt has no invented raw/row counts."""
    try:
        payload, raw, url = fetch(base, operation, params)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        receipt = {
            "state": "DOWNLOADED",
            "source_url": url,
            "raw_file": path.name,
            "bytes": len(raw),
            "raw_sha256": hashlib.sha256(raw).hexdigest(),
        }
        return payload, receipt
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return None, {
            "state": "PROBED",
            "source_url": base.rstrip("/") + ("/" + operation.lstrip("/") if operation else ""),
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }


def parse_fema(features, source_url):
    if not isinstance(features, list):
        raise ValueError("FEMA query missing features array")
    accepted, rejected, native = [], [], set()
    for index, feature in enumerate(features):
        attr = feature.get("attributes") if isinstance(feature, dict) else None
        geometry = feature.get("geometry") if isinstance(feature, dict) else None
        if not isinstance(attr, dict):
            rejected.append({"index": index, "reason": "missing_attributes"})
            continue
        oid = attr.get("OBJECTID")
        stable = attr.get("FLD_AR_ID")
        df = attr.get("DFIRM_ID")
        if oid is None and not (stable and df):
            rejected.append({"index": index, "reason": "missing_native_identifier"})
            continue
        rings = geometry.get("rings") if isinstance(geometry, dict) else None
        if not isinstance(rings, list) or not rings:
            rejected.append({"index": index, "reason": "missing_polygon_geometry"})
            continue
        try:
            coordinates = [p for ring in rings for p in ring]
            if not coordinates or not all(
                isinstance(p, list) and len(p) >= 2 and
                all(isinstance(v, (int, float)) and math.isfinite(v) for v in p[:2]) and
                -180 <= p[0] <= 180 and -90 <= p[1] <= 90
                for p in coordinates
            ):
                raise ValueError("Bad WGS84 polygon coordinate")
        except (TypeError, ValueError):
            rejected.append({"index": index, "reason": "invalid_wgs84_polygon"})
            continue
        # DFIRM_ID + FLD_AR_ID are native identifiers. OBJECTID is retained
        # but scoped to this service; it is not a canonical property ID.
        source_key = (
            "dfirm:" + str(df) + ":fld_ar:" + str(stable)
            if df and stable else "service_objectid:" + str(oid)
        )
        if source_key in native:
            rejected.append({"index": index, "reason": "duplicate_in_response"})
            continue
        native.add(source_key)
        accepted.append({
            "source_key": source_key,
            "objectid": oid,
            "dfirm_id": df,
            "version_id": attr.get("VERSION_ID"),
            "fld_ar_id": stable,
            "flood_zone": attr.get("FLD_ZONE"),
            "source_citation": attr.get("SOURCE_CIT"),
            "source_url": source_url,
            "raw_feature": feature,
        })
    return accepted, rejected


def parse_whp(payload):
    # ImageServer identify returns one numeric raster pixel value, not wildfire incidents.
    raw_value = payload.get("value")
    if raw_value is None and isinstance(payload.get("properties"), dict):
        values = payload["properties"].get("Values")
        raw_value = values[0] if isinstance(values, list) and values else None
    if isinstance(raw_value, (list, dict, bool)) or raw_value is None:
        return None, "no_numeric_pixel"
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None, "no_numeric_pixel"
    if not math.isfinite(value) or value < 0:
        return None, "no_numeric_pixel"
    return value, None


def setup_sqlite(target):
    target.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(target)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS fema_source_observations(
          probe TEXT NOT NULL, source_key TEXT NOT NULL,
          objectid TEXT, dfirm_id TEXT, version_id TEXT, fld_ar_id TEXT,
          flood_zone TEXT, source_citation TEXT, source_url TEXT NOT NULL,
          raw_feature_json TEXT NOT NULL,
          PRIMARY KEY(probe,source_key)
        );
        CREATE INDEX IF NOT EXISTS fema_native_ids ON
          fema_source_observations(dfirm_id,fld_ar_id);
        CREATE TABLE IF NOT EXISTS usfs_raster_observations(
          probe TEXT PRIMARY KEY, latitude REAL NOT NULL, longitude REAL NOT NULL,
          release TEXT NOT NULL, service_url TEXT NOT NULL,
          pixel_value REAL NOT NULL, raw_response_json TEXT NOT NULL
        );
    """)
    return db


def run(output_dir, fetch=fetch_json, windows=FLOOD_WINDOWS, points=WILDFIRE_POINTS):
    output_dir = pathlib.Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw"
    db = setup_sqlite(output_dir / "source-only.sqlite")
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "non_exhaustive_geographic_source_qa_NOT_facility_site_matching",
        "verified_physical_facility_count": 0,
        "national_coverage_claim": False,
        "sources": {
            "fema_nfhl": {"publisher": "FEMA", "url": FEMA, "layer": 28,
                          "published_vintage": "varies_by_DFIRM_and_revision",
                          "samples": [], "metadata": {}, "sample_accepted": 0,
                          "sample_rejected": 0, "sample_raw": 0},
            "usfs_whp_continuous_2023": {
                "publisher": "USDA Forest Service", "url": WHP, "release": "2023",
                "resolution_m": 270, "samples": [], "metadata": {},
                "sample_accepted": 0, "sample_rejected": 0, "sample_raw": 0,
            },
        },
    }
    fema = manifest["sources"]["fema_nfhl"]
    whp = manifest["sources"]["usfs_whp_continuous_2023"]
    for key, base in (("fema_nfhl", FEMA), ("usfs_whp_continuous_2023", WHP)):
        payload, receipt = fetch_capture(base, "", {"f": "json"}, raw_dir / (key + ".metadata.json"), fetch)
        if payload is not None:
            if key == "fema_nfhl":
                receipt["geometry_type"] = payload.get("geometryType")
                receipt["native_oid_field"] = payload.get("objectIdField")
                receipt["reported_field_names"] = [f.get("name") for f in payload.get("fields", []) if isinstance(f, dict)]
            else:
                receipt["pixel_size_x"] = payload.get("pixelSizeX")
                receipt["pixel_type"] = payload.get("pixelType")
                receipt["service_name"] = payload.get("name")
            receipt["metadata_valid"] = (
                receipt.get("geometry_type") == "esriGeometryPolygon"
                if key == "fema_nfhl" else
                bool(receipt.get("service_name")) and receipt.get("pixel_size_x") is not None
            )
        manifest["sources"][key]["metadata"] = receipt

    for name, bbox in windows:
        bounds = {"xmin": bbox[0], "ymin": bbox[1], "xmax": bbox[2], "ymax": bbox[3],
                  "spatialReference": {"wkid": 4326}}
        params = {
            "f": "json", "geometry": json.dumps(bounds, separators=(",", ":")),
            "geometryType": "esriGeometryEnvelope", "inSR": 4326, "outSR": 4326,
            "spatialRel": "esriSpatialRelIntersects", "returnGeometry": "true",
            "outFields": "*", "resultRecordCount": 10,
        }
        payload, receipt = fetch_capture(FEMA, "query", params, raw_dir / ("fema." + name + ".json"), fetch)
        receipt.update({"geographic_probe": name, "bbox_wgs84": list(bbox),
                        "not_site_matched": True, "sample_limit": 10,
                        "accepted": 0, "rejected": 0, "raw_records": 0})
        if payload is not None:
            try:
                accepted, rejected = parse_fema(payload.get("features"), receipt["source_url"])
                receipt["raw_records"] = len(payload["features"])
                receipt["accepted"] = len(accepted)
                receipt["rejected"] = len(rejected)
                receipt["rejection_reasons"] = rejected
                receipt["source_exceeded_transfer_limit"] = bool(payload.get("exceededTransferLimit"))
                receipt["state"] = "STAGED_SAMPLE"
                for row in accepted:
                    db.execute("INSERT INTO fema_source_observations VALUES(?,?,?,?,?,?,?,?,?,?)", (
                        name, row["source_key"], str(row["objectid"]) if row["objectid"] is not None else None,
                        row["dfirm_id"], row["version_id"], row["fld_ar_id"], row["flood_zone"],
                        row["source_citation"], row["source_url"],
                        json.dumps(row["raw_feature"], sort_keys=True, separators=(",", ":")),
                    ))
            except (ValueError, sqlite3.Error) as exc:
                receipt["state"] = "DOWNLOADED_NOT_VALIDATED"
                receipt["error"] = str(exc)[:500]
        for field, amount in (("sample_raw", receipt["raw_records"]),
                              ("sample_accepted", receipt["accepted"]), ("sample_rejected", receipt["rejected"])):
            fema[field] += amount
        fema["samples"].append(receipt)

    for name, (lon, lat) in points:
        geom = {"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}
        payload, receipt = fetch_capture(WHP, "identify", {
            "f": "json", "geometry": json.dumps(geom, separators=(",", ":")),
            "geometryType": "esriGeometryPoint",
            "returnGeometry": "false", "returnCatalogItems": "false",
        }, raw_dir / ("usfs." + name + ".json"), fetch)
        receipt.update({"geographic_probe": name, "point_wgs84": [lon, lat],
                        "not_site_matched": True, "raw_records": 0,
                        "accepted": 0, "rejected": 0})
        if payload is not None:
            receipt["raw_records"] = 1
            value, reason = parse_whp(payload)
            if reason:
                receipt["state"] = "DOWNLOADED_NO_PIXEL"
                receipt["rejected"] = 1
                receipt["rejection_reason"] = reason
            else:
                receipt["state"] = "STAGED_SAMPLE"
                receipt["accepted"] = 1
                receipt["pixel_value"] = value
                db.execute("INSERT INTO usfs_raster_observations VALUES(?,?,?,?,?,?,?)", (
                    name, lat, lon, "2023", receipt["source_url"], value,
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                ))
        for field, amount in (("sample_raw", receipt["raw_records"]),
                              ("sample_accepted", receipt["accepted"]), ("sample_rejected", receipt["rejected"])):
            whp[field] += amount
        whp["samples"].append(receipt)

    db.commit()
    fema["indexed_observations"] = db.execute("SELECT COUNT(*) FROM fema_source_observations").fetchone()[0]
    fema["distinct_source_keys"] = db.execute("SELECT COUNT(DISTINCT source_key) FROM fema_source_observations").fetchone()[0]
    whp["indexed_observations"] = db.execute("SELECT COUNT(*) FROM usfs_raster_observations").fetchone()[0]
    integrity = db.execute("PRAGMA quick_check").fetchone()[0]
    db.close()
    manifest["sqlite_quick_check"] = integrity
    manifest["stage"] = "SOURCE_ONLY_EPHEMERAL_SAMPLE"
    manifest["source_access_complete"] = all(
        s["metadata"].get("metadata_valid") is True and
        all(x.get("state") == "STAGED_SAMPLE" for x in s["samples"]) and
        s["sample_accepted"] > 0
        for s in manifest["sources"].values()
    )
    manifest["all_qa_reconciled"] = all(
        s["sample_raw"] == s["sample_accepted"] + s["sample_rejected"] and
        s["indexed_observations"] == s["sample_accepted"]
        for s in manifest["sources"].values()
    ) and integrity == "ok"
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="data/lane_a/live_validation")
    args = parser.parse_args(argv)
    m = run(args.output_dir)
    print("LANE_A_VALIDATION_SUMMARY=" + json.dumps({
        "source_access_complete": m["source_access_complete"],
        "all_qa_reconciled": m["all_qa_reconciled"],
        "sources": {key: {
            "metadata": val["metadata"].get("state"),
            "metadata_valid": val["metadata"].get("metadata_valid"),
            "sample_raw": val["sample_raw"],
            "sample_accepted": val["sample_accepted"],
            "sample_rejected": val["sample_rejected"],
            "indexed_observations": val["indexed_observations"],
            "distinct_source_keys": val.get("distinct_source_keys"),
            "states": [sample["state"] for sample in val["samples"]],
            "errors": [sample.get("error", sample.get("rejection_reason")) for sample in val["samples"]
                       if sample.get("error") or sample.get("rejection_reason")],
        } for key, val in m["sources"].items()},
    }, sort_keys=True))
    return 0 if m["source_access_complete"] and m["all_qa_reconciled"] else 2


if __name__ == "__main__":
    sys.exit(main())
