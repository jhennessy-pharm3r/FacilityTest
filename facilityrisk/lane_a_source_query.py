"""Lane A read-only evidence queries over the isolated government source indexes.

These source keys describe FEMA flood polygons or USDA geographic aggregates;
they are NEVER independently identified insured properties, loss outcomes, or
client-visible production records. Coordinator Lane E controls deployment.
"""
import json
import pathlib
import sqlite3

WHP_GEOGRAPHY_TYPES = frozenset(("county", "state", "zip"))
WHP_MANAGEMENT_TYPE = "management_jurisdiction"


def _readonly_db(path):
    path = pathlib.Path(path)
    if not path.is_file():
        raise FileNotFoundError("Lane A source-only index does not exist: " + str(path))
    db = sqlite3.connect("file:" + str(path.resolve()) + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def source_whp_record(index_path, source_geography_type, native_source_id):
    """Exact USDA publisher geographic ID, retaining leading zeros and source grain."""
    if (source_geography_type not in WHP_GEOGRAPHY_TYPES and
            source_geography_type != WHP_MANAGEMENT_TYPE):
        raise ValueError("Unrecognized USDA WHP source-identity grain")
    if not isinstance(native_source_id, str) or not native_source_id.strip():
        raise ValueError("Native USDA geographic identifier must be a nonempty string")
    if source_geography_type in WHP_GEOGRAPHY_TYPES:
        length = 2 if source_geography_type == "state" else 5
        if len(native_source_id) != length or not native_source_id.isdigit():
            raise ValueError("Native geographic ID must retain publisher FIPS/ZIP characters")
    else:
        if native_source_id != native_source_id.strip() or len(native_source_id) > 200:
            raise ValueError("Invalid source-native management category label")
    db = _readonly_db(index_path)
    try:
        if source_geography_type == WHP_MANAGEMENT_TYPE:
            row = db.execute(
                "SELECT raw_row_json,source_workbook_sha256,source_zip_sha256 "
                "FROM whp2023_management WHERE source_label=?",
                (native_source_id,)
            ).fetchone()
        else:
            row = db.execute(
                "SELECT raw_row_json,source_workbook_sha256,source_zip_sha256 "
                "FROM whp2023_geography WHERE geography_type=? AND native_geographic_id=?",
                (source_geography_type, native_source_id)
            ).fetchone()
    finally:
        db.close()
    if row is None:
        return {
            "source": "usda_fs_whp2023_official_summary",
            "source_grain": source_geography_type,
            "native_source_id": native_source_id,
            "state": "NOT_IN_STAGED_SOURCE_INDEX",
            "risk_assessment": "UNKNOWN",
            "physical_site_verified": False, "app_deployed": False,
        }
    result = json.loads(row["raw_row_json"])
    if (result["original_xlsx_sha256"] != row["source_workbook_sha256"] or
            result["original_archive_sha256"] != row["source_zip_sha256"]):
        raise ValueError("Staged USDA source row provenance mismatch")
    result["source_id"] = "usda_fs_whp2023_official_summary"
    result["query_record_status"] = "STAGED_SOURCE_AGGREGATE"
    result["risk_assessment"] = "NOT_INSURED_PROPERTY_RISK_SCORE"
    result["physical_site_verified"] = False
    result["app_deployed"] = False
    return result


def source_fema_polygon(index_path, source_key):
    """Read exact native FEMA DFIRM/flood-area key; do not return huge geometry inline."""
    if (not isinstance(source_key, str) or not source_key or
            len(source_key) > 250 or "\n" in source_key):
        raise ValueError("Invalid FEMA source identity")
    db = _readonly_db(index_path)
    try:
        row = db.execute(
            "SELECT source_key,objectid,dfirm_id,fld_ar_id,flood_zone,zone_subtype,"
            "sfha_tf,source_cit,version_id,original_reply_sha256,"
            "geometry_tolerance_degrees, LENGTH(feature_json) as serialized_bytes "
            "FROM fema_source_features WHERE source_key=?",
            (source_key,)
        ).fetchone()
    finally:
        db.close()
    if row is None:
        return {
            "source": "fema_nfhl_s_fld_haz_ar",
            "source_key": source_key, "state": "NOT_IN_STAGED_WINDOW_INDEX",
            "coverage_is_national": False,
            "risk_assessment": "UNKNOWN", "physical_site_verified": False,
            "app_deployed": False,
        }
    result = dict(row)
    result.update({
        "source": "fema_nfhl_s_fld_haz_ar",
        "source_native_key_not_site_id": True,
        "source_polygon_geometry_indexed": True,
        "geometry_precision": ("GENERALIZED_REVIEW_REQUIRED" if
                               row["geometry_tolerance_degrees"] else "SOURCE_API_GEOMETRY"),
        "map_effective_date": None, "effective_date_verified": False,
        "source_response_sha256": row["original_reply_sha256"],
        "coverage_is_national": False,
        "physical_site_verified": False,
        "app_deployed": False,
        "risk_assessment": "NOT_SITE_EXPOSURE_OR_INSURANCE_LOSS",
    })
    return result
