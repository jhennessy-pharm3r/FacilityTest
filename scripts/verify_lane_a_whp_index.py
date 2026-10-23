"""Independent reconciliation of real USDA WHP2023 geographical summary source ZIP.

Checks the exact official ZIP bytes, retained XLSX file SHA-256, deterministic
normalized NDJSON.gz rows and indexed source keys/NULL-coverage states.
No physical facility, raster pixel or insurance loss counts are inferred.
"""
import argparse
import gzip
import hashlib
import io
import json
import pathlib
import sqlite3
import sys
import zipfile

def sha256(raw):
    return hashlib.sha256(raw).hexdigest()

def verify(original_zip, indexed_directory):
    indexed_directory = pathlib.Path(indexed_directory)
    original_zip = pathlib.Path(original_zip)
    m = json.loads((indexed_directory / "manifest.json").read_text(encoding="utf-8"))
    if sha256(original_zip.read_bytes()) != m["source_zip_sha256"]:
        raise ValueError("Original official USDA source ZIP SHA256 mismatch")
    with zipfile.ZipFile(original_zip) as archive:
        for k, detail in m["workbooks"].items():
            raw = archive.read(detail["source_workbook"])
            if sha256(raw) != detail["original_xlsx_sha256"]:
                raise ValueError("Original USDA XLSX SHA256 mismatch: " + k)
    gz = indexed_directory / m["normalized_gzip_filename"]
    if sha256(gz.read_bytes()) != m["normalized_gzip_sha256"]:
        raise ValueError("Normalized USDA NDJSON gzip SHA256 mismatch")
    emitted = 0
    ids = set()
    noncovered = 0
    by_geography = {}
    with gzip.open(gz, "rt", encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            key = (record["source_geography_type"], record["native_geographic_id"])
            if key in ids:
                raise ValueError("Duplicate normalized source geographies")
            ids.add(key)
            emitted += 1
            if record["source_coverage"] == "UNKNOWN_NO_AREA_VALUES":
                noncovered += 1
            if not record["source_workbook"] or len(record["original_xlsx_sha256"]) != 64:
                raise ValueError("Normalized row missing official source provenance")
            if record["original_archive_sha256"] != m["source_zip_sha256"]:
                raise ValueError("Normalized source archive checksum does not reconcile")
            by_geography[key[0]] = by_geography.get(key[0], 0) + 1
    con = sqlite3.connect("file:" + str((indexed_directory / m["source_only_index_filename"]).resolve()) + "?mode=ro", uri=True)
    try:
        quick = con.execute("PRAGMA quick_check").fetchone()[0]
        indexed = con.execute("SELECT COUNT(*) FROM whp2023_geography").fetchone()[0]
        missing = con.execute(
            "SELECT COUNT(*) FROM whp2023_geography WHERE coverage_state='UNKNOWN_NO_AREA_VALUES'"
        ).fetchone()[0]
        stored_geo = dict(con.execute("SELECT geography_type,COUNT(*) FROM whp2023_geography GROUP BY 1"))
        dupes = con.execute(
            "SELECT COUNT(*) FROM (SELECT geography_type,native_geographic_id,COUNT(*) c "
            "FROM whp2023_geography GROUP BY 1,2 HAVING c>1)").fetchone()[0]
    finally:
        con.close()
    if (quick != "ok" or dupes or indexed != emitted or
            indexed != m["normalized_records"] or
            missing != noncovered or missing != m["source_coverage_missing"] or
            stored_geo != by_geography or
            m["source_records_read"] != m["normalized_records"] + m["rejected_records"] or
            not m["reconciled"]):
        raise ValueError("USDA official index reconciliation failed")
    return {
        "official_zip_sha256_verified": m["source_zip_sha256"],
        "workbook_sha256_verified": len(m["workbooks"]),
        "normalized_gzip_sha256_verified": m["normalized_gzip_sha256"],
        "source_rows_read": m["source_records_read"], "normalized": emitted,
        "rejected": m["rejected_records"], "unknown_raster_coverage": missing,
        "sqlite_indexed": indexed, "by_geography": stored_geo,
        "sqlite_integrity": quick,
        "full_national_270m_raster": False, "insurer_site_matches": 0,
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--source", default="data/lane_a/whp_official_summary/whp2023_official_summaries.zip")
    p.add_argument("--index-dir", default="data/lane_a/whp_official_index")
    args = p.parse_args(argv)
    try:
        result = verify(args.source, args.index_dir)
    except (OSError, ValueError, sqlite3.Error, KeyError, json.JSONDecodeError) as exc:
        print("LANE_A_USDA_INDEX_VERIFY_FAILED=" + str(exc), file=sys.stderr)
        return 2
    print("LANE_A_USDA_INDEX_VERIFY_PASS=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
