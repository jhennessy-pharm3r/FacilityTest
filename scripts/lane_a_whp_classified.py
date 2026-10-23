"""USFS official WHP 2023 classified image-source geographic sampling.

Source classes 1-5 are ordinal wildfire *landscape* hazard; class 6 is
nonburnable and 7 is water. No site identification, loss or event inference.
WHP 2023 has landscape inputs dated 2020 (not current-season forecasting).
"""
import argparse
import concurrent.futures
import hashlib
import json
import pathlib
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from scripts.lane_a_whp_regions import REGIONS, grid_points

IMAGE_SERVER = ("https://imagery.geoplatform.gov/iipp/rest/services/"
                "Fire_Aviation/USFS_EDW_RMRS_WildfireHazardPotentialClassified/ImageServer")
CLASSES = {1: "Very low", 2: "Low", 3: "Moderate", 4: "High",
           5: "Very high", 6: "Non-burnable", 7: "Water"}


def fetch_json(endpoint, params):
    uri = IMAGE_SERVER + ("/" + endpoint if endpoint else "") + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(uri, headers={
        "User-Agent": "FacilityRisk-LaneA-USFS-Classified-2023/1.0",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=35) as response:
        raw = response.read(1_000_001)
        final_url = response.geturl()
    if len(raw) > 1_000_000:
        raise ValueError("USFS classified raster reply exceeds 1MB")
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("error"):
        raise ValueError("USFS classified API error " + str(data.get("error") if isinstance(data, dict) else type(data))[:450])
    return data, raw, final_url


def parse_class(data, nodata):
    value = data.get("value")
    if value is None and isinstance(data.get("properties"), dict):
        v = data["properties"].get("Values")
        value = v[0] if isinstance(v, list) and v else None
    if value is None or isinstance(value, (bool, list, dict)):
        return "NO_DATA", None, None
    try:
        numeric = float(value)
    except (ValueError, TypeError):
        if str(value).strip().lower() in ("nodata", "no data", "null", "none"):
            return "NO_DATA", None, None
        return "REJECTED_INVALID_CLASS", None, None
    if numeric in nodata:
        return "NO_DATA", None, None
    if numeric not in CLASSES:
        return "REJECTED_INVALID_CLASS", None, None
    category = int(numeric)
    state = ("BURNABLE_HAZARD_CLASS" if category <= 5 else
             "NON_BURNABLE_MASK" if category == 6 else "WATER_MASK")
    return state, category, CLASSES[category]


def run(output, fetch=fetch_json, regions=REGIONS, workers=3):
    output = pathlib.Path(output)
    rawdir = output / "raw"
    rawdir.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(output / "whp-classified-source-only.sqlite")
    db.executescript("""
      CREATE TABLE IF NOT EXISTS usfs_whp_classified_probes(
        observation_key TEXT PRIMARY KEY, region TEXT NOT NULL, probe_index INTEGER NOT NULL,
        longitude REAL NOT NULL, latitude REAL NOT NULL, raster_release TEXT NOT NULL,
        source_url TEXT NOT NULL, class_state TEXT NOT NULL, class_value INTEGER,
        class_label TEXT, raw_sha256 TEXT NOT NULL, raw_json TEXT NOT NULL,
        native_pixel_id TEXT,
        CHECK(native_pixel_id IS NULL)
      );
      CREATE INDEX IF NOT EXISTS whp_classified_region ON usfs_whp_classified_probes(region,class_value);
    """)
    m = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_id": "USFS_WHP2023_CLASSIFIED",
        "publisher": "USDA Forest Service, Rocky Mountain Research Station",
        "image_service": IMAGE_SERVER,
        "source_product_release": "WHP 2023, amended 2024-07-17",
        "landscape_input_year": 2020,
        "publisher_use_statement": "USDA Research Data Archive: usable without additional permissions or fees; cite Dillon 2023, updated July 17 2024, DOI 10.2737/RDS-2015-0047-4",
        "source_disclaimer": "Modeled landscape hazard, not individual property wildfire probability; confirm service-level redistribution terms before deployment",
        "data_gov_metadata": "https://catalog.data.gov/dataset/wildfire-hazard-potential-classified-image-service",
        "official_methodology": "https://research.fs.usda.gov/firelab/products/dataandtools/wildfire-hazard-potential",
        "class_meanings": {str(k): v for k, v in CLASSES.items()},
        "class_are_ordinal_not_probabilities": True,
        "nonburnable_and_water_not_zero_risk": True,
        "spatial_scope": "14-region geographic QA sampling; NOT national raster census or verified physical facility locations",
        "actual_site_matches": 0, "production_deployed": 0, "national_raster_complete": False,
        "requested_regions": len(regions),
        "requested_points": sum(1 for _ in grid_points(regions)),
        "received": 0, "burnable_classes": 0, "special_mask_classes": 0,
        "nodata": 0, "rejected": 0, "source_failures": 0,
        "class_distribution": {}, "records": [], "metadata": None,
        "sample_complete": False, "all_counts_reconciled": False,
    }
    try:
        metadata, raw, url = fetch("", {"f": "json"})
        if not metadata.get("name") or metadata.get("pixelSizeX") is None:
            raise ValueError("Official classified ImageServer metadata missing raster schema")
        name = "metadata.json"
        (rawdir / name).write_bytes(raw)
        m["metadata"] = {
            "source_url": url, "raw_file": name, "raw_sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw), "pixelType": metadata.get("pixelType"),
            "pixelSizeX": metadata.get("pixelSizeX"),
            "pixelSizeY": metadata.get("pixelSizeY"),
            "noDataValues": metadata.get("noDataValues", []),
            "minValues": metadata.get("minValues", []),
            "maxValues": metadata.get("maxValues", []),
            "extent": metadata.get("extent"),
            "name": metadata.get("name"),
        }
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
        m["metadata_error"] = str(exc)[:500]
    if not m["metadata"]:
        db.close()
        (output / "manifest.json").write_text(json.dumps(m, indent=2, sort_keys=True) + "\n")
        return m

    nodata = set(m["metadata"]["noDataValues"])
    def read_point(point):
        region, i, lon, lat = point
        p = {
            "f": "json", "geometryType": "esriGeometryPoint",
            "geometry": json.dumps({"x": lon, "y": lat,
                                    "spatialReference": {"wkid": 4326}}, separators=(",", ":")),
            "returnGeometry": "false", "returnCatalogItems": "false",
        }
        try:
            return point, fetch("identify", p), None
        except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
            return point, None, str(exc)[:500]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for point, result, error in pool.map(read_point, grid_points(regions)):
            region, i, lon, lat = point
            entry = {"region": region, "probe_index": i, "longitude": lon,
                     "latitude": lat, "native_pixel_id": None}
            if error:
                entry.update({"state": "SOURCE_UNAVAILABLE", "error": error})
                m["source_failures"] += 1
            else:
                payload, raw, url = result
                filename = region + "." + str(i) + ".json"
                (rawdir / filename).write_bytes(raw)
                sha = hashlib.sha256(raw).hexdigest()
                state, code, label = parse_class(payload, nodata)
                entry.update({"state": state, "class_value": code, "class_label": label,
                              "raw_file": filename, "raw_sha256": sha,
                              "source_url": url, "bytes": len(raw)})
                m["received"] += 1
                if state == "NO_DATA":
                    m["nodata"] += 1
                elif state == "REJECTED_INVALID_CLASS":
                    m["rejected"] += 1
                elif state in ("NON_BURNABLE_MASK", "WATER_MASK"):
                    m["special_mask_classes"] += 1
                else:
                    m["burnable_classes"] += 1
                if state != "REJECTED_INVALID_CLASS":
                    key = "WHP2023_CLASSIFIED:" + region + ":" + str(i)
                    db.execute("INSERT INTO usfs_whp_classified_probes VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (key, region, i, lon, lat, "2023", url, state, code,
                         label, sha, json.dumps(payload, sort_keys=True), None))
                m["class_distribution"][label or state] = m["class_distribution"].get(label or state, 0) + 1
            m["records"].append(entry)
    db.commit()
    m["indexed_observations"] = db.execute(
        "SELECT COUNT(*) FROM usfs_whp_classified_probes").fetchone()[0]
    m["distinct_geographic_regions"] = db.execute(
        "SELECT COUNT(DISTINCT region) FROM usfs_whp_classified_probes").fetchone()[0]
    m["sqlite_quick_check"] = db.execute("PRAGMA quick_check").fetchone()[0]
    db.close()
    m["all_counts_reconciled"] = (
        m["requested_points"] == len(m["records"]) == m["received"] + m["source_failures"] and
        m["received"] == m["burnable_classes"] + m["special_mask_classes"] + m["nodata"] + m["rejected"] and
        m["indexed_observations"] == m["received"] - m["rejected"] and
        sum(m["class_distribution"].values()) == m["received"] and
        m["sqlite_quick_check"] == "ok"
    )
    m["sample_complete"] = (
        m["all_counts_reconciled"] and m["source_failures"] == 0 and
        m["rejected"] == 0 and m["burnable_classes"] > 0
    )
    (output / "manifest.json").write_text(json.dumps(m, indent=2, sort_keys=True) + "\n")
    return m


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default="data/lane_a/whp_classified")
    args = p.parse_args(argv)
    m = run(args.out_dir)
    print("LANE_A_WHP_CLASSIFIED=" + json.dumps({
        "sample_complete": m.get("sample_complete", False),
        "requested": m["requested_points"], "received": m["received"],
        "burnable": m["burnable_classes"], "masks": m["special_mask_classes"],
        "nodata": m["nodata"], "rejected": m["rejected"], "failures": m["source_failures"],
        "indexed": m.get("indexed_observations"), "distribution": m["class_distribution"],
        "metadata_error": m.get("metadata_error"),
    }, sort_keys=True))
    return 0 if m.get("sample_complete", False) else 2


if __name__ == "__main__":
    sys.exit(main())
