"""Lane A official geospatial hazard source sampling; no facility identity linkage."""
import argparse
import hashlib
import json
import math
import pathlib
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

FEMA = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28"
USFS = "https://apps.fs.usda.gov/arcx/rest/services/RDW_Wildfire/RMRS_WildfireHazardPotential_2023/MapServer"
SOURCES = {"fema_nfhl": FEMA, "usfs_whp_2023": USFS}


def valid_point(lon, lat):
    return all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in (lon, lat)) and -180 <= lon <= 180 and -90 <= lat <= 90


def request_json(base, path, params, opener=None):
    url = base.rstrip("/") + "/" + path.lstrip("/") + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "FacilityRisk-LaneA/1.0 (official-source-validation)", "Accept": "application/json"})
    if opener is None:
        opener = urllib.request.urlopen
    with opener(request, timeout=45) as response:
        payload = response.read()
    document = json.loads(payload)
    if not isinstance(document, dict) or document.get("error"):
        raise ValueError("Source API error or invalid JSON object: " + str(document.get("error") if isinstance(document, dict) else type(document)))
    return document, url, hashlib.sha256(payload).hexdigest(), len(payload)


def nfhl_point(lon, lat, fetch=request_json):
    if not valid_point(lon, lat):
        raise ValueError("Invalid WGS84 longitude/latitude")
    # Native ArcGIS point-in-polygon server query; do not treat absent polygons as low flood risk.
    payload, url, digest, nbytes = fetch(FEMA, "query", {
        "f": "json", "geometry": json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}),
        "geometryType": "esriGeometryPoint", "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects", "returnGeometry": "false",
        "outFields": "OBJECTID,DFIRM_ID,FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE,V_DATUM,SOURCE_CIT",
    })
    features = payload.get("features")
    if not isinstance(features, list):
        raise ValueError("FEMA response missing features list")
    if payload.get("exceededTransferLimit"):
        raise ValueError("FEMA query truncated; cannot assert complete spatial coverage")
    rows = []
    for feature in features:
        attr = feature.get("attributes") if isinstance(feature, dict) else None
        if not isinstance(attr, dict) or attr.get("OBJECTID") is None:
            raise ValueError("FEMA row missing source OBJECTID")
        rows.append({"source_id": str(attr["OBJECTID"]), "source_attributes": attr})
    if len({r["source_id"] for r in rows}) != len(rows):
        raise ValueError("Duplicate FEMA OBJECTID in query")
    return {"source": "fema_nfhl", "source_url": url, "sha256": digest, "raw_bytes": nbytes,
            "raw_count": len(features), "accepted_count": len(rows), "rejected_count": 0,
            "coverage_state": "intersections_found" if rows else "unknown_no_intersection",
            "records": rows}


def whp_point(lon, lat, fetch=request_json):
    if not valid_point(lon, lat):
        raise ValueError("Invalid WGS84 longitude/latitude")
    # Raster MapServer: Identify is supported; FeatureServer/query is NOT equivalent.
    delta = 0.05
    payload, url, digest, nbytes = fetch(USFS, "identify", {
        "f": "json", "geometry": json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}),
        "geometryType": "esriGeometryPoint", "sr": 4326, "layers": "all",
        "tolerance": 1,
        "mapExtent": ",".join(str(v) for v in (lon-delta, lat-delta, lon+delta, lat+delta)),
        "imageDisplay": "600,600,96", "returnGeometry": "false",
    })
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError("USFS identify missing results list")
    records = []
    for r in results:
        if not isinstance(r, dict) or r.get("layerId") is None:
            raise ValueError("USFS identify result missing layerId")
        records.append({"source_id": "usfs_whp_2023:layer:" + str(r["layerId"]),
                        "layer_name": r.get("layerName"), "value": r.get("value"),
                        "source_attributes": r.get("attributes", {})})
    return {"source": "usfs_whp_2023", "source_url": url, "sha256": digest,
            "raw_bytes": nbytes, "raw_count": len(results), "accepted_count": len(records),
            "rejected_count": 0, "coverage_state": "raster_values_returned" if records else "unknown_no_raster_value",
            "records": records}


def collect(points, fetch=request_json):
    observations = []
    for point in points:
        name, lon, lat = point["site_reference"], point["longitude"], point["latitude"]
        if not valid_point(lon, lat) or not point.get("coordinates_corroborated"):
            raise ValueError("Corroborated WGS84 coordinates required for " + str(name))
        for source, method in (("fema_nfhl", nfhl_point), ("usfs_whp_2023", whp_point)):
            try:
                result = method(lon, lat, fetch)
                status = "STAGED"
            except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as exc:
                result = {"source": source, "raw_count": 0, "accepted_count": 0, "rejected_count": 0,
                          "coverage_state": "unknown_source_unavailable", "error": str(exc)}
                status = "NOT_TESTED" if isinstance(exc, OSError) else "PROBED"
            observations.append({"site_reference": name, "longitude": lon, "latitude": lat,
                                 "site_identity_verified": False, "hazard_not_loss": True,
                                 "ingestion_state": status, **result})
    return {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "dataset_vintage": {"fema_nfhl": "see source DFIRM_ID / SOURCE_CIT; not globally uniform",
                                "usfs_whp_2023": "2023"},
            "observation_count": len(observations),
            "observations": observations}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lane A official-source hazard sampling")
    parser.add_argument("--points", required=True, help="JSON array: site_reference, longitude, latitude, coordinates_corroborated=true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    points = json.loads(pathlib.Path(args.points).read_text(encoding="utf-8"))
    if not isinstance(points, list) or not points:
        parser.error("At least one corroborated site coordinate required")
    report = collect(points)
    target = pathlib.Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    failures = sum(1 for r in report["observations"] if r["ingestion_state"] != "STAGED")
    print(json.dumps({"observations": report["observation_count"], "source_failures": failures, "manifest": str(target)}))
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
