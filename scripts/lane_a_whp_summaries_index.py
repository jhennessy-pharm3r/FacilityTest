"""Normalize USDA WHP 2023 official summary XLSX source rows without Excel dependencies.

The source archive contains geographic area summaries, *not* property or site
observations. Native source IDs: 5-character county GEOID, 2-character state
FIPS, and 5-character ZIP. Preserve original rows, unknown coverage, and SHA.
"""
import argparse
import gzip
import hashlib
import io
import json
import math
import pathlib
import re
import sqlite3
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

SHEETS = {
    "county": ("WHP2023_County_Summary.xlsx", "GEOID", "STUSPS", "NAME"),
    "state": ("WHP2023_State_Summary.xlsx", "STATE_FIPS", "STATE_ABBR", "STATE_NAME"),
    "zip": ("WHP2023_ZipCode_Summary.xlsx", "ZIP", "STATE", "PO_NAME"),
}
ACRES = ("VH Acres", "H Acres", "M Acres", "L Acres", "VL Acres", "NB Acres", "W Acres")
MANAGEMENT_MEMBER = "WHP2023_ManagementJurisdiction_Summary.xlsx"
MANAGEMENT_ACRE_COLS = {
    "VH Acres": "Very High WHP", "H Acres": "High WHP",
    "M Acres": "Moderate WHP", "L Acres": "Low WHP",
    "VL Acres": "Very Low WHP", "NB Acres": "Non-burnable",
    "W Acres": "Water",
}
MANAGEMENT_ROUNDING_TOLERANCE_ACRES = 3000.0
XML_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
MAX_XLSX_BYTES = 45 * 1024 * 1024


def colnum(cellref):
    letters = re.match(r"^[A-Z]+", cellref)
    if not letters:
        raise ValueError("Invalid XLSX cell coordinate: " + cellref)
    n = 0
    for c in letters.group(0):
        n = n * 26 + ord(c) - 64
    return n - 1


def xml_shared_strings(book):
    if "xl/sharedStrings.xml" not in book.namelist():
        return []
    with book.open("xl/sharedStrings.xml") as src:
        root = ET.parse(src).getroot()
    return ["".join(t.text or "" for t in si.iter(XML_NS + "t"))
            for si in root.findall(XML_NS + "si")]


def sheet1_rows(xlsx_bytes):
    """Yield row number / positional cell values; Excel display formatting is not used."""
    if len(xlsx_bytes) > MAX_XLSX_BYTES:
        raise ValueError("Unexpectedly large workbook")
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as book:
        shared = xml_shared_strings(book)
        filename = "xl/worksheets/sheet1.xml"
        if filename not in book.namelist():
            raise ValueError("Required source first worksheet missing")
        with book.open(filename) as f:
            for _, elem in ET.iterparse(f, events=("end",)):
                if elem.tag != XML_NS + "row":
                    continue
                row_num = int(elem.attrib.get("r", "0"))
                values = {}
                for cell in elem.findall(XML_NS + "c"):
                    ref = cell.attrib.get("r", "")
                    idx = colnum(ref)
                    typ = cell.attrib.get("t")
                    v = cell.find(XML_NS + "v")
                    inline = cell.find(XML_NS + "is")
                    if typ == "s" and v is not None:
                        value = shared[int(v.text or "0")]
                    elif typ == "inlineStr" and inline is not None:
                        value = "".join(t.text or "" for t in inline.iter(XML_NS + "t"))
                    elif typ in ("str", "e") and v is not None:
                        value = v.text
                    elif typ == "b" and v is not None:
                        value = (v.text == "1")
                    elif v is not None and v.text not in ("", None):
                        try:
                            value = float(v.text)
                        except ValueError:
                            value = v.text
                    else:
                        value = None
                    values[idx] = value
                width = max(values, default=-1) + 1
                row = [values.get(i) for i in range(width)]
                yield row_num, row
                elem.clear()


def parse_amount(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("Invalid USDA WHP acreage quantity")
    if not math.isfinite(number) or number < 0:
        raise ValueError("Invalid negative/nonfinite USDA WHP acreage")
    return number


def normalize(geography, data, source_row):
    member, id_col, state_col, name_col = SHEETS[geography]
    raw_id = data.get(id_col)
    if raw_id is None:
        raise ValueError("Missing original geographic source ID")
    if geography == "state":
        value = str(int(float(raw_id))).zfill(2)
        if len(value) != 2:
            raise ValueError("Invalid 2-character state FIPS")
    else:
        value = str(raw_id)
        if value.endswith(".0"):
            value = value[:-2]
        if len(value) != 5 or not value.isdigit():
            raise ValueError("Invalid original 5-character " + geography + " ID")
    acreage = {col: parse_amount(data.get(col)) for col in ACRES}
    area = parse_amount(data.get("Total Acres"))
    supplied = [acreage[k] for k in ACRES]
    all_null = all(v is None for v in supplied) and area is None
    if not all_null and (any(v is None for v in supplied) or area is None):
        raise ValueError("Partially missing WHP acreage; requires source review")
    if not all_null:
        if abs(sum(supplied) - area) > max(5.0, area * 0.00001):
            raise ValueError("Original USDA WHP acreage components do not reconcile")
    state = str(data.get(state_col) or "").strip().upper()
    if not state:
        raise ValueError("Missing geographic state abbreviation")
    label = str(data.get(name_col) or "").strip()
    if not label:
        raise ValueError("Missing source geographic name")
    return {
        "source_geography_type": geography,
        "native_geographic_id": value,
        "state": state,
        "original_source_name": label,
        "whp2023_landscape_year": 2020,
        "whp_product_year": 2023,
        "source_workbook": member,
        "source_excel_row": source_row,
        "area_unit": "acres",
        "acreages": acreage,
        "total_acres": area,
        "source_coverage": "UNKNOWN_NO_AREA_VALUES" if all_null else "AGGREGATE_AREA_VALUES",
        "raw_source_columns": data,
        "site_verified": False,
        "insurance_loss_or_probability": False,
    }


def normalize_management(data, source_row):
    label = str(data.get("Management Jurisdiction") or "").strip()
    if not label:
        raise ValueError("Missing original management-jurisdiction label")
    acres = {k: parse_amount(data.get(source_col))
             for k, source_col in MANAGEMENT_ACRE_COLS.items()}
    total = parse_amount(data.get("Total Acres"))
    if total is None or any(value is None for value in acres.values()):
        raise ValueError("Missing publisher management acreage")
    difference = sum(acres.values()) - total
    if abs(difference) > MANAGEMENT_ROUNDING_TOLERANCE_ACRES:
        raise ValueError("Management acres exceed 3000-acre publisher rounding allowance")
    return {
        "source_geography_type": "management_jurisdiction",
        "source_identity_type": "publisher_label_no_geographic_id",
        "native_geographic_id": label,
        "state": None, "original_source_name": label,
        "source_workbook": MANAGEMENT_MEMBER,
        "source_excel_row": source_row, "whp_product_year": 2023,
        "whp2023_landscape_year": 2020,
        "acreages": acres, "total_acres": total, "area_unit": "acres",
        "publisher_rounding_difference_acres": difference,
        "publisher_rounding_tolerance_acres": MANAGEMENT_ROUNDING_TOLERANCE_ACRES,
        "source_coverage": "AGGREGATE_AREA_VALUES",
        "is_publisher_grand_total": label.casefold() == "grand total",
        "not_site_or_independent_geographic_polygon": True,
        "raw_source_columns": data,
        "site_verified": False, "insurance_loss_or_probability": False,
    }


def init_db(path):
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS whp2023_geography(
          geography_type TEXT NOT NULL, native_geographic_id TEXT NOT NULL,
          state TEXT NOT NULL, geography_name TEXT NOT NULL,
          coverage_state TEXT NOT NULL, total_acres REAL,
          source_workbook TEXT NOT NULL, source_excel_row INTEGER NOT NULL,
          source_workbook_sha256 TEXT NOT NULL, source_zip_sha256 TEXT NOT NULL,
          raw_row_json TEXT NOT NULL,
          PRIMARY KEY (geography_type,native_geographic_id)
        );
        CREATE INDEX IF NOT EXISTS whp2023_by_state ON whp2023_geography(state,geography_type);
        CREATE INDEX IF NOT EXISTS whp2023_by_coverage ON whp2023_geography(coverage_state);
        CREATE TABLE IF NOT EXISTS whp2023_management(
            source_label TEXT PRIMARY KEY,
            is_grand_total INTEGER NOT NULL, total_acres REAL NOT NULL,
            source_workbook TEXT NOT NULL, source_excel_row INTEGER NOT NULL,
            source_workbook_sha256 TEXT NOT NULL, source_zip_sha256 TEXT NOT NULL,
            raw_row_json TEXT NOT NULL
        );
    """)
    return db


def run(source_zip, out_dir):
    source_zip = pathlib.Path(source_zip)
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    original = source_zip.read_bytes()
    if not zipfile.is_zipfile(io.BytesIO(original)):
        raise ValueError("Expected original official USFS source ZIP")
    source_zip_sha = hashlib.sha256(original).hexdigest()
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "publisher": "USDA Forest Service", "source_file": source_zip.name,
        "source_zip_sha256": source_zip_sha, "source_zip_bytes": len(original),
        "whp_release": "2023 revised 2024-07-17", "landscape_inputs_as_of": "2020",
        "scope": "official nationwide administrative polygon summary rows, NOT original 270m raster, physical facility registry or site risk",
        "source_complete_national_raster": False, "physical_facilities_matched": 0,
        "deployed_count": 0, "workbooks": {}, "source_records_read": 0,
        "normalized_records": 0, "rejected_records": 0, "source_coverage_missing": 0,
        "aggregate_area_records": 0, "duplicate_source_keys": 0,
        "rejected_examples": [], "state_codes_covered": [],
        "source_only_index_filename": "whp2023-source-geographies.sqlite",
        "normalized_gzip_filename": "whp2023-source-geographies.ndjson.gz",
    }
    db = init_db(out_dir / manifest["source_only_index_filename"])
    states = set()
    normalized = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as archive, gzip.GzipFile(
        fileobj=normalized, mode="wb", mtime=0, filename=""
    ) as stream:
        for geo, (member, id_col, state_col, name_col) in SHEETS.items():
            if member not in archive.namelist():
                raise ValueError("Missing required official workbook: " + member)
            raw_workbook = archive.read(member)
            workbook_sha = hashlib.sha256(raw_workbook).hexdigest()
            report = {"source_workbook": member, "original_xlsx_sha256": workbook_sha,
                      "original_bytes": len(raw_workbook), "source_rows_read": 0,
                      "accepted": 0, "rejected": 0,
                      "coverage_missing": 0, "source_keys_duplicated": 0}
            manifest["workbooks"][geo] = report
            cols = None
            for rownum, raw_row in sheet1_rows(raw_workbook):
                if rownum < 3:
                    continue
                if rownum == 3:
                    cols = [str(k).strip() if k is not None else None
                            for k in raw_row]
                    if not {id_col, state_col, name_col, "Total Acres"}.issubset(set(cols)):
                        raise ValueError("WHP official " + geo + " worksheet schema unexpectedly changed")
                    if not set(ACRES).issubset(set(cols)):
                        raise ValueError("WHP source acreage columns missing")
                    report["source_column_names"] = [c for c in cols if c]
                    continue
                if not any(v is not None for v in raw_row):
                    continue
                data = {key: (raw_row[idx] if idx < len(raw_row) else None)
                        for idx, key in enumerate(cols) if key}
                report["source_rows_read"] += 1
                manifest["source_records_read"] += 1
                try:
                    record = normalize(geo, data, rownum)
                    record["original_xlsx_sha256"] = workbook_sha
                    record["original_archive_sha256"] = source_zip_sha
                    db.execute(
                        "INSERT INTO whp2023_geography VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (geo, record["native_geographic_id"], record["state"],
                         record["original_source_name"], record["source_coverage"],
                         record["total_acres"], member, rownum,
                         workbook_sha, source_zip_sha,
                         json.dumps(record, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False)),
                    )
                    stream.write((json.dumps(record, sort_keys=True,
                                ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
                    states.add(record["state"])
                    report["accepted"] += 1
                    manifest["normalized_records"] += 1
                    if record["source_coverage"] == "UNKNOWN_NO_AREA_VALUES":
                        manifest["source_coverage_missing"] += 1
                        report["coverage_missing"] += 1
                    else:
                        manifest["aggregate_area_records"] += 1
                except (ValueError, sqlite3.IntegrityError) as exc:
                    report["rejected"] += 1
                    manifest["rejected_records"] += 1
                    if isinstance(exc, sqlite3.IntegrityError):
                        report["source_keys_duplicated"] += 1
                        manifest["duplicate_source_keys"] += 1
                    if len(manifest["rejected_examples"]) < 100:
                        manifest["rejected_examples"].append({
                            "workbook": member, "rownum": rownum, "reason": str(exc)[:250]})

        # Publisher workbook 4: ownership categories, not physical sites.
        if MANAGEMENT_MEMBER not in archive.namelist():
            raise ValueError("Missing required official management workbook")
        original_management = archive.read(MANAGEMENT_MEMBER)
        management_sha = hashlib.sha256(original_management).hexdigest()
        management_report = {
            "source_workbook": MANAGEMENT_MEMBER,
            "original_xlsx_sha256": management_sha,
            "original_bytes": len(original_management),
            "source_rows_read": 0, "accepted": 0, "rejected": 0,
            "coverage_missing": 0, "source_keys_duplicated": 0,
            "grand_total_rows": 0, "acreage_rounding_tolerance": 3000.0,
        }
        manifest["workbooks"]["management_jurisdiction"] = management_report
        cols = None
        required = {"Management Jurisdiction", "Total Acres"} | set(MANAGEMENT_ACRE_COLS.values())
        for rownum, raw_row in sheet1_rows(original_management):
            if rownum < 3:
                continue
            if rownum == 3:
                cols = [str(k).strip() if k is not None else None for k in raw_row]
                if not required.issubset(set(cols)):
                    raise ValueError("WHP management worksheet missing original source columns")
                management_report["source_column_names"] = [col for col in cols if col]
                continue
            if not any(v is not None for v in raw_row):
                continue
            data = {key: (raw_row[idx] if idx < len(raw_row) else None)
                    for idx, key in enumerate(cols) if key}
            management_report["source_rows_read"] += 1
            manifest["source_records_read"] += 1
            try:
                record = normalize_management(data, rownum)
                record["original_xlsx_sha256"] = management_sha
                record["original_archive_sha256"] = source_zip_sha
                db.execute(
                    "INSERT INTO whp2023_management VALUES (?,?,?,?,?,?,?,?)",
                    (record["native_geographic_id"], int(record["is_publisher_grand_total"]),
                     record["total_acres"], MANAGEMENT_MEMBER, rownum,
                     management_sha, source_zip_sha,
                     json.dumps(record, sort_keys=True, separators=(",", ":"),
                                ensure_ascii=False)),
                )
                stream.write((json.dumps(record, sort_keys=True,
                                        ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
                management_report["accepted"] += 1
                manifest["normalized_records"] += 1
                manifest["aggregate_area_records"] += 1
                if record["is_publisher_grand_total"]:
                    management_report["grand_total_rows"] += 1
            except (ValueError, sqlite3.IntegrityError) as exc:
                management_report["rejected"] += 1
                manifest["rejected_records"] += 1
                if isinstance(exc, sqlite3.IntegrityError):
                    management_report["source_keys_duplicated"] += 1
                    manifest["duplicate_source_keys"] += 1
                if len(manifest["rejected_examples"]) < 100:
                    manifest["rejected_examples"].append({
                        "workbook": MANAGEMENT_MEMBER, "rownum": rownum,
                        "reason": str(exc)[:250]})

    (out_dir / manifest["normalized_gzip_filename"]).write_bytes(normalized.getvalue())
    manifest["normalized_gzip_sha256"] = hashlib.sha256(normalized.getvalue()).hexdigest()
    db.commit()
    manifest["source_only_indexed_geographies"] = db.execute(
        "SELECT COUNT(*) FROM whp2023_geography").fetchone()[0]
    manifest["source_only_indexed_management"] = db.execute(
        "SELECT COUNT(*) FROM whp2023_management").fetchone()[0]
    manifest["source_only_indexed_records"] = (
        manifest["source_only_indexed_geographies"] + manifest["source_only_indexed_management"]
    )
    manifest["management_grand_total_rows"] = db.execute(
        "SELECT COUNT(*) FROM whp2023_management WHERE is_grand_total=1"
    ).fetchone()[0]
    manifest["source_only_null_area"] = db.execute(
        "SELECT COUNT(*) FROM whp2023_geography WHERE coverage_state='UNKNOWN_NO_AREA_VALUES'").fetchone()[0]
    manifest["source_unique_geography_counts"] = dict(db.execute(
        "SELECT geography_type,COUNT(*) FROM whp2023_geography GROUP BY geography_type").fetchall())
    manifest["source_unique_geography_counts"]["management_jurisdiction"] = (
        manifest["source_only_indexed_management"]
    )
    manifest["sql_quick_check"] = db.execute("PRAGMA quick_check").fetchone()[0]
    db.close()
    manifest["state_codes_covered"] = sorted(states)
    manifest["reconciled"] = bool(
        manifest["normalized_records"] + manifest["rejected_records"] == manifest["source_records_read"] and
        manifest["normalized_records"] == manifest["source_only_indexed_records"] and
        manifest["source_coverage_missing"] == manifest["source_only_null_area"] and
        manifest["source_coverage_missing"] + manifest["aggregate_area_records"] == manifest["normalized_records"] and
        manifest["management_grand_total_rows"] == manifest["workbooks"]["management_jurisdiction"]["grand_total_rows"] and
        manifest["sql_quick_check"] == "ok" and
        all(len(w["source_column_names"]) >= (9 if kind == "management_jurisdiction" else 11)
            for kind, w in manifest["workbooks"].items())
    )
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--source", default="data/lane_a/whp_official_summary/whp2023_official_summaries.zip")
    p.add_argument("--out-dir", default="data/lane_a/whp_official_index")
    args = p.parse_args(argv)
    result = run(args.source, args.out_dir)
    print("LANE_A_USDA_GEO_INDEX=" + json.dumps({
        "source_rows": result["source_records_read"],
        "normalized": result["normalized_records"],
        "rejected": result["rejected_records"],
        "duplicate_keys": result["duplicate_source_keys"],
        "indexed": result["source_only_indexed_records"],
        "missing_area": result["source_coverage_missing"],
        "per_geography": result["source_unique_geography_counts"],
        "states_covered": len(result["state_codes_covered"]),
        "reconciled": result["reconciled"],
        "source_zip_sha256": result["source_zip_sha256"],
        "normalized_sha256": result["normalized_gzip_sha256"],
        "rejection_examples": result["rejected_examples"][:5],
    }, sort_keys=True))
    return 0 if result["reconciled"] and result["rejected_records"] == 0 and result["normalized_records"] > 30000 else 2


if __name__ == "__main__":
    sys.exit(main())
