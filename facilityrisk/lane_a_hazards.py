"""Lane A official flood polygons + USDA WHP 2023 raster point sampling.

This module is for independently corroborated WGS84 site coordinates ONLY.
A source hazard observation is never automatically a verified insured property.
"""
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
USFS = "https://imagery.geoplatform.gov/iipp/rest/services/Fire_Aviation/USFS_EDW_RMRS_WildfireHazardPotentialContinuous/ImageServer"
SOURCES = {"fema_nfhl": FEMA, "usfs_whp_continuous_2023": USFS}


def valid_point(lon, lat):
    return (
        all(isinstance(x, (int, float)) and not isinstance(x, bool)
            and math.isfinite(x) for x in (lon, lat))
        and -180 <= lon <= 180 and -90 <= lat <= 90
    )


def request_json(base, path, params, opener=None):
    url = base.rstrip("/") + "/" + path.lstrip("/") + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={
        "User-Agent": "FacilityRisk-LaneA/1.1",
        "Accept": "application/json",
    })
    if opener is None:
        opener = urllib.request.urlopen
    with opener(request, timeout=45) as response:
        raw = response.read(10_000_001)
        if len(raw) > 10_000_000:
            raise ValueError("Source response exceeds 10MB safety limit")
    document = json.loads(raw)
    if not isinstance(document, dict) or document.get("error"):
        raise ValueError("Source API error or invalid JSON object: "
                         + str(document.get("error") if isinstance(document, dict) else type(document)))
    return document, url, hashlib.sha256(raw).hexdigest(), len(raw)


def nfhl_point(lon, lat, fetch=request_json):
    if not valid_point(lon, lat):
        raise ValueError("Invalid WGS84 longitude/latitude")
    # Native ArcGIS point-in-polygon server query; no polygons != low risk.
    payload, url, digest, nbytes = fetch(FEMA, "query", {
        "f": "json",
        "geometry": json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}),
        "geometryType": "esriGeometryPoint", "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "returnGeometry": "false",
        "outFields": "OBJECTID,DFIRM_ID,VERSION_ID,FLD_AR_ID,FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE,V_DATUM,SOURCE_CIT",
    })
    features = payload.get("features")
    if not isinstance(features, list):
        raise ValueError("FEMA response missing features list")
    if payload.get("exceededTransferLimit"):
        raise ValueError("FEMA query truncated; cannot assert complete spatial coverage")
    rows, keys = [], set()
    for feature in features:
        attr = feature.get("attributes") if isinstance(feature, dict) else None
        if not isinstance(attr, dict):
            raise ValueError("FEMA record missing source attributes")
        oid, dfirm, fld_ar = (attr.get("OBJECTID"), attr.get("DFIRM_ID"), attr.get("FLD_AR_ID"))
        if oid is None and not (dfirm and fld_ar):
            raise ValueError("FEMA record missing source identifier")
        # Keep native DFIRM/FLD_AR and OBJECTID; never label as facility ID.
        key = ("dfirm:" + str(dfirm) + ":fld_ar:" + str(fld_ar)
               if dfirm and fld_ar else "service_objectid:" + str(oid))
        if key in keys:
            raise ValueError("Duplicate FEMA source key in query")
        keys.add(key)
        rows.append({"source_key": key, "source_objectid": oid,
                     "source_attributes": attr})
    return {
        "source": "fema_nfhl", "source_url": url, "sha256": digest,
        "raw_bytes": nbytes, "raw_count": len(features),
        "accepted_count": len(rows), "rejected_count": 0,
        "coverage_state": "intersections_found" if rows else "unknown_no_intersection",
        "records": rows,
    }


def whp_point(lon, lat, fetch=request_json):
    if not valid_point(lon, lat):
        raise ValueError("Invalid WGS84 longitude/latitude")
    # USDA WHP is a 270m modeled continuous raster, NOT an incident feature layer.
    payload, url, digest, nbytes = fetch(USFS, "identify", {
        "f": "json",
        "geometry": json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}),
        "geometryType": "esriGeometryPoint",
        "returnGeometry": "false", "returnCatalogItems": "false",
    })
    raw_value = payload.get("value")
    if raw_value is None and isinstance(payload.get("properties"), dict):
        vals = payload["properties"].get("Values")
        raw_value = vals[0] if isinstance(vals, list) and vals else None
    try:
        value = None if raw_value is None or isinstance(raw_value, (list, dict, bool)) else float(raw_value)
        if value is not None and (not math.isfinite(value) or value < 0):
            value = None
    except (TypeError, ValueError):
        value = None
    # No source-native pixel identifier is supplied. A point observation key is
    # derived only for local reproducibility, not presented as a USFS feature ID.
    records = ([{
        "observation_key": "usfs_whp_2023_point:" + format(lon, ".7f") + "," + format(lat, ".7f"),
        "source_native_feature_id": None,
        "pixel_value": value,
        "raster_release": "2023",
        "resolution_m": 270,
        "source_attributes": payload,
    }] if value is not None else [])
    return {
        "source": "usfs_whp_continuous_2023", "source_url": url,
        "sha256": digest, "raw_bytes": nbytes,
        "raw_count": 1, "accepted_count": len(records),
        "rejected_count": 1 - len(records),
        "coverage_state": "raster_value_returned" if records else "unknown_no_raster_value",
        "records": records,
    }


def collect(points, fetch=request_json):
    observations = []
    for point in points:
        name = point["site_reference"]
        lon, lat = point["longitude"], point["latitude"]
        if (not isinstance(name, str) or not name.strip() or
                not valid_point(lon, lat) or
                point.get("coordinates_corroborated") is not True or
                not isinstance(point.get("coordinate_evidence"), str) or
                not point["coordinate_evidence"].strip()):
            raise ValueError("Corroborated WGS84 coordinates and explicit coordinate_evidence required")
        for source, method in (("fema_nfhl", nfhl_point),
                               ("usfs_whp_continuous_2023", whp_point)):
            try:
                result = method(lon, lat, fetch)
                state = "STAGED_POINT_SAMPLE"
            except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as exc:
                result = {
                    "source": source, "source_service": SOURCES[source],
                    "raw_count": None, "accepted_count": None, "rejected_count": None,
                    "coverage_state": "unknown_source_unavailable",
                    "error_type": type(exc).__name__, "error": str(exc)[:500],
                }
                state = "PROBED"
            observations.append({
                "site_reference": name, "longitude": lon, "latitude": lat,
                "coordinate_evidence": point["coordinate_evidence"],
                "site_identity_verified_by_source": False,
                "hazard_not_loss": True, "ingestion_state": state,
                **result,
            })
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "corroborated_site_point_samples_not_full_source_census",
        "dataset_vintage": {
            "fema_nfhl": "varies_by_DFIRM_and_revision",
            "usfs_whp_continuous_2023": "2023",
        },
        "observation_count": len(observations), "observations": observations,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Lane A official-source point samples")
    parser.add_argument("--points", required=True,
                        help="JSON array: site_reference, longitude, latitude, coordinates_corroborated=true, coordinate_evidence")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    points = json.loads(pathlib.Path(args.points).read_text(encoding="utf-8"))
    if not isinstance(points, list) or not points:
        parser.error("At least one corroborated coordinate is required")
    report = collect(points)
    target = pathlib.Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    failures = sum(o["ingestion_state"] != "STAGED_POINT_SAMPLE" for o in report["observations"])
    print(json.dumps({"observations": report["observation_count"],
                      "source_failures": failures, "manifest": str(target)}))
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
