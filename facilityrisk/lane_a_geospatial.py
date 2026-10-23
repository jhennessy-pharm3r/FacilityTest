"""Lane A source-only spatial evidence query (NO canonical facility linking).

RTree narrows candidates, native FEMA polygon rings decide containment, and the
source-run manifest gates negative results. Geometry/point matches are hazard
observations, not inspected buildings, damage, insured loss or policy coverage.
"""
import json
import math
import pathlib
import sqlite3

from facilityrisk.lane_a_hazards import valid_point


def segment_boundary(x, y, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    cross = (x - ax) * dy - (y - ay) * dx
    if abs(cross) > 1e-11 * max(1.0, abs(dx), abs(dy)):
        return False
    return (min(ax, bx) - 1e-12 <= x <= max(ax, bx) + 1e-12 and
            min(ay, by) - 1e-12 <= y <= max(ay, by) + 1e-12)


def polygon_point_relation(feature, lon, lat):
    """Even-odd handling of nested Esri polygon rings. Return INSIDE/BOUNDARY/OUTSIDE."""
    rings = feature.get("geometry", {}).get("rings", [])
    if not isinstance(rings, list) or not rings:
        raise ValueError("Missing FEMA source polygon rings")
    inside = False
    for ring in rings:
        if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
            raise ValueError("Invalid FEMA polygon ring")
        crossed = False
        for (ax, ay), (bx, by) in zip(ring, ring[1:]):
            if segment_boundary(lon, lat, ax, ay, bx, by):
                return "BOUNDARY"
            if (ay > lat) != (by > lat) and lon < (bx - ax) * (lat - ay) / (by - ay) + ax:
                crossed = not crossed
        if crossed:
            inside = not inside
    return "INSIDE" if inside else "OUTSIDE"


def _within_window(lon, lat, bbox):
    left, south, right, north = bbox
    return left <= lon <= right and south <= lat <= north


def query_fema_point(index, manifest_file, *, longitude, latitude,
                     site_reference, coordinate_evidence,
                     coordinates_corroborated, max_candidates=500):
    """Query only independently evidenced coordinates; do not write site crosswalk."""
    if (not valid_point(longitude, latitude) or
            coordinates_corroborated is not True or
            not isinstance(coordinate_evidence, str) or not coordinate_evidence.strip() or
            not isinstance(site_reference, str) or not site_reference.strip()):
        raise ValueError("An independently corroborated WGS84 site coordinate and coordinate_evidence are required")
    index = pathlib.Path(index)
    manifest_file = pathlib.Path(manifest_file)
    if not index.is_file() or not manifest_file.is_file():
        raise FileNotFoundError("Verified Lane A source index and manifest required")
    m = json.loads(manifest_file.read_text(encoding="utf-8"))
    local_windows = {n: w for n, w in m.get("windows", {}).items()
                     if _within_window(longitude, latitude, w["bbox_wgs84"])}
    all_complete = bool(local_windows) and all(
        w.get("status") == "COMPLETE_WITHIN_WINDOW" for w in local_windows.values()
    ) and m.get("source_metadata") is not None
    db = sqlite3.connect("file:" + str(index.resolve()) + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        candidates = db.execute("""
            SELECT f.source_key,f.objectid,f.dfirm_id,f.fld_ar_id,
                   f.flood_zone,f.zone_subtype,f.sfha_tf,f.source_cit,f.version_id,
                   f.feature_json,f.original_reply_sha256,f.geometry_tolerance_degrees
              FROM fema_source_bounds b
              JOIN fema_source_features f ON f.rowid=b.feature_rowid
             WHERE b.min_lon<=? AND b.max_lon>=?
               AND b.min_lat<=? AND b.max_lat>=?
             ORDER BY f.source_key
             LIMIT ?
        """, (longitude, longitude, latitude, latitude, max_candidates + 1)).fetchall()
        if len(candidates) > max_candidates:
            return {
                "site_reference": site_reference, "source": "fema_nfhl",
                "coverage_state": "UNKNOWN_TOO_MANY_CANDIDATES",
                "source_features": [], "candidate_overflow": True,
                "known_complete_windows": list(local_windows),
                "hazard_not_loss": True, "site_identity_not_source_verified": True,
            }
        matches = []
        for f in candidates:
            feature = json.loads(f["feature_json"])
            relation = polygon_point_relation(feature, longitude, latitude)
            if relation == "OUTSIDE":
                continue
            tolerance = f["geometry_tolerance_degrees"]
            matches.append({
                "fema_source_key": f["source_key"], "objectid_service_scoped": f["objectid"],
                "dfirm_id": f["dfirm_id"], "fld_ar_id": f["fld_ar_id"],
                "flood_zone": f["flood_zone"], "zone_subtype": f["zone_subtype"],
                "sfha_tf": f["sfha_tf"], "source_citation": f["source_cit"],
                "version_id_not_map_effective_date": f["version_id"],
                "geometry_relation": relation,
                "geometry_precision": "GENERALIZED_REVIEW_REQUIRED" if tolerance else
                                      "SOURCE_API_GEOMETRY",
                "max_allowable_offset_degrees": tolerance,
                "original_response_sha256": f["original_reply_sha256"],
            })
    finally:
        db.close()
    if not all_complete:
        state = "UNKNOWN_INCOMPLETE_SOURCE_COVERAGE"
    elif not matches:
        state = "UNKNOWN_NO_POLYGON_AT_POINT"
    elif any(x["geometry_relation"] == "BOUNDARY" or
             x["max_allowable_offset_degrees"] > 0 for x in matches):
        state = "BOUNDARY_OR_SIMPLIFICATION_REVIEW_REQUIRED"
    else:
        state = "SOURCE_POLYGON_INTERSECTION_AT_CORROBORATED_POINT"
    return {
        "site_reference": site_reference, "source": "fema_nfhl",
        "index_scope": "bounded_QA_windows_NOT_national",
        "longitude": longitude, "latitude": latitude,
        "coordinate_evidence": coordinate_evidence,
        "site_identity_not_source_verified": True,
        "hazard_not_loss": True,
        "coverage_state": state,
        "known_complete_windows": [n for n, w in local_windows.items()
                                   if w.get("status") == "COMPLETE_WITHIN_WINDOW"],
        "incomplete_windows": [n for n, w in local_windows.items()
                               if w.get("status") != "COMPLETE_WITHIN_WINDOW"],
        "bbox_candidates": len(candidates),
        "source_features": matches,
        "map_effective_date_state": "not_validated_per_DFIRM",
        "no_policy_coverage_or_risk_score": True,
    }
