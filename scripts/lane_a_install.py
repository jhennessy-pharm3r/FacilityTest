"""Install verified Lane A government source indexes into an immutable local release.

No shared app/schema/UI edits. Accepts publisher-source GitHub Actions artifact
ZIP files and/or an already-extracted data/lane_a directory. Verifies original
response SHA, native source IDs, row counts, SQLite and independent read-only
queries *before* atomic activation. A release is durable only if the coordinator
installs it on their provisioned persistent disk; CI tests are NOT deployment.
"""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import sqlite3
import stat
import sys
import tempfile
import zipfile
from datetime import datetime, timezone

from scripts.verify_lane_a_archive import verify_dir
from scripts.verify_lane_a_whp_index import verify as verify_whp_index
from scripts.lane_a_fema_query_smoke import validate as verify_fema_index
from scripts.lane_a_integration_handoff import generate as source_handoff
from facilityrisk.lane_a_source_query import source_whp_record, source_fema_polygon

DIRECTORIES = frozenset((
    "paged_windows", "whp_regions", "whp_classified",
    "whp_official_summary", "whp_official_index",
))
REQUIRED_FILES = {
    "fema_nfhl": ("paged_windows/manifest.json",
                  "paged_windows/fema-window-index.sqlite"),
    "usda_continuous": ("whp_regions/manifest.json",
                        "whp_regions/whp-regional-source-only.sqlite"),
    "usda_classified": ("whp_classified/manifest.json",
                        "whp_classified/whp-classified-source-only.sqlite"),
    "usda_summary": ("whp_official_index/manifest.json",
                     "whp_official_index/whp2023-source-geographies.sqlite",
                     "whp_official_index/whp2023-source-geographies.ndjson.gz",
                     "whp_official_summary/whp2023_official_summaries.zip"),
}
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_TOTAL_BYTES = 400 * 1024 * 1024


def sha256(path):
    digest = hashlib.sha256()
    with pathlib.Path(path).open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def _safe_relative_name(filename):
    if "\\" in filename or "\x00" in filename or filename.startswith("/"):
        raise ValueError("Archive contains an unsafe path")
    parts = pathlib.PurePosixPath(filename).parts
    if (not parts or any(p in ("..", ".", "") for p in parts) or
            len(parts) > 12 or parts[0] not in DIRECTORIES):
        raise ValueError("Archive contains a path outside Lane A owned sources")
    return pathlib.Path(*parts)


def _copy_checked(stream, target, size):
    if size > MAX_FILE_BYTES:
        raise ValueError("An artifact member exceeds 100MB limit")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as out:
        transferred = 0
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            transferred += len(chunk)
            if transferred > MAX_FILE_BYTES or transferred > size:
                raise ValueError("Archive decompression exceeds declared source size")
            out.write(chunk)
    if transferred != size:
        raise ValueError("Archive member has a mismatched uncompressed length")


def stage_sources(root, *, artifact_paths=(), source_root=None):
    """Extract only allowed Lane A source components; reject conflicts and symlinks."""
    root = pathlib.Path(root)
    root.mkdir(parents=True, exist_ok=True)
    receipts = {}
    total = 0

    def process(rel, data_reader, size):
        nonlocal total
        total += size
        if total > MAX_TOTAL_BYTES:
            raise ValueError("Source bundle exceeds 400MB safety limit")
        dest = root / rel
        if dest.exists():
            with tempfile.NamedTemporaryFile(dir=root, delete=False) as f:
                scratch = pathlib.Path(f.name)
            try:
                with data_reader() as stream:
                    _copy_checked(stream, scratch, size)
                if sha256(dest) != sha256(scratch):
                    raise ValueError("Conflicting source artifacts for path: " + str(rel))
            finally:
                scratch.unlink(missing_ok=True)
        else:
            with data_reader() as stream:
                _copy_checked(stream, dest, size)
        receipts[str(rel).replace("\\", "/")] = {"sha256": sha256(dest), "bytes": size}

    for archive_path in artifact_paths:
        archive_path = pathlib.Path(archive_path)
        if not archive_path.is_file() or archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
            raise ValueError("Missing/oversized input GitHub Actions artifact ZIP")
        with zipfile.ZipFile(archive_path) as archive:
            for entry in archive.infolist():
                if entry.is_dir():
                    continue
                # Artifact ZIPs occasionally include .gitkeep etc; explicitly
                # reject anything other than Lane A's own source directories.
                rel = _safe_relative_name(entry.filename)
                if stat.S_IFMT(entry.external_attr >> 16) == stat.S_IFLNK:
                    raise ValueError("Refusing artifact symlink: " + entry.filename)
                if entry.file_size > MAX_FILE_BYTES:
                    raise ValueError("Source member exceeds size budget")
                process(rel, lambda a=archive, e=entry: a.open(e), entry.file_size)
    if source_root is not None:
        source_root = pathlib.Path(source_root)
        if not source_root.is_dir():
            raise ValueError("Source root does not exist")
        for name in sorted(DIRECTORIES):
            directory = source_root / name
            if not directory.is_dir():
                continue
            for path in sorted(directory.rglob("*")):
                if path.is_symlink():
                    raise ValueError("Refusing source staging symlink")
                if not path.is_file():
                    continue
                rel = path.relative_to(source_root)
                _safe_relative_name(rel.as_posix())
                process(rel, lambda p=path: p.open("rb"), path.stat().st_size)
    if not receipts:
        raise ValueError("No eligible official Lane A source artifact files supplied")
    return receipts


def _scalar(db_path, query):
    path = pathlib.Path(db_path).resolve()
    with sqlite3.connect("file:" + str(path) + "?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        return db.execute(query).fetchone()[0]


def validate(root, required):
    """Full archive rehash plus original-source, row-level and query contract QA."""
    root = pathlib.Path(root)
    required = frozenset(required)
    if not required or not required.issubset(REQUIRED_FILES):
        raise ValueError("Pass one or more recognized --require source components")
    available = {
        name for name, files in REQUIRED_FILES.items()
        if all((root / file).is_file() for file in files)
    }
    for name, files in REQUIRED_FILES.items():
        found = [(root / f).is_file() for f in files]
        if any(found) and not all(found):
            raise ValueError("Partially supplied required files for " + name)
    if not required.issubset(available):
        raise ValueError("Required official source cohort missing: " +
                         repr(sorted(required - available)))
    if not available:
        raise ValueError("No complete source component is installable")
    receipt = {
        "status": "VALIDATED_LOCAL_INSTALL_READY_NOT_DEPLOYED",
        "available_sources": sorted(available), "required_sources": sorted(required),
        "source_only_indexes": {}, "read_only_verified": True,
        "physical_site_matches": 0, "insured_losses": 0,
        "app_deployed": False, "national_raster_or_nfhl_complete": False,
    }
    # Global original FEMA/USFS source-reply checksums. This verifier also
    # checks all SQL staging index row counts against the source manifests.
    if available.intersection({"fema_nfhl", "usda_continuous", "usda_classified"}):
        hashes = verify_dir(root)
        receipt["original_source_response_sha256_files_verified"] = (
            hashes["total_preserved_source_responses"]
        )
        receipt["source_response_index_verification"] = {
            k: v.get("indexed") for k, v in hashes["source_directories"].items()
        }
    if "fema_nfhl" in available:
        manifest = json.loads((root / "paged_windows/manifest.json").read_text())
        if not manifest.get("all_requested_windows_complete"):
            raise ValueError("Incomplete FEMA geographic window source corpus; fail closed")
        fema = verify_fema_index(root / "paged_windows")
        if not fema["read_only_source_query_verified"]:
            raise ValueError("FEMA native source key query / spatial index incomplete")
        receipt["source_only_indexes"]["fema_nfhl"] = {
            "rows": fema["original_polygon_count"],
            "rtree": fema["rtree_index_rows"],
            "bbox_windows": fema["source_windows"],
            "generalized_geometry": fema["generalized_geometry_review_only"],
            "source_native_ids": fema["distinct_source_native_keys"],
            "coverage": "ONLY_SIX_GEO_QA_WINDOWS_NOT_NATIONWIDE",
        }
    if "usda_continuous" in available:
        m = json.loads((root / "whp_regions/manifest.json").read_text())
        if not m.get("complete_geographic_probe_set"):
            raise ValueError("Incomplete official USDA WHP continuous geographic probes")
        receipt["source_only_indexes"]["usda_continuous"] = {
            "rows": m["indexed_point_observations"],
            "pixels": m["downloaded_replies"],
            "coverage": "70_REGION_PROBES_NOT_NATIONAL_RASTER",
        }
    if "usda_classified" in available:
        m = json.loads((root / "whp_classified/manifest.json").read_text())
        if not m.get("sample_complete"):
            raise ValueError("Incomplete official USDA WHP classified geographic probes")
        receipt["source_only_indexes"]["usda_classified"] = {
            "rows": m["indexed_observations"], "pixels": m["received"],
            "masked": m["special_mask_classes"] + m["nodata"],
            "coverage": "70_REGION_PROBES_NOT_NATIONAL_RASTER",
        }
    if {"usda_classified", "usda_continuous"}.issubset(available):
        a = root / "whp_regions/whp-regional-source-only.sqlite"
        b = root / "whp_classified/whp-classified-source-only.sqlite"
        with sqlite3.connect("file:" + str(a.resolve()) + "?mode=ro", uri=True) as db:
            continuous = set(db.execute(
                "SELECT region,probe_index,longitude,latitude FROM whp_geographic_probes"))
        with sqlite3.connect("file:" + str(b.resolve()) + "?mode=ro", uri=True) as db:
            classified = set(db.execute(
                "SELECT region,probe_index,longitude,latitude FROM usfs_whp_classified_probes"))
        if continuous != classified:
            raise ValueError("USFS classified and continuous official source sample coordinates differ")
        receipt["aligned_two_raster_service_qa_locations"] = len(continuous)
    if "usda_summary" in available:
        admin = verify_whp_index(
            root / "whp_official_summary/whp2023_official_summaries.zip",
            root / "whp_official_index")
        if admin["source_rows_read"] != admin["sqlite_indexed"] or admin["sqlite_integrity"] != "ok":
            raise ValueError("USDA official source-to-SQLite verification incomplete")
        dbpath = root / "whp_official_index/whp2023-source-geographies.sqlite"
        probe = source_whp_record(dbpath, "zip", "10168")
        if (probe.get("source_coverage") != "UNKNOWN_NO_AREA_VALUES" or
                probe.get("total_acres") is not None):
            raise ValueError("Original publisher missing-area ZIP incorrectly assigned numeric hazard")
        if source_whp_record(dbpath, "zip", "00029").get("native_geographic_id") != "00029":
            raise ValueError("WHP original leading-zero ZIP key lost")
        receipt["source_only_indexes"]["usda_summary"] = {
            "rows": admin["sqlite_indexed"], "by_geography": admin["by_geography"],
            "missing_whp_acreage": admin["unknown_raster_coverage"],
            "original_source_zip_sha256": admin["official_zip_sha256_verified"],
            "normalized_gzip_sha256": admin["normalized_gzip_sha256_verified"],
            "coverage": "COMPLETE_PUBLISHER_2023_AGGREGATES_NOT_270M_RASTER",
        }
    receipt["coordinator_source_handoff"] = source_handoff(root)
    return receipt


def install(destination, *, archives=(), source_root=None, required=("usda_summary",)):
    """Hash-address immutable release and atomically move a current pointer.

    Root must be an authorized, persistent directory owned by the operator.
    Operator controls authentication, backups, refresh and real app deployment.
    """
    destination = pathlib.Path(destination).resolve()
    if destination.exists() and destination.is_symlink():
        raise ValueError("Installer destination must not be a symlink")
    destination.mkdir(parents=True, exist_ok=True)
    releases = destination / "releases"
    releases.mkdir(exist_ok=True)
    scratch = pathlib.Path(tempfile.mkdtemp(prefix=".lane_a_pending_", dir=destination))
    try:
        data_root = scratch / "data" / "lane_a"
        files = stage_sources(data_root, artifact_paths=archives, source_root=source_root)
        result = validate(data_root, required)
        # Stable for identical retained original artifacts regardless of input
        # archive order, extraction order or installation timestamp.
        deterministic = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
        release_id = hashlib.sha256(deterministic).hexdigest()[:24]
        result["release_id"] = release_id
        result["source_file_count"] = len(files)
        result["retained_source_file_sha256"] = files
        result["release_content_sha256"] = hashlib.sha256(deterministic).hexdigest()
        target = releases / release_id
        (scratch / "release-verification.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        for path in scratch.rglob("*"):
            if path.is_file() and not path.is_symlink():
                path.chmod(0o444)
        if target.exists():
            verify_existing = validate(target / "data" / "lane_a", required)
            stored = json.loads((target / "release-verification.json").read_text())
            if (stored.get("release_content_sha256") != result["release_content_sha256"] or
                    verify_existing["source_only_indexes"] != result["source_only_indexes"]):
                raise ValueError("Existing same-ID release content differs; refusing replace")
        else:
            os.replace(scratch, target)
        pointer = {
            "schema_version": "facility_risk_lane_a_read_only_release_v1",
            "release_id": release_id,
            "relative_root": "releases/" + release_id + "/data/lane_a",
            "verified_source_only_rows": {
                name: item["rows"] for name, item in result["source_only_indexes"].items()
            },
            "source_health_for_main_app": "NOT_DEPLOYED_UNTIL_COORDINATOR_VERIFIES",
            "site_matches_verified": 0,
            "published_by_lane_a": False,
            "activated_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination,
            prefix=".lane_a_pointer_", delete=False
        ) as writable:
            pointer_temp = pathlib.Path(writable.name)
            json.dump(pointer, writable, sort_keys=True, indent=2)
            writable.write("\n")
            writable.flush()
            os.fsync(writable.fileno())
        os.replace(pointer_temp, destination / "current.json")
        return result
    finally:
        if scratch.exists():
            shutil.rmtree(scratch)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--destination", required=True)
    p.add_argument("--archive", action="append", default=[],
                   help="A ZIP produced by the official lane-a GitHub Actions workflow; repeatable")
    p.add_argument("--source-root",
                   help="Source output directory data/lane_a from a successful official run")
    p.add_argument("--require", action="append", choices=sorted(REQUIRED_FILES), default=[],
                   help="Component(s) that must be present and fully verified; repeatable")
    args = p.parse_args(argv)
    try:
        report = install(args.destination, archives=args.archive,
                         source_root=args.source_root,
                         required=args.require or ["usda_summary"])
    except (OSError, ValueError, RuntimeError, sqlite3.Error,
            zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
        print("LANE_A_INSTALL_FAILED=" + type(exc).__name__ + ": " + str(exc),
              file=sys.stderr)
        return 2
    print("LANE_A_INSTALL_VERIFIED=" + json.dumps({
        "release_id": report["release_id"],
        "installed_source_only_indexes": report["source_only_indexes"],
        "retained_source_file_count": report["source_file_count"],
        "app_deployed": False, "physical_sites_matched": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
