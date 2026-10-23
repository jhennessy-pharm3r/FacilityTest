"""Validated Lane A government-source index status and authenticated query adapter.

The only supported serving mode is an operator-mounted, previously verified,
immutable Lane A release. Geographic publisher aggregates and 70 sampled pixels
are NOT property risk scores, losses or proof of nationwide raster coverage.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3

from .db import get_db_path
from .intelligence import is_reviewed_site_coordinate
from .lane_a_installed import (
    INDEX_PATHS, installed_release, query_publisher_id,
    query_raster_probe, query_reviewed_coordinate,
)

ROOT_ENV = "FACILITY_RISK_LANE_A_INDEX_ROOT"
REQUIRED = frozenset(INDEX_PATHS)
NATIVE_PART = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")
PRIVATE_TABLES = frozenset((
    "facilities", "evidence", "raw_snapshots", "audit_events",
    "insurance_policies", "insurance_terms", "facility_assets",
    "sec_findings", "review_approvals",
))
TABLES = {
    "fema_nfhl": ("fema_source_features",),
    "usda_summary": ("whp2023_geography", "whp2023_management"),
    "usda_continuous": ("whp_geographic_probes",),
    "usda_classified": ("usfs_whp_classified_probes",),
}


class LaneASourceUnavailable(ValueError):
    """The required signed-off release is absent or failed content validation."""


def _sha256(path):
    hasher = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _configured_root():
    configured = os.environ.get(ROOT_ENV, "").strip()
    if not configured:
        raise LaneASourceUnavailable("Lane A source index not configured")
    root = Path(configured).expanduser()
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise LaneASourceUnavailable("Lane A root must be an existing absolute non-symlinked directory")
    if root.resolve() == get_db_path().resolve():
        raise LaneASourceUnavailable("Source index cannot be the private research workspace")
    return root.resolve()


def _fingerprint(root, source_root):
    """Invalidate cached official-source QA on *any* input change or symlink."""
    proof = source_root.parents[1] / "release-verification.json"
    try:
        evidence = json.loads(proof.read_text(encoding="utf-8"))
        receipts = evidence.get("retained_source_file_sha256")
        if not isinstance(receipts, dict) or not receipts:
            raise LaneASourceUnavailable("Original source-file receipt list missing")
        paths = [root / "current.json", proof]
        for relative in sorted(receipts):
            if not isinstance(relative, str):
                raise LaneASourceUnavailable("Invalid original source receipt path")
            components = PurePosixPath(relative)
            if (components.is_absolute() or
                    ".." in components.parts or
                    len(components.parts) < 2):
                raise LaneASourceUnavailable("Unsafe source receipt path")
            paths.append(source_root.joinpath(*components.parts))
        signature = []
        for path in paths:
            if path.is_symlink() or not path.is_file():
                raise LaneASourceUnavailable("Missing or symlinked original source file")
            resolved = path.resolve()
            if path not in (root / "current.json", proof) and not resolved.is_relative_to(source_root):
                raise LaneASourceUnavailable("Publisher source file escapes verified release")
            st = path.stat()
            signature.append((str(resolved), st.st_size, st.st_mtime_ns,
                              st.st_ctime_ns, st.st_dev, st.st_ino))
        return tuple(signature)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise LaneASourceUnavailable("Missing or unreadable source validation files") from exc


@lru_cache(maxsize=8)
def _validate_release(root_text, release_id, fingerprints):
    root = Path(root_text)
    source_root, pointer = installed_release(root)
    if pointer["release_id"] != release_id:
        raise LaneASourceUnavailable("Source release changed during validation")
    proof_file = source_root.parents[1] / "release-verification.json"
    if not proof_file.is_file() or proof_file.is_symlink():
        raise LaneASourceUnavailable("Original immutable release-verification receipt missing")
    evidence = json.loads(proof_file.read_text(encoding="utf-8"))
    rows = pointer.get("verified_source_only_rows")
    details = evidence.get("source_only_indexes")
    if (evidence.get("release_id") != release_id or
            evidence.get("read_only_verified") is not True or
            evidence.get("status") != "VALIDATED_LOCAL_INSTALL_READY_NOT_DEPLOYED" or
            evidence.get("physical_site_matches") != 0 or
            evidence.get("app_deployed") is not False or
            not isinstance(rows, dict) or
            set(rows) != REQUIRED or
            not isinstance(details, dict) or set(details) != REQUIRED or
            any(type(v) is not int or v <= 0 or
                details[k].get("rows") != v for k, v in rows.items())):
        raise LaneASourceUnavailable("Source release metadata or counts invalid")
    receipts = evidence.get("retained_source_file_sha256")
    if (not isinstance(receipts, dict) or
            len(receipts) != evidence.get("source_file_count") or
            len(receipts) < 8):
        raise LaneASourceUnavailable("Missing original publisher source-file receipts")
    serialized = json.dumps(receipts, sort_keys=True, separators=(",", ":")).encode()
    if hashlib.sha256(serialized).hexdigest() != evidence.get("release_content_sha256"):
        raise LaneASourceUnavailable("Installed release content-address mismatch")
    # Cold-start verification of every official source file; cached only for an
    # unchanged, immutable mounted snapshot. Do not rely on file names alone.
    for rel, receipt in receipts.items():
        parts = PurePosixPath(rel)
        if (parts.is_absolute() or ".." in parts.parts or
                len(parts.parts) < 2 or not isinstance(receipt, dict)):
            raise LaneASourceUnavailable("Unsafe installed publisher-source receipt")
        path = source_root.joinpath(*parts.parts)
        if (not path.is_file() or path.is_symlink() or
                not path.resolve().is_relative_to(source_root.resolve()) or
                receipt.get("bytes") != path.stat().st_size or
                receipt.get("sha256") != _sha256(path)):
            raise LaneASourceUnavailable("Installed source file differs from original SHA-256")
    output = {}
    for name in sorted(REQUIRED):
        path = source_root / INDEX_PATHS[name]
        if path.is_symlink() or not path.is_file():
            raise LaneASourceUnavailable("Source-only SQLite missing")
        wal = Path(str(path) + "-wal")
        if wal.is_file() and wal.stat().st_size > 0:
            raise LaneASourceUnavailable("Uncheckpointed SQLite WAL on read-only source")
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1",
                             uri=True, timeout=10) as db:
            db.execute("PRAGMA query_only=ON")
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise LaneASourceUnavailable("SQLite source integrity failed")
            present = {x[0] for x in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if set(TABLES[name]) - present or present.intersection(PRIVATE_TABLES):
                raise LaneASourceUnavailable("Source index schema/private-table guard failed")
            count = sum(db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                        for table in TABLES[name])
            if count != rows[name]:
                raise LaneASourceUnavailable("Installed native source count mismatch")
            if name == "fema_nfhl":
                if db.execute("SELECT COUNT(*) FROM fema_source_bounds").fetchone()[0] != count:
                    raise LaneASourceUnavailable("FEMA RTree/native-feature count mismatch")
                if db.execute("SELECT COUNT(DISTINCT source_key) FROM fema_source_features").fetchone()[0] != count:
                    raise LaneASourceUnavailable("FEMA source-key duplication")
            if name == "usda_summary":
                unknown = db.execute(
                    "SELECT COUNT(*) FROM whp2023_geography WHERE coverage_state='UNKNOWN_NO_AREA_VALUES'"
                ).fetchone()[0]
                if unknown != details[name].get("missing_whp_acreage"):
                    raise LaneASourceUnavailable("WHP missing-area rows changed")
        output[name] = count
    if evidence.get("aligned_two_raster_service_qa_locations") != output["usda_continuous"]:
        raise LaneASourceUnavailable("Continuous and classified source pixel locations unaligned")
    return {
        "state": "ready_partial",
        "source": "LANE_A_FEMA_USFS_SOURCE_ONLY",
        "release_id": release_id,
        "source_only_records": output,
        "fema_source_polygons": output["fema_nfhl"],
        "fema_rtree_entries": output["fema_nfhl"],
        "usda_administrative_records": output["usda_summary"],
        "usda_continuous_qa_pixels": output["usda_continuous"],
        "usda_classified_qa_pixels": output["usda_classified"],
        "usda_zip_areas_missing_acreage": details["usda_summary"]["missing_whp_acreage"],
        "publisher_geographies": details["usda_summary"].get("by_geography"),
        "source_coverage": "FEMA_SIX_SMALL_TEST_WINDOWS_USFS_70_PIXEL_SAMPLES_2023_ADMIN_SUMMARIES",
        "fema_national_geometry_complete": False,
        "usfs_270m_national_raster_complete": False,
        "verified_insured_sites": 0,
        "insured_loss_records": 0,
        "publisher_vintage": "WHP2023 revised 2024-07-17; source landscape ~2020",
        "original_usda_zip_sha256": details["usda_summary"]["original_source_zip_sha256"],
        "authenticated_private_index_mounted": True,
        "notice": ("Verified source-only bounded sample and nationwide publisher geography "
                   "aggregates. Not a national flood or wildfire raster, physical-site "
                   "assessment, policy coverage or insured loss. Missing coverage is UNKNOWN."),
    }


def _ready():
    try:
        root = _configured_root()
        source_root, ptr = installed_release(root)
        info = _validate_release(str(root), ptr["release_id"],
                                 _fingerprint(root, source_root))
        return root, info
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError,
            sqlite3.Error) as exc:
        raise LaneASourceUnavailable("Mounted Lane A source release is absent or failed validation") from exc


def status():
    if not os.environ.get(ROOT_ENV, "").strip():
        return {
            "state": "not_configured", "source": "LANE_A_FEMA_USFS_SOURCE_ONLY",
            "authenticated_private_index_mounted": False,
            "verified_insured_sites": 0, "source_only_records": None,
            "notice": "Lane A validated CI indexes are not mounted on this private backend",
        }
    try:
        return _ready()[1]
    except LaneASourceUnavailable:
        return {
            "state": "unavailable", "source": "LANE_A_FEMA_USFS_SOURCE_ONLY",
            "authenticated_private_index_mounted": False,
            "verified_insured_sites": 0, "source_only_records": None,
            "notice": "Source index missing or invalid. No absence/zero-hazard conclusion",
        }


def usda_geography(geography_type, native_source_id):
    if geography_type not in ("zip", "county", "state", "management_jurisdiction"):
        raise ValueError("Unsupported native USDA publisher geography type")
    root, facts = _ready()
    record = query_publisher_id(root, "usda_summary",
                                geography_type=geography_type, original_id=native_source_id)
    record["source_release_id"] = facts["release_id"]
    record["is_physical_insured_facility"] = False
    return record


def fema_polygon(dfirm_id, fld_ar_id):
    if not NATIVE_PART.fullmatch(dfirm_id) or not NATIVE_PART.fullmatch(fld_ar_id):
        raise ValueError("Invalid original FEMA source identifiers")
    root, facts = _ready()
    key = "dfirm:" + dfirm_id + ":fld_ar:" + fld_ar_id
    record = query_publisher_id(root, "fema_nfhl", original_id=key)
    record["source_release_id"] = facts["release_id"]
    record["is_physical_insured_facility"] = False
    return record


def wildfire_qa_pixel(kind, region, index):
    if kind not in ("usda_continuous", "usda_classified"):
        raise ValueError("Invalid wildfire source product")
    root, facts = _ready()
    record = query_raster_probe(root, kind, region=region, grid_index=index)
    record["source_release_id"] = facts["release_id"]
    record["is_physical_insured_facility"] = False
    return record


def reviewed_facility_flood(conn, facility_id):
    root, facts = _ready()
    site = conn.execute("SELECT id,latitude,longitude FROM facilities WHERE id=?",
                        (facility_id,)).fetchone()
    if site is None:
        raise LookupError("Unknown private research facility")
    review = conn.execute(
        "SELECT * FROM location_reviews WHERE facility_id=?", (facility_id,)
    ).fetchone()
    if not is_reviewed_site_coordinate(site, review):
        return {
            "facility_id": facility_id, "source": "fema_nfhl",
            "coverage_state": "UNKNOWN_UNVERIFIED_SITE_COORDINATE",
            "source_features": [], "source_release_id": facts["release_id"],
            "review_required": True, "verified_property_hazard": False,
            "notice": "Current physical-site point requires independently corroborated location review",
        }
    result = query_reviewed_coordinate(
        root, longitude=float(site["longitude"]), latitude=float(site["latitude"]),
        site_reference=facility_id, coordinate_evidence=review["evidence_url"],
        coordinates_corroborated=True,
    )
    result["facility_id"] = facility_id
    result["source_release_id"] = facts["release_id"]
    result["property_hazard_legally_confirmed"] = False
    result["source_effective_map_dates_checked"] = False
    result["insurance_loss_or_claim"] = False
    return result
