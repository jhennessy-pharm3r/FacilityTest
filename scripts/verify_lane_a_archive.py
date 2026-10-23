"""Verify downloaded Lane A official-source replies against manifest + SQLite.

Run after the GitHub Actions source workflow or after extracting its ZIP artifact.
A PASS proves artifact integrity, NOT nationwide coverage or site-level readiness.
"""
import argparse
import hashlib
import json
import pathlib
import sqlite3
import sys


def file_receipt(root, receipt):
    raw_file = receipt.get("raw_file")
    sha = receipt.get("raw_sha256") or receipt.get("response_sha256")
    if raw_file is None:
        if sha is not None:
            raise ValueError("Receipt has checksum but no retained raw file")
        return None
    if not isinstance(sha, str) or len(sha) != 64:
        raise ValueError("Downloaded sample lacks SHA256")
    raw_path = root / "raw" / raw_file
    raw_bytes = raw_path.read_bytes()
    actual = hashlib.sha256(raw_bytes).hexdigest()
    if actual != sha:
        raise ValueError("Checksum mismatch: " + str(raw_path))
    if "bytes" in receipt and receipt["bytes"] != len(raw_bytes):
        raise ValueError("Response byte count mismatch: " + str(raw_path))
    if "downloaded_bytes" in receipt and receipt["downloaded_bytes"] != len(raw_bytes):
        raise ValueError("Response byte count mismatch: " + str(raw_path))
    parsed = json.loads(raw_bytes)
    if not isinstance(parsed, dict):
        raise ValueError("Invalid original ArcGIS response object")
    return {"file": raw_file, "sha256": sha, "bytes": len(raw_bytes)}


def sqlite_count(file, table):
    db = sqlite3.connect(file)
    try:
        assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        row = db.execute("SELECT COUNT(*) FROM " + table).fetchone()
        return row[0]
    finally:
        db.close()


def verify_dir(root):
    root = pathlib.Path(root)
    report = {"source_directories": {}, "total_preserved_source_responses": 0,
              "source_samples_not_national_coverage": True}
    for d, db_filename, specs in (
        ("live_validation", "source-only.sqlite",
         (("fema_nfhl", "fema_source_observations"),
          ("usfs_whp_continuous_2023", "usfs_raster_observations"))),
        ("massgis_2025", "massgis-source-only.sqlite",
         (("massgis_ma_nfhl_2025_sfha_subset", "fema_source_observations"),)),
        ("fema_transport", "fema-attribute-only.sqlite",
         (("fema_transport_attribute_only", "fema_attribute_samples"),)),
    ):
        directory = root / d
        manifest_path = directory / "manifest.json"
        if not manifest_path.exists():
            continue
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        receipts = []
        if d == "live_validation":
            for source in m["sources"].values():
                receipts.append(source["metadata"])
                receipts.extend(source["samples"])
        elif d == "massgis_2025":
            receipts = [m["metadata"]] + m["samples"]
        else:
            receipts = m["strategies"]
        retained = [result for r in receipts if (result := file_receipt(directory, r)) is not None]
        report["total_preserved_source_responses"] += len(retained)
        tables = {}
        for source, table in specs:
            actual = sqlite_count(directory / db_filename, table)
            expected = (
                m["sources"][source]["indexed_observations"]
                if d == "live_validation" else m["indexed_observations"]
            )
            if actual != expected:
                raise ValueError("Indexed count mismatch: " + d + " / " + table)
            if d == "live_validation":
                s = m["sources"][source]
                if s["sample_raw"] != s["sample_accepted"] + s["sample_rejected"]:
                    raise ValueError("Accepted/rejected mismatch: " + source)
                if s["sample_accepted"] != actual:
                    raise ValueError("Accepted/indexed mismatch: " + source)
            elif d == "fema_transport":
                if (m["total_raw_observations"] !=
                        m["total_accepted_observations"] + m["total_rejected_observations"] or
                        m["total_accepted_observations"] != actual):
                    raise ValueError("FEMA transport count mismatch")
            elif (m["sample_raw"] != m["sample_accepted"] + m["sample_rejected"] or
                  m["sample_accepted"] != actual):
                raise ValueError("Accepted/rejected mismatch: " + d)
            tables[source] = {"indexed_observations": actual}
        report["source_directories"][d] = {
            "preserved_source_response_count": len(retained),
            "source_response_hashes": retained,
            "tables": tables,
        }
    if not report["source_directories"]:
        raise ValueError("No Lane A source manifests to verify")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="data/lane_a")
    args = parser.parse_args(argv)
    try:
        report = verify_dir(args.root)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, sqlite3.Error) as exc:
        print("LANE_A_ARTIFACT_QA_FAILED=" + str(exc), file=sys.stderr)
        return 2
    print("LANE_A_ARTIFACT_QA_PASS=" + json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
