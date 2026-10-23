"""Non-exhaustive Massachusetts government republication QA of FEMA-derived NFHL.

This July 2025 MassGIS statewide FEMA-derived layer is NOT current nationwide FEMA NFHL.
Never silently substitute it for the unavailable FEMA authoritative live service.
"""
import argparse
import json
import pathlib
import sqlite3
import sys
from datetime import datetime, timezone

from scripts.validate_lane_a_sources import fetch_capture, parse_fema, setup_sqlite

MASSGIS = ("https://arcgisserver.digital.mass.gov/arcgisserver/rest/services/"
           "FEMA/FEMA_National_Flood_Hazard_Layer/FeatureServer/0")
MASSGIS_SOURCE = "massgis_ma_nfhl_2025_state_archive"
WINDOW = (-71.056, 42.344, -71.042, 42.354)


def collect(out_dir, fetch=None):
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "raw"
    kwargs = {"fetch": fetch} if fetch is not None else {}
    layer, meta = fetch_capture(MASSGIS, "", {"f": "json"}, raw_dir / "source_metadata.json", **kwargs)
    metadata_ok = bool(
        isinstance(layer, dict)
        and layer.get("geometryType") == "esriGeometryPolygon"
        and layer.get("objectIdField")
        and isinstance(layer.get("fields"), list)
    )
    meta["metadata_valid"] = metadata_ok
    if layer is not None:
        meta["layer_name"] = layer.get("name")
        meta["native_oid_field"] = layer.get("objectIdField")
        meta["reported_field_names"] = [f.get("name") for f in layer.get("fields", []) if isinstance(f, dict)]
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": MASSGIS_SOURCE, "source_url": MASSGIS,
        "publisher": "Commonwealth of Massachusetts MassGIS (FEMA-derived data)",
        "source_data_vintage": "FEMA as of 2025-07-18 per MassGIS source description",
        "coverage": "July 18 2025 MassGIS Massachusetts FEMA NFHL state snapshot; mapped regions only, not national current coverage",
        "not_a_national_nfhl_replacement": True,
        "sfha_only": False,
        "unmapped_areas_are_unknown": True,
        "declared_vintage_is_not_current_live_fema": True,
        "source_link": "https://www.mass.gov/info-details/massgis-data-fema-national-flood-hazard-layer",
        "verified_physical_facilities": 0, "sample_is_national_census": False,
        "metadata": meta, "samples": [], "sample_raw": 0,
        "sample_accepted": 0, "sample_rejected": 0,
    }
    db = setup_sqlite(out_dir / "massgis-source-only.sqlite")
    query_definitions = (
        ("first_five_polygons", None),
        ("boston_harbor_geographic_probe", WINDOW),
    )
    for name, bounds in query_definitions:
        params = {
            "f": "json", "where": "1=1", "outFields": "*",
            "returnGeometry": "true", "outSR": 4326,
            "resultRecordCount": 5,
        }
        if metadata_ok:
            params["orderByFields"] = str(layer["objectIdField"]) + " ASC"
        if bounds is not None:
            params.update({
                "geometry": json.dumps({
                    "xmin": bounds[0], "ymin": bounds[1],
                    "xmax": bounds[2], "ymax": bounds[3],
                    "spatialReference": {"wkid": 4326},
                }, separators=(",", ":")),
                "geometryType": "esriGeometryEnvelope", "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
            })
        data, receipt = fetch_capture(MASSGIS, "query", params, raw_dir / (name + ".json"), **kwargs)
        receipt.update({
            "geographic_probe": name, "sample_limit": 5,
            "query_bbox_wgs84": list(bounds) if bounds else None,
            "not_facility_site_matched": True,
            "raw_records": 0, "accepted": 0, "rejected": 0,
        })
        if data is not None:
            try:
                good, bad = parse_fema(data.get("features"), MASSGIS)
                receipt["raw_records"] = len(data["features"])
                receipt["accepted"] = len(good)
                receipt["rejected"] = len(bad)
                receipt["rejections"] = bad
                receipt["source_exceeded_transfer_limit"] = bool(data.get("exceededTransferLimit"))
                receipt["state"] = "STAGED_SAMPLE"
                for row in good:
                    db.execute("INSERT INTO fema_source_observations VALUES(?,?,?,?,?,?,?,?,?,?)", (
                        name, row["source_key"],
                        str(row["objectid"]) if row["objectid"] is not None else None,
                        row["dfirm_id"], row["version_id"], row["fld_ar_id"],
                        row["flood_zone"], row["source_citation"],
                        MASSGIS,
                        json.dumps(row["raw_feature"], sort_keys=True, separators=(",", ":")),
                    ))
            except (ValueError, sqlite3.Error) as exc:
                receipt["state"] = "DOWNLOADED_NOT_VALIDATED"
                receipt["error"] = str(exc)[:500]
        manifest["sample_raw"] += receipt["raw_records"]
        manifest["sample_accepted"] += receipt["accepted"]
        manifest["sample_rejected"] += receipt["rejected"]
        manifest["samples"].append(receipt)
    db.commit()
    manifest["indexed_observations"] = db.execute(
        "SELECT COUNT(*) FROM fema_source_observations").fetchone()[0]
    manifest["distinct_fema_native_keys"] = db.execute(
        "SELECT COUNT(DISTINCT source_key) FROM fema_source_observations").fetchone()[0]
    manifest["sqlite_quick_check"] = db.execute("PRAGMA quick_check").fetchone()[0]
    db.close()
    manifest["source_sample_validated"] = bool(
        metadata_ok and manifest["sample_accepted"] > 0 and
        manifest["sample_accepted"] == manifest["indexed_observations"] and
        manifest["sample_raw"] == manifest["sample_accepted"] + manifest["sample_rejected"] and
        manifest["sqlite_quick_check"] == "ok" and
        all(s["state"] == "STAGED_SAMPLE" for s in manifest["samples"])
    )
    (out_dir / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return manifest


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", default="data/lane_a/massgis_2025")
    args = p.parse_args(argv)
    m = collect(args.output_dir)
    print("LANE_A_MASSGIS_VALIDATION=" + json.dumps({
        "source_sample_validated": m["source_sample_validated"],
        "sample_raw": m["sample_raw"], "sample_accepted": m["sample_accepted"],
        "sample_rejected": m["sample_rejected"],
        "indexed_observations": m["indexed_observations"],
        "distinct_fema_native_keys": m["distinct_fema_native_keys"],
        "sample_states": [s["state"] for s in m["samples"]],
        "metadata_valid": m["metadata"].get("metadata_valid"),
        "sample_errors": [s.get("error") for s in m["samples"] if s.get("error")],
        "source_vintage": m["source_data_vintage"],
        "limited_geography": m["coverage"],
    }, sort_keys=True))
    return 0 if m["source_sample_validated"] else 2


if __name__ == "__main__":
    sys.exit(main())
