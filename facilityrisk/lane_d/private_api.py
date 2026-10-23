"""Authenticated private Lane D API adapter over *installed* immutable source indexes.

This module belongs to coordinator integration, not a lane importer. Its public
contract returns source-reported county/utility evidence, never verified policy,
insured site downtime, insurer payment, or facility-to-utility linkage.

All routes run under facilityrisk.app's existing private security middleware.
Github Pages cannot access these SQLite files.
"""
from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
import re
import sqlite3

from fastapi import APIRouter, HTTPException, Query

from .install_source_index import (
    SPECS, resolve_current, verify_install, query_install,
)
from ..db import get_db_path

router = APIRouter(tags=["Lane D source context"])
SOURCE_ROOT_VAR = "FACILITY_RISK_LANE_D_INDEX_ROOT"
ODIN_RIGHTS_VAR = "FACILITY_RISK_LANE_D_ODIN_USE_APPROVED"

# A single original publisher source family per endpoint; source vintages must
# remain segregated and cannot be joined to create a new incident census.
ROUTES = {
    "eia861_2025": "2025 EIA reporting utilities, not property service assignments",
    "pnnl_2014_2023": "2014-2023 DOE PNNL county episodes, not insured site outages",
    "oe417_annual_public": "DOE 2023 discovery reporting rows; overlaps EIA EPM",
    "odin_direct_public": "current original ORNL ODIN county status snapshot, use rights pending",
}
PRIVATE_TABLES = {
    "facilities", "evidence", "insurance_policies", "insurance_terms",
    "facility_assets", "sec_findings", "raw_snapshots", "audit_events",
    "review_approvals", "universal_sites", "universal_source_records",
}


class LaneDSourceUnavailable(ValueError):
    """Source-only archive has not been reviewed, installed or verified."""


def _root():
    value = os.environ.get(SOURCE_ROOT_VAR, "").strip()
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise LaneDSourceUnavailable("Private read-only source root is missing or unsafe")
    # Do not permit source indexes inside the mutable insured research workspace.
    db_path = get_db_path().resolve()
    root = path.resolve()
    if root == db_path.parent or root.is_relative_to(db_path.parent):
        raise LaneDSourceUnavailable("Source-only indexes must be independent of insured workspace")
    return root


def _is_wal_sealed(db_path):
    for name in (str(db_path) + "-wal", str(db_path) + "-journal"):
        shadow = Path(name)
        if shadow.is_file() and shadow.stat().st_size:
            return False
    return True


@lru_cache(maxsize=12)
def _check_cached(root_string, dataset, pointer_inode, pointer_size,
                  pointer_mtime, db_inode, db_size, db_mtime,
                  manifest_inode, manifest_mtime):
    result = verify_install(Path(root_string), dataset)
    path, _pointer = resolve_current(Path(root_string), dataset)
    if not _is_wal_sealed(path):
        raise LaneDSourceUnavailable("Uncheckpointed source SQLite has a live journal")
    # Fail closed if an untrusted source index contains private client/insured data.
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as db:
        tables = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        unexpected = tables.intersection(PRIVATE_TABLES)
        if unexpected:
            raise LaneDSourceUnavailable("Invalid source index: private workspace tables detected")
        db.execute("PRAGMA query_only=ON")
        if not {"source_observations"}.issubset(tables):
            raise LaneDSourceUnavailable("Original source observation table is missing")
    return result


def _verified(dataset):
    if dataset not in SPECS or dataset not in ROUTES:
        raise LaneDSourceUnavailable("Unknown publisher data family")
    root = _root()
    if root is None:
        raise LaneDSourceUnavailable("Private Lane D source index is not configured")
    try:
        path, _meta = resolve_current(root, dataset)
        pointer = root / dataset / "current.json"
        manifest = path.parent / "manifest.json"
        pst, st, mst = pointer.stat(), path.stat(), manifest.stat()
        info = _check_cached(
            str(root), dataset,
            pst.st_ino, pst.st_size, pst.st_mtime_ns,
            st.st_ino, st.st_size, st.st_mtime_ns,
            mst.st_ino, mst.st_mtime_ns,
        )
    except (ValueError, KeyError, OSError, sqlite3.DatabaseError) as exc:
        raise LaneDSourceUnavailable("Installed source index failed its integrity/provenance gate") from exc
    if info["source_rows_accepted"] <= 0 or not _is_wal_sealed(path):
        raise LaneDSourceUnavailable("Installed source index not safe for immutable read-only access")
    return root, info


def _rights_available(dataset):
    return dataset != "odin_direct_public" or os.environ.get(ODIN_RIGHTS_VAR) == "1"


def installed_status():
    try:
        root = _root()
        root_error = None
    except LaneDSourceUnavailable:
        root = None
        root_error = "invalid_source_root"
    rows = {}
    for dataset in ROUTES:
        item = {
            "source": dataset,
            "publisher_grain_notice": ROUTES[dataset],
            "state": "not_configured" if root is None and root_error is None else "not_installed",
            "indexed_private_readonly_rows": 0,
            "verified_insured_site_utility_connections": 0,
            "verified_insured_facility_outages": 0,
            "independently_carrier_verified_bi_claims": 0,
            "public_pages_deployed": False,
            "not_a_national_site_coverage_census": True,
        }
        if root_error is not None:
            item["state"] = "unavailable"
        elif root is not None:
            try:
                _root_live, receipt = _verified(dataset)
                item.update({
                    "state": "verified_private_source_index" if _rights_available(dataset)
                             else "rights_review_required",
                    "indexed_private_readonly_rows": receipt["source_rows_accepted"],
                    "publisher_original_sha256": receipt["source_archive_sha256"],
                    "sqlite_sha256": receipt["index_sha256"],
                    "source_row_exact_duplicates_flagged": receipt["exact_duplicate_rows_flagged"],
                    "private_api_queryable": _rights_available(dataset),
                })
            except LaneDSourceUnavailable:
                # Do not convert an improperly configured index into "zero risk".
                if (root / dataset / "current.json").exists():
                    item["state"] = "unavailable"
        rows[dataset] = item
    return {
        "readiness": "PRIVATE_SOURCE_INDEX_STATUS_NOT_PHYSICAL_FACILITY_RISK",
        "source_index_mount_configured": root is not None,
        "datasets": rows,
        "confirmed_insured_site_outages": 0,
        "confirmed_paid_insurance_claims": 0,
        "status_is_private_backend_not_public_github_pages": True,
        "limitations": [
            "Original publisher source identities are not insured property records",
            "EIA provider candidates do not prove the serving utility of a building",
            "PNNL county episodes are historical/contextual and not electric meter outages at a site",
            "OE417 annual source and EIA EPM overlap; cannot sum their event counts",
            "ODIN is a point-in-time county snapshot; do not sum successive snapshots",
            "Source installation does not independently verify any insurance policy or payment",
        ],
    }


def _query(dataset, **kwargs):
    if not _rights_available(dataset):
        raise HTTPException(503, "ORNL publisher rights review is required before source serving")
    try:
        root, receipt = _verified(dataset)
        data = query_install(root, dataset, **kwargs)
    except LaneDSourceUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except (ValueError, sqlite3.DatabaseError, OSError) as exc:
        # Invalid query args should not be confused with unavailable source index.
        if isinstance(exc, ValueError) and not isinstance(exc, sqlite3.DatabaseError):
            raise HTTPException(422, str(exc)) from exc
        raise HTTPException(503, "Verified source query currently unavailable") from exc
    return {
        "publisher_source": dataset,
        "source_original_sha256": receipt["source_archive_sha256"],
        "installed_index_sha256": receipt["index_sha256"],
        "read_only_source_context_served_by_private_api": True,
        "insured_site_service_connection_verified": False,
        "insured_site_outage_verified": False,
        "paid_insurer_business_interruption_claim_verified": False,
        "site_loss_amount_verified": False,
        "data": data["data"],
    }


@router.get("/api/source-context/lane-d/status")
def lane_d_status():
    return installed_status()


@router.get("/api/source-context/utility-candidates")
def utility_candidates(
    state: str = Query(..., min_length=2, max_length=2, pattern=r"^[A-Z]{2}$"),
    county: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(25, ge=1, le=100),
):
    if not re.fullmatch(r"[a-zA-Z0-9 .'\-()]+", county):
        raise HTTPException(422, "County must be the exact original EIA county name")
    return _query("eia861_2025", state=state, county=county, limit=limit)


@router.get("/api/source-context/historical-outages")
def historical_county_outages(
    county_fips: str = Query(..., min_length=5, max_length=5, pattern=r"^[0-9]{5}$"),
    year: int | None = Query(None, ge=2014, le=2023),
    limit: int = Query(25, ge=1, le=100),
):
    return _query("pnnl_2014_2023", fips=county_fips, year=year, limit=limit)


@router.get("/api/source-context/annual-electric-disturbances")
def annual_disturbances(
    year: int | None = Query(None, ge=2000, le=2026),
    limit: int = Query(25, ge=1, le=100),
):
    return _query("oe417_annual_public", year=year, limit=limit)


@router.get("/api/source-context/current-outages")
def current_county_outages(
    county_fips: str = Query(..., min_length=5, max_length=5, pattern=r"^[0-9]{5}$"),
    limit: int = Query(25, ge=1, le=100),
):
    return _query("odin_direct_public", fips=county_fips, limit=limit)
