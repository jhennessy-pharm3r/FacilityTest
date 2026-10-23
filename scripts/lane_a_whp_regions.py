"""Multi-region real USDA Wildfire Hazard Potential 2023 ImageServer evidence.

Bounded independent geographic probes only: NOT facility/site matches, national
raster census, active incidents, physical damages, or underwriter risk scores.
"""
import argparse
import concurrent.futures
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

USFS = ("https://imagery.geoplatform.gov/iipp/rest/services/"
        "Fire_Aviation/USFS_EDW_RMRS_WildfireHazardPotentialContinuous/ImageServer")
# Region centroids sampled on a 5-point grid; never classify as insured sites.
REGIONS = {
    "pnw": (-121.3, 46.3),
    "norcal": (-122.0, 39.5),
    "socal": (-118.1, 34.2),
    "rockies": (-106.8, 40.2),
    "southwest": (-111.4, 33.8),
    "plains": (-99.5, 39.2),
    "texas": (-97.3, 31.2),
    "gulf": (-89.2, 30.4),
    "southeast": (-83.2, 34.1),
    "great_lakes": (-88.2, 43.2),
    "mid_atlantic": (-78.1, 37.6),
    "northeast": (-72.0, 42.0),
    "alaska": (-150.1, 61.4),
    "hawaii": (-155.8, 19.6),
}
OFFSETS = ((0.0, 0.0), (-0.07, -0.05), (-0.07, 0.05),
           (0.07, -0.05), (0.07, 0.05))


def fetch_json(path, params, *, timeout=30, attempts=2):
    url = USFS.rstrip("/") + "/" + path + "?" + urllib.parse.urlencode(params)
    err = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "FacilityRisk-LaneA-USFS-2023-Grid/1.0",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = response.read(1_000_001)
                final_url = response.geturl()
            if len(data) > 1_000_000:
                raise ValueError("ImageServer identify response exceeded 1MB limit")
            doc = json.loads(data)
            if not isinstance(doc, dict) or doc.get("error"):
                raise ValueError("ArcGIS ImageServer error: " + str(doc.get("error") if isinstance(doc, dict) else type(doc)))
            return doc, data, final_url
        except (OSError, ValueError, TimeoutError, json.JSONDecodeError) as exc:
            err = exc
            if attempt == attempts - 1:
                break
    raise RuntimeError("Official USDA ImageServer unavailable: " + str(err)[:450])


def interpret_pixel(doc, no_data_values, *, lo=None, hi=None):
    val = doc.get("value")
    if val is None and isinstance(doc.get("properties"), dict):
        props = doc["properties"].get("Values")
        val = props[0] if isinstance(props, list) and props else None
    if val is None or isinstance(val, bool) or isinstance(val, (dict, list)):
        return "NO_DATA", None
    try:
        numeric = float(val)
    except (ValueError, TypeError):
        if isinstance(val, str) and val.casefold() in ("nodata", "null", "none"):
            return "NO_DATA", None
        return "INVALID_PIXEL", None
    if not math.isfinite(numeric):
        return "INVALID_PIXEL", None
    if numeric in no_data_values:
        return "NO_DATA", None
    if lo is not None and numeric < lo or hi is not None and numeric > hi:
        return "INVALID_PIXEL", None
    return "VALUE", numeric


def grid_points(regions=REGIONS):
    for name, (lon, lat) in regions.items():
        for k, (dx, dy) in enumerate(OFFSETS):
            x, y = round(lon + dx, 6), round(lat + dy, 6)
            if not (-180 <= x <= 180 and -90 <= y <= 90):
                raise ValueError("Invalid geographic QA point")
            yield name, k, x, y


def init_index(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS whp_geographic_probes (
          observation_key TEXT PRIMARY KEY, region TEXT NOT NULL,
          probe_index INTEGER NOT NULL, longitude REAL NOT NULL, latitude REAL NOT NULL,
          whp_release TEXT NOT NULL, source_url TEXT NOT NULL,
          pixel_state TEXT NOT NULL, pixel_value REAL,
          raw_sha256 TEXT NOT NULL, raw_json TEXT NOT NULL,
          native_pixel_id TEXT,
          CHECK (native_pixel_id IS NULL)
        );
        CREATE INDEX IF NOT EXISTS whp_region_idx ON whp_geographic_probes(region,pixel_state);
    """)
    return db


def run(outdir, fetch=fetch_json, regions=REGIONS, *, workers=3):
    outdir = pathlib.Path(outdir)
    rawdir = outdir / "raw"
    rawdir.mkdir(parents=True, exist_ok=True)
    db = init_index(outdir / "whp-regional-source-only.sqlite")
    m = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "official_source_url": USFS, "publisher": "USDA Forest Service",
        "product": "WHP continuous 2023 270m", "citation_revision": "2024-07-17",
        "landscape_inputs_as_of": "2020", "data_type": "relative_fire_hazard_model_not_event_or_loss",
        "national_raster_complete": False, "site_matches": 0, "production_deployed": 0,
        "region_count": len(regions), "requested_points": len(regions) * len(OFFSETS),
        "downloaded_replies": 0, "accepted_numeric_pixels": 0,
        "no_data_pixels": 0, "rejected_pixels": 0,
        "source_failures": 0, "observations": [], "regions": {},
    }
    meta = None
    try:
        metadata, raw, url = fetch("", {"f": "json"})
        (rawdir / "usfs.image_service.json").write_bytes(raw)
        meta = {
            "url": url, "raw_file": "usfs.image_service.json",
            "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
            "name": metadata.get("name"),
            "pixel_type": metadata.get("pixelType"),
            "resolution": [metadata.get("pixelSizeX"), metadata.get("pixelSizeY")],
            "no_data_values": metadata.get("noDataValues", []),
            "min_values": metadata.get("minValues", []),
            "max_values": metadata.get("maxValues", []),
            "extent": metadata.get("extent"),
        }
        if not meta["name"] or meta["pixel_type"] is None:
            raise ValueError("Official USFS raster schema incomplete")
    except (RuntimeError, ValueError, OSError) as exc:
        m["metadata_error"] = str(exc)
    m["metadata"] = meta
    if not meta:
        (outdir / "manifest.json").write_text(json.dumps(m, sort_keys=True, indent=2) + "\n")
        db.close()
        return m

    def query_point(item):
        region, index, lon, lat = item
        geom = {"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}
        params = {"f": "json", "geometryType": "esriGeometryPoint",
                  "geometry": json.dumps(geom, separators=(",", ":")),
                  "returnGeometry": "false", "returnCatalogItems": "false"}
        try:
            return item, fetch("identify", params), None
        except (RuntimeError, ValueError, OSError) as exc:
            return item, None, str(exc)[:500]

    all_points = list(grid_points(regions))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for point, result, error in pool.map(query_point, all_points):
            region, index, lon, lat = point
            entry = {"region": region, "grid_index": index,
                     "longitude": lon, "latitude": lat,
                     "source_native_pixel_id": None}
            if error:
                entry.update({"state": "SOURCE_UNAVAILABLE", "error": error})
                m["source_failures"] += 1
            else:
                doc, raw, url = result
                filename = region + "." + str(index) + ".json"
                (rawdir / filename).write_bytes(raw)
                digest = hashlib.sha256(raw).hexdigest()
                entry.update({"state": "DOWNLOADED", "raw_file": filename,
                              "raw_sha256": digest, "bytes": len(raw),
                              "source_url": url})
                m["downloaded_replies"] += 1
                nodata = set(meta["no_data_values"])
                minval = meta["min_values"][0] if meta["min_values"] else None
                maxval = meta["max_values"][0] if meta["max_values"] else None
                state, value = interpret_pixel(doc, nodata, lo=minval, hi=maxval)
                entry["pixel_state"] = state
                entry["pixel_value"] = value
                if state == "INVALID_PIXEL":
                    m["rejected_pixels"] += 1
                else:
                    if state == "NO_DATA":
                        m["no_data_pixels"] += 1
                    else:
                        m["accepted_numeric_pixels"] += 1
                    key = "usfs_whp_2023_geographic_probe:" + region + ":" + str(index)
                    db.execute("INSERT INTO whp_geographic_probes VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (key, region, index, lon, lat, "2023", url, state, value,
                         digest, json.dumps(doc, sort_keys=True), None))
                    entry["observation_key_not_native_id"] = key
            m["observations"].append(entry)
            area = m["regions"].setdefault(region, {"requested": 0,
                    "numeric": 0, "no_data": 0, "invalid": 0, "unavailable": 0})
            area["requested"] += 1
            bucket = ("numeric" if entry.get("pixel_state") == "VALUE"
                      else "no_data" if entry.get("pixel_state") == "NO_DATA"
                      else "invalid" if entry.get("pixel_state") == "INVALID_PIXEL"
                      else "unavailable")
            area[bucket] += 1
    db.commit()
    m["indexed_point_observations"] = db.execute(
        "SELECT COUNT(*) FROM whp_geographic_probes").fetchone()[0]
    m["distinct_region_count"] = db.execute(
        "SELECT COUNT(DISTINCT region) FROM whp_geographic_probes").fetchone()[0]
    m["actual_pixel_value_range"] = list(db.execute(
        "SELECT MIN(pixel_value),MAX(pixel_value) FROM whp_geographic_probes WHERE pixel_state='VALUE'").fetchone())
    m["sqlite_quick_check"] = db.execute("PRAGMA quick_check").fetchone()[0]
    db.close()
    m["sample_reconciled"] = (
        m["requested_points"] == len(m["observations"]) ==
        m["downloaded_replies"] + m["source_failures"] and
        m["downloaded_replies"] == m["accepted_numeric_pixels"] +
        m["no_data_pixels"] + m["rejected_pixels"] and
        m["indexed_point_observations"] == m["accepted_numeric_pixels"] +
        m["no_data_pixels"] and m["sqlite_quick_check"] == "ok"
    )
    m["complete_geographic_probe_set"] = (
        m["sample_reconciled"] and m["source_failures"] == 0 and
        m["rejected_pixels"] == 0 and m["accepted_numeric_pixels"] > 0
    )
    (outdir / "manifest.json").write_text(json.dumps(m, sort_keys=True, indent=2) + "\n")
    return m


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default="data/lane_a/whp_regions")
    args = p.parse_args(argv)
    m = run(args.out_dir)
    print("LANE_A_WHP_REGIONS=" + json.dumps({
        "complete_geographic_probe_set": m.get("complete_geographic_probe_set", False),
        "requested": m["requested_points"], "downloaded": m["downloaded_replies"],
        "numeric_values": m["accepted_numeric_pixels"],
        "nodata": m["no_data_pixels"], "rejected": m["rejected_pixels"],
        "source_failures": m["source_failures"],
        "indexed": m.get("indexed_point_observations"), "regions": m["regions"],
        "value_range": m.get("actual_pixel_value_range"),
    }, sort_keys=True))
    return 0 if m.get("complete_geographic_probe_set", False) else 2


if __name__ == "__main__":
    sys.exit(main())
