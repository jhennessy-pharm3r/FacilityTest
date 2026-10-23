"""Lane D source-only SQLite installation contract for a private backend.

Installs verified EIA-861 or DOE/PNNL source indexes outside CI staging using
versioned, atomic, read-only SQLite files. This module cannot deploy a web API,
match physical sites, mark Source Health DEPLOYED, or verify insured BI claims.

The caller must supply a trusted expected SHA-256 of the official *raw source*
archive. A bundle containing only a self-asserted manifest is not trusted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from urllib.parse import quote
from uuid import uuid4

SPECS = {
    "eia861_2025": {
        "database": "lane_d_eia861_staging.sqlite",
        "publisher_source": "EIA861",
        "manifest_count": "accepted",
        "manifest_kinds": "accepted_by_source_kind",
        "receipt_source_sha": "original_zip_sha256",
        "receipt_db_sha": "local_index_sha256",
        "receipt_count": "local_index_rows",
        "kind_values": ("reliability", "state_total", "service_territory"),
        "native_key": "ingestion_row_key",
        "required_columns": ("ingestion_row_key", "source_kind", "utility_id", "state",
                             "county", "source_member", "source_sheet", "source_row",
                             "row_sha256", "original_row_json"),
    },
    "pnnl_2014_2023": {
        "database": "pnnl_county_outage_staging.sqlite",
        "publisher_source": "DOE_PNNL_EVENT_CORRELATED_OUTAGE",
        "manifest_count": "accepted",
        "manifest_kinds": "accepted_by_source_kind",
        "receipt_source_sha": "source_zip_sha256",
        "receipt_db_sha": "staged_sqlite_sha256",
        "receipt_count": "sqlite_rows_verified",
        "kind_values": ("county_episode", "correlated_event", "correlation_8h_sensitivity",
                        "correlation_24h_sensitivity", "state_month_aggregate"),
        "native_key": "source_row_key",
        "required_columns": ("source_row_key", "source_kind", "dataset_year", "county_fips",
                             "reported_start", "source_member", "source_line_number",
                             "source_row_sha256", "is_exact_duplicate_source_row",
                             "duplicate_of_source_line", "raw_json"),
    },
}
SHA = re.compile(r"[0-9a-f]{64}\Z")
VERSION = re.compile(r"[0-9a-f]{16}-[0-9a-f]{16}\Z")


def validate_sha(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise ValueError("An exact 64-character SHA-256 hex digest is required")
    return value


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as source:
        for piece in iter(lambda: source.read(1024 * 1024), b""):
            h.update(piece)
    return h.hexdigest()


def json_file(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def readonly_connect(path):
    path = Path(path).resolve(strict=True)
    if not path.is_file():
        raise ValueError("Missing reviewed SQLite database")
    url = "file:" + quote(str(path), safe="/:") + "?mode=ro&immutable=1"
    db = sqlite3.connect(url, uri=True, timeout=30)
    db.execute("PRAGMA query_only=ON")
    return db


def checked_path(folder, filename):
    folder = Path(folder)
    if folder.is_symlink():
        raise ValueError("Source package directory cannot be a symlink")
    candidate = folder / filename
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError("Missing or symlinked source package file: " + filename)
    return candidate


def audit_source_bundle(source, dataset, expected_source_sha256, expected_db_sha256=None):
    if dataset not in SPECS:
        raise ValueError("Only approved Lane D source-only index families may be installed")
    expected_source_sha256 = validate_sha(expected_source_sha256)
    if expected_db_sha256 is not None:
        validate_sha(expected_db_sha256)
    spec = SPECS[dataset]
    source = Path(source)
    manifest = json_file(checked_path(source, "manifest.json"))
    handoff = json_file(checked_path(source, "coordinator_handoff.json"))
    dbfile = checked_path(source, spec["database"])
    if manifest.get("source") != spec["publisher_source"]:
        raise ValueError("Wrong publisher/source manifest for dataset family")
    archive_sha = validate_sha(manifest.get("archive_sha256"))
    if archive_sha != expected_source_sha256:
        raise ValueError("Trusted raw-source archive SHA-256 does not match package")
    if handoff.get(spec["receipt_source_sha"]) != archive_sha:
        raise ValueError("Publisher raw-source checksum differs between manifest and handoff")
    manifest_count = manifest.get(spec["manifest_count"])
    receipt_count = handoff.get(spec["receipt_count"])
    if type(manifest_count) is not int or manifest_count < 1 or receipt_count != manifest_count:
        raise ValueError("Handoff and manifest accepted-row counts do not reconcile")
    for marker in ("durable_backend_indexed", "deployed"):
        if manifest.get(marker, 0) != 0:
            raise ValueError("Source-only handoff claims an unverified production state")
    if handoff.get("deployed", 0) != 0:
        raise ValueError("Coordinator source handoff cannot assert DEPLOYED")
    if manifest.get("rejected", -1) < 0:
        raise ValueError("Rejection count is absent from publisher receipt")
    if manifest.get("source_rows_scanned", manifest_count + manifest["rejected"]) != manifest_count + manifest["rejected"]:
        raise ValueError("Original source scanned/accepted/rejected counts differ")
    count_by_kind = manifest.get(spec["manifest_kinds"])
    if not isinstance(count_by_kind, dict) or any(
        kind not in spec["kind_values"] or type(count) is not int or count < 0
        for kind, count in count_by_kind.items()
    ):
        raise ValueError("Unknown source category or noninteger source count")
    if sum(count_by_kind.values()) != manifest_count:
        raise ValueError("Source-kind totals do not reconcile")
    digest = sha256_file(dbfile)
    if digest != validate_sha(handoff.get(spec["receipt_db_sha"])):
        raise ValueError("Source-only SQLite SHA-256 differs from package handoff receipt")
    if expected_db_sha256 is not None and digest != expected_db_sha256:
        raise ValueError("Index does not match optional coordinator-pinned SQLite digest")
    if dbfile.stat().st_size != handoff.get("local_index_bytes", handoff.get("staged_sqlite_bytes")):
        raise ValueError("SQLite byte size differs from coordinator receipt")
    with readonly_connect(dbfile) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite full integrity check failed")
        columns = {x[1] for x in db.execute("PRAGMA table_info(source_observations)")}
        if not set(spec["required_columns"]).issubset(columns):
            raise ValueError("Index missing source identifiers/provenance columns")
        rows = db.execute("SELECT COUNT(*) FROM source_observations").fetchone()[0]
        if rows != manifest_count:
            raise ValueError("Source index row count does not equal accepted source count")
        kinds = dict(db.execute(
            "SELECT source_kind, COUNT(*) FROM source_observations GROUP BY source_kind"))
        expected = {k: v for k, v in count_by_kind.items() if v > 0}
        if kinds != expected:
            raise ValueError("Installed index source-kind count does not equal manifest")
        if db.execute(
            f"SELECT COUNT(*) FROM source_observations WHERE {spec['native_key']} IS NULL"
        ).fetchone()[0]:
            raise ValueError("Null source-row IDs present")
        if dataset == "pnnl_2014_2023":
            duplicate_count = db.execute(
                "SELECT COUNT(*) FROM source_observations WHERE is_exact_duplicate_source_row=1"
            ).fetchone()[0]
            if duplicate_count != manifest.get("accepted_exact_duplicate_rows"):
                raise ValueError("PNNL duplicate lineage not consistent with source receipt")
            if rows - duplicate_count != manifest.get("distinct_source_table_row_contents"):
                raise ValueError("PNNL raw/content-distinct count cannot be reconciled")
        else:
            duplicate_count = None
    return {
        "dataset": dataset, "publisher_source": manifest["source"],
        "source_archive_sha256": archive_sha,
        "index_sha256": digest, "index_bytes": dbfile.stat().st_size,
        "source_rows_accepted": manifest_count, "source_rows_rejected": manifest["rejected"],
        "source_row_kinds": count_by_kind, "exact_duplicate_rows_flagged": duplicate_count,
        "index_integrity": "ok", "source_index_schema_verified": True,
        "deployed": False, "verified_insured_facility_outages": 0,
    }


def pointer_path(destination, dataset):
    if dataset not in SPECS:
        raise ValueError("Unsupported source dataset")
    destination = Path(destination)
    if destination.is_symlink() or (destination / dataset).is_symlink():
        raise ValueError("Symlinked destination or dataset root is not allowed")
    return destination / dataset / "current.json"


def install(source, destination, dataset, expected_source_sha256,
            expected_db_sha256=None, installation_role="ci-smoke"):
    if installation_role not in ("ci-smoke", "private-backend-candidate"):
        raise ValueError("Unrecognized installation context")
    report = audit_source_bundle(source, dataset, expected_source_sha256, expected_db_sha256)
    destination = Path(destination)
    pointer = pointer_path(destination, dataset)
    folder = pointer.parent
    folder.mkdir(parents=True, exist_ok=True)
    version = report["source_archive_sha256"][:16] + "-" + report["index_sha256"][:16]
    if not VERSION.fullmatch(version):
        raise RuntimeError("Unsafe source version")
    index_path = folder / "versions" / version
    lock = folder / ".install.lock"
    # Fail fast for parallel installers; never overwrite the currently served
    # pointer while another staging promotion is in progress.
    fd = None
    temporary = None
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.write(fd, b"lane-d-exclusive-source-install\n")
        os.close(fd)
        fd = None
        if not index_path.exists():
            (folder / "versions").mkdir(parents=True, exist_ok=True)
            temporary = Path(tempfile.mkdtemp(prefix=".pending-", dir=folder / "versions"))
            spec = SPECS[dataset]
            dest_index = temporary / spec["database"]
            shutil.copyfile(checked_path(source, spec["database"]), dest_index)
            if sha256_file(dest_index) != report["index_sha256"]:
                raise ValueError("Source index changed during copy; no promotion")
            shutil.copyfile(checked_path(source, "manifest.json"), temporary / "manifest.json")
            shutil.copyfile(checked_path(source, "coordinator_handoff.json"),
                            temporary / "coordinator_handoff.json")
            os.chmod(dest_index, 0o444)
            receipt = {
                **report, "version": version, "installation_role": installation_role,
                "installed_at_utc": datetime.now(timezone.utc).isoformat(),
                "state": "READONLY_PRIVATE_INSTALL_CANDIDATE_NOT_APP_DEPLOYED",
                "physical_site_crosswalk_verified": False,
                "source_health_deployed": False,
            }
            (temporary / "installation.json").write_text(
                json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, index_path)
            temporary = None
        else:
            existing = json_file(index_path / "installation.json")
            if (existing.get("index_sha256") != report["index_sha256"]
                or existing.get("source_archive_sha256") != report["source_archive_sha256"]
                or not (index_path / SPECS[dataset]["database"]).is_file()
                or sha256_file(index_path / SPECS[dataset]["database"]) != report["index_sha256"]):
                raise ValueError("Existing version directory is incomplete or has changed; current untouched")
        ptr = {
            "dataset": dataset, "version": version,
            "relative_db": "versions/" + version + "/" + SPECS[dataset]["database"],
            "index_sha256": report["index_sha256"],
            "source_archive_sha256": report["source_archive_sha256"],
            "rows": report["source_rows_accepted"],
            "source_health_deployed": False,
        }
        new_pointer = folder / (".current-" + uuid4().hex + ".json")
        try:
            new_pointer.write_text(json.dumps(ptr, indent=2) + "\n", encoding="utf-8")
            os.replace(new_pointer, pointer)
        finally:
            new_pointer.unlink(missing_ok=True)
        installed = verify_install(destination, dataset)
        return {**installed, "version": version, "installation_role": installation_role}
    finally:
        if fd is not None:
            os.close(fd)
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)
        lock.unlink(missing_ok=True)


def resolve_current(destination, dataset):
    current = pointer_path(destination, dataset)
    data = json_file(checked_path(current.parent, "current.json"))
    version = data.get("version")
    if data.get("dataset") != dataset or not isinstance(version, str) or not VERSION.fullmatch(version):
        raise ValueError("Index pointer contains wrong dataset or invalid version")
    path = current.parent / "versions" / version / SPECS[dataset]["database"]
    if data.get("relative_db") != "versions/" + version + "/" + SPECS[dataset]["database"]:
        raise ValueError("Index pointer has unapproved relative path")
    if path.is_symlink() or not path.is_file():
        raise ValueError("Installed source index is missing or symlinked")
    return path, data


def verify_install(destination, dataset):
    path, pointer = resolve_current(destination, dataset)
    folder = path.parent
    receipt = json_file(checked_path(folder, "installation.json"))
    if (receipt.get("index_sha256") != pointer["index_sha256"]
        or receipt.get("source_archive_sha256") != pointer["source_archive_sha256"]
        or receipt.get("source_rows_accepted") != pointer["rows"]):
        raise ValueError("Installed index pointer disagrees with install receipt")
    bundle = audit_source_bundle(folder, dataset, pointer["source_archive_sha256"],
                                 pointer["index_sha256"])
    if bundle["source_rows_accepted"] != pointer["rows"]:
        raise ValueError("Installed source row count changed")
    return {
        **bundle, "installation_role": receipt.get("installation_role"),
        "verification": "COMPLETE_STAGED_SOURCE_TO_INSTALLED_INDEX",
        "verified_readonly_sqlite": True, "verified_application_deployment": False,
    }


def query_install(destination, dataset, *, fips=None, year=None, state=None,
                  county=None, limit=10):
    path, pointer = resolve_current(destination, dataset)
    if dataset == "pnnl_2014_2023":
        from .query_staging import get_county_context
        result = get_county_context(fips, pnnl_db=path, year=year, limit=limit)
    else:
        from .query_eia_service_territory import service_territory_candidates
        result = service_territory_candidates(path, state, county, limit)
    return {
        "installed_dataset": dataset,
        "source_archive_sha256": pointer["source_archive_sha256"],
        "index_sha256": pointer["index_sha256"],
        "query_state": "READONLY_SOURCE_CONTEXT_NOT_FACILITY_EVIDENCE",
        "deployed_to_live_facility_app": False,
        "data": result,
    }


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    ins = sub.add_parser("install")
    ins.add_argument("--bundle", type=Path, required=True)
    ins.add_argument("--dest", type=Path, required=True)
    ins.add_argument("--dataset", choices=tuple(SPECS), required=True)
    ins.add_argument("--source-sha256", required=True)
    ins.add_argument("--index-sha256")
    ins.add_argument("--role", choices=("ci-smoke", "private-backend-candidate"),
                     default="ci-smoke")
    check = sub.add_parser("verify")
    check.add_argument("--dest", type=Path, required=True)
    check.add_argument("--dataset", choices=tuple(SPECS), required=True)
    qry = sub.add_parser("query")
    qry.add_argument("--dest", type=Path, required=True)
    qry.add_argument("--dataset", choices=tuple(SPECS), required=True)
    qry.add_argument("--fips")
    qry.add_argument("--year", type=int)
    qry.add_argument("--state")
    qry.add_argument("--county")
    qry.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if args.command == "install":
        result = install(args.bundle, args.dest, args.dataset, args.source_sha256,
                         args.index_sha256, args.role)
    elif args.command == "verify":
        result = verify_install(args.dest, args.dataset)
    else:
        result = query_install(args.dest, args.dataset, fips=args.fips, year=args.year,
                               state=args.state, county=args.county, limit=args.limit)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
