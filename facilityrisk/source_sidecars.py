"""Validated read-only EPA FRS and NOAA sources for the authenticated private app.

Source identities and regional events are not physical property verifications,
insured damage, or loss measurements. Public GitHub Pages does not use this.
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
import json
import os
from pathlib import Path
import re
import sqlite3

from .db import get_db_path
from .universal_registry import search as universal_search, detail as universal_detail
from .storm_events import search as noaa_search

FRS_INDEX_ENV = "FACILITY_RISK_FRS_INDEX_PATH"
FRS_QA_ENV = "FACILITY_RISK_FRS_INDEX_QA"
NOAA_INDEX_ENV = "FACILITY_RISK_NOAA_INDEX_PATH"
NOAA_MANIFEST_ENV = "FACILITY_RISK_NOAA_INDEX_MANIFEST"
GOOD_STATES = frozenset(("ready_full", "ready_partial"))
PRIVATE_TABLES = ("facilities", "evidence", "sec_findings", "raw_snapshots",
                  "audit_events", "insurance_policies", "insurance_terms",
                  "facility_assets", "review_approvals")


class SourceIndexUnavailable(ValueError):
    """A source-only index is absent, unreadable or did not pass validation."""


def _config(path_var, evidence_var):
    db_text = os.environ.get(path_var, "").strip()
    meta_text = os.environ.get(evidence_var, "").strip()
    if not db_text and not meta_text:
        return None
    if not db_text or not meta_text:
        raise SourceIndexUnavailable("Database and matching manifest must both be configured")
    db = Path(db_text).expanduser()
    meta = Path(meta_text).expanduser()
    if not db.is_absolute() or not meta.is_absolute():
        raise SourceIndexUnavailable("Source-only index paths must be absolute")
    if db.resolve() == get_db_path().resolve():
        raise SourceIndexUnavailable("Source index must not be the writable insured research database")
    if not db.is_file() or not meta.is_file():
        raise SourceIndexUnavailable("Configured index or manifest is absent")
    # Immutable SQLite deliberately ignores WAL writes: a nonempty WAL means
    # the source has not been sealed/checkpointed and must never be served.
    live_wal=Path(str(db)+"-wal")
    if live_wal.is_file() and live_wal.stat().st_size>0:
        raise SourceIndexUnavailable("Source-only SQLite has a live uncheckpointed WAL")
    return db, meta


@contextmanager
def _readonly(path: Path):
    # Snapshots must be sealed and mounted read-only; immutable mode avoids
    # SQLite WAL sidecar writes on Docker's read-only source volume.
    uri = path.resolve().as_uri() + "?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True, timeout=15)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA busy_timeout=15000")
        yield conn
    finally:
        conn.close()


def _cache_key(db, manifest):
    a, b = db.stat(), manifest.stat()
    return (str(db.resolve()), a.st_dev, a.st_ino, a.st_size, a.st_mtime_ns,
            str(manifest.resolve()), b.st_dev, b.st_ino, b.st_size, b.st_mtime_ns)


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r"[a-fA-F0-9]{64}", value) is not None


@lru_cache(maxsize=12)
def _frs_facts(db_path, device, inode, size, mtime, qa_path, qdevice, qinode, qsize, qmtime):
    qa = json.loads(Path(qa_path).read_text(encoding="utf-8"))
    if (qa.get("source") != "EPA FRS public reporting identities" or
        qa.get("sqlite_quick_check") != "ok" or
        not _sha(qa.get("source_archive_sha256")) or
        not _sha(qa.get("normalized_source_sha256")) or
        qa.get("database_bytes") != size):
        raise SourceIndexUnavailable("FRS source QA manifest invalid")
    with _readonly(Path(db_path)) as conn:
        tables = {r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"universal_sites", "universal_source_records", "universal_site_fts"}
        if not required.issubset(tables):
            raise SourceIndexUnavailable("FRS identity search tables missing")
        count = conn.execute("SELECT COUNT(*) FROM universal_source_records").fetchone()[0]
        sites = conn.execute("SELECT COUNT(*) FROM universal_sites").fetchone()[0]
        keys = {r[0] for r in conn.execute("SELECT DISTINCT source_key FROM universal_source_records")}
        if (count != qa.get("unique_source_identifiers") or sites != qa.get("site_candidates")
            or count <= 0 or keys != {"EPA_FRS"}):
            raise SourceIndexUnavailable("FRS indexed source identities disagree with QA")
        for table in PRIVATE_TABLES:
            if table in tables and conn.execute('SELECT 1 FROM "' + table + '" LIMIT 1').fetchone():
                raise SourceIndexUnavailable("Source-only index contains private research records")
    return {"state": "ready_full" if count >= 5_000_000 else "ready_partial",
            "source": "EPA_FRS", "site_candidates": sites, "source_identities": count,
            "vintage": qa.get("source_vintage"), "publisher": "US EPA Facility Registry Service",
            "source_sha256": qa["source_archive_sha256"],
            "manifest_status": "previously_validated_qa_and_current_counts",
            "notice": "Source identities only; property coordinates and insurance losses are not verified"}


@lru_cache(maxsize=12)
def _noaa_facts(db_path, device, inode, size, mtime, manifest_path,
                mdevice, minode, msize, mmtime):
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    parts = manifest.get("partitions")
    if (manifest.get("publisher") != "NOAA NCEI Storm Events Details" or
        manifest.get("complete_requested_years") is not True or
        not _sha(manifest.get("normalized_sha256")) or
        not isinstance(parts, list) or not parts):
        raise SourceIndexUnavailable("NOAA source manifest invalid")
    years = [p.get("year") for p in parts]
    if (len(years) != len(set(years)) or
        sorted(years) != sorted(manifest.get("requested_years", []))):
        raise SourceIndexUnavailable("NOAA source years are incomplete or duplicated")
    with _readonly(Path(db_path)) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"noaa_storm_events", "noaa_storm_imports"}.issubset(tables):
            raise SourceIndexUnavailable("NOAA source tables missing")
        for table in PRIVATE_TABLES:
            if table in tables and conn.execute('SELECT 1 FROM "' + table + '" LIMIT 1').fetchone():
                raise SourceIndexUnavailable("NOAA index contains private research records")
        records = list(conn.execute(
            "SELECT source_year,COUNT(*) AS rows, "
            "SUM(CASE WHEN begin_latitude IS NOT NULL AND begin_longitude IS NOT NULL "
            "THEN 1 ELSE 0 END) AS with_coordinates FROM noaa_storm_events "
            "GROUP BY source_year ORDER BY source_year"))
        by_year = {r["source_year"]: r for r in records}
        imports = {r["source_year"]: r for r in conn.execute(
            "SELECT * FROM noaa_storm_imports")}
        if len(by_year) != len(parts) or len(imports) != len(parts):
            raise SourceIndexUnavailable("NOAA database is missing a source year")
        for p in parts:
            yr = p["year"]
            row, original = by_year.get(yr), imports.get(yr)
            if (row is None or original is None or row["rows"] != p["event_records"]
                or (row["with_coordinates"] or 0) != p["point_coordinates_reported"]
                or original["source_sha256"] != p["original_archive_sha256"]
                or original["normalized_sha256"] != manifest["normalized_sha256"]):
                raise SourceIndexUnavailable("NOAA year differs from source manifest")
        total = sum(r["rows"] for r in records)
        if total != manifest["total_events"]:
            raise SourceIndexUnavailable("NOAA source-event total mismatch")
    return {"state": "ready_partial", "source": "NOAA_STORM_EVENTS",
            "records": total,
            "coordinate_records": sum(p["point_coordinates_reported"] for p in parts),
            "years": sorted(by_year), "vintage": manifest.get("generated_at"),
            "publisher": "NOAA NCEI", "source_sha256": manifest["normalized_sha256"],
            "manifest_status": "complete_matching_requested_years",
            "notice": "Regional source reports only; not site-specific hazard intensity or insured damage"}


def _status(kind, db_env, meta_env, validator):
    if not os.environ.get(db_env, "").strip() and not os.environ.get(meta_env, "").strip():
        return {"state": "not_configured", "source": kind,
                "notice": "Verified read-only source snapshot not mounted on this private server"}
    try:
        paths = _config(db_env, meta_env)
        return validator(*_cache_key(*paths))
    except (SourceIndexUnavailable, ValueError, TypeError, OSError, sqlite3.Error, KeyError):
        return {"state": "unavailable", "source": kind,
                "notice": "Configured source index failed validation; do not infer coverage"}


def frs_status():
    return _status("EPA_FRS", FRS_INDEX_ENV, FRS_QA_ENV, _frs_facts)


def noaa_index_status():
    return _status("NOAA_STORM_EVENTS", NOAA_INDEX_ENV, NOAA_MANIFEST_ENV, _noaa_facts)


def status():
    return {"frs": frs_status(), "noaa": noaa_index_status(),
            "scope": "Read-only public-authority source catalogs, never insured properties or claims"}


@contextmanager
def frs_connection():
    if frs_status()["state"] not in GOOD_STATES:
        raise SourceIndexUnavailable("Validated EPA FRS source index not mounted")
    with _readonly(_config(FRS_INDEX_ENV, FRS_QA_ENV)[0]) as conn:
        yield conn


@contextmanager
def noaa_connection():
    if noaa_index_status()["state"] not in GOOD_STATES:
        raise SourceIndexUnavailable("Validated NOAA source index not mounted")
    with _readonly(_config(NOAA_INDEX_ENV, NOAA_MANIFEST_ENV)[0]) as conn:
        yield conn


def frs_search(**filters):
    with frs_connection() as conn:
        results = universal_search(conn, source="EPA_FRS", **filters)
    results["index"] = "EPA_FRS"
    results["property_verification"] = "unassessed"
    return results


def frs_detail(site_id):
    with frs_connection() as conn:
        result = universal_detail(conn, site_id)
    if result is None or not any(r["source_key"] == "EPA_FRS" for r in result["source_identities"]):
        return None
    result["source_database"] = "EPA_FRS_readonly"
    result["property_verification"] = "unassessed"
    return result


def noaa_events(**filters):
    with noaa_connection() as conn:
        return noaa_search(conn, **filters)
