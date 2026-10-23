"""Lane D: EIA-861 utility reliability source-preserving ingestion. Stdlib + openpyxl.

Run: python -m facilityrisk.lane_d.ingest_eia861 --year 2025 --output data/eia861
     python -m facilityrisk.lane_d.ingest_eia861 --zip path/to/f8612025.zip --year 2025 --output data/eia861
Never infer site-specific outages, service provider or insured losses from these rows.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
import urllib.request
import zipfile

SOURCE = "https://www.eia.gov/electricity/data/eia861/zip/f861{year}.zip"
SOURCE_PAGE = "https://www.eia.gov/electricity/data/eia861/"
HEADERS = {"utilitynumber", "utilityid", "utilitynumberid"}
NULLS = {"", ".", "na", "n/a", "nan", "null", "none"}
METRIC = ("saidi", "saifi", "caidi")

def canon(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())

def values(member, data):
    if member.lower().endswith(".csv"):
        text = io.StringIO(data.decode("utf-8-sig"))
        yield from csv.reader(text)
    elif member.lower().endswith((".xlsx", ".xlsm")):
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise RuntimeError("Install openpyxl to read official EIA Excel files") from exc
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        try:
            for sheet in wb:
                for row in sheet.iter_rows(values_only=True):
                    yield ["" if v is None else str(v) for v in row]
        finally:
            wb.close()
    else:
        raise ValueError("Unsupported workbook: " + member)

def find_header(rows):
    for i, row in enumerate(rows[:25]):
        normalized = [canon(x) for x in row]
        if any(x in HEADERS for x in normalized):
            return i, normalized
    raise ValueError("No EIA utility ID header in first 25 rows")

def normalize(member, contents, year):
    rows = list(values(member, contents))
    header_i, headers = find_header(rows)
    id_col = next(i for i, x in enumerate(headers) if x in HEADERS)
    names = [str(v).strip() for v in rows[header_i]]
    seen = set()
    accepted, rejected, duplicates = [], [], 0
    null_metrics = 0
    for line, row in enumerate(rows[header_i + 1:], start=header_i + 2):
        if not any(str(v).strip() for v in row):
            continue
        raw = dict(zip(names, [str(v).strip() for v in row]))
        uid = str(row[id_col]).strip() if id_col < len(row) else ""
        if not re.fullmatch(r"[0-9]+", uid):
            rejected.append({"source_member": member, "line": line, "reason": "invalid_utility_id", "raw": raw})
            continue
        # Multiple utility rows per year may differ by state, method or metric grouping.
        # Deduplicate exact rows only, never by utility ID.
        checksum = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
        if checksum in seen:
            duplicates += 1
            rejected.append({"source_member": member, "line": line, "reason": "duplicate_exact_row", "raw": raw})
            continue
        seen.add(checksum)
        fields = {canon(k): v for k, v in raw.items()}
        missing_metrics = all(not any(m in k and v.lower() not in NULLS for k, v in fields.items()) for m in METRIC)
        null_metrics += int(missing_metrics)
        accepted.append({"source": "EIA861", "source_year": year, "source_utility_id": uid,
                         "source_member": member, "source_sheet_row": line,
                         "row_sha256": checksum, "missing_reliability_metrics": missing_metrics,
                         "raw": raw, "evidence_type": "UTILITY_AGGREGATE_CONTEXT",
                         "facility_match_status": "NOT_ASSESSED"})
    return accepted, rejected, duplicates, null_metrics

def run(year, output, archive=None):
    if not 2013 <= year <= datetime.now(timezone.utc).year:
        raise ValueError("Outside EIA-861 reliability collection period")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    source_url = SOURCE.format(year=year)
    if archive:
        archive_path = Path(archive)
        if not archive_path.is_file():
            raise FileNotFoundError(archive)
    else:
        archive_path = output / ("f861%d.zip" % year)
        # Download atomically; no fallback to a previous vintage.
        tmp = archive_path.with_suffix(".zip.partial")
        try:
            with urllib.request.urlopen(urllib.request.Request(source_url, headers={"User-Agent": "FacilityRiskLaneD/1.0"}), timeout=90) as response, tmp.open("wb") as f:
                shutil.copyfileobj(response, f)
            tmp.replace(archive_path)
        finally:
            tmp.unlink(missing_ok=True)
    raw_sha = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    if not zipfile.is_zipfile(archive_path):
        raise ValueError("Downloaded content is not a ZIP archive")
    all_rows, all_bad, members = [], [], []
    with zipfile.ZipFile(archive_path) as z:
        for name in sorted(z.namelist()):
            if "reliability" not in name.lower() or not name.lower().endswith((".xlsx", ".xlsm", ".csv")):
                continue
            data = z.read(name)
            rows, bad, dup, null = normalize(name, data, year)
            all_rows.extend(rows)
            all_bad.extend(bad)
            members.append({"path": name, "sha256": hashlib.sha256(data).hexdigest(),
                            "accepted": len(rows), "rejected": len(bad),
                            "exact_duplicates": dup, "rows_without_metrics": null})
    if not members:
        raise ValueError("No EIA-861 reliability workbook found; inspect ZIP layout")
    def write_jsonl(path, objects):
        with path.open("w", encoding="utf-8") as f:
            for obj in objects:
                f.write(json.dumps(obj, sort_keys=True, ensure_ascii=False) + "\n")
    write_jsonl(output / "eia861_reliability.jsonl", all_rows)
    write_jsonl(output / "eia861_rejected.jsonl", all_bad)
    manifest = {
        "source": "EIA861", "publisher": "US Energy Information Administration",
        "source_page": SOURCE_PAGE, "source_url": source_url,
        "reporting_year": year, "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "input_origin": "local_official_archive" if archive else "official_download",
        "archive_sha256": raw_sha, "archive_bytes": archive_path.stat().st_size,
        "raw_archive_path": str(archive_path), "members": members,
        "accepted": len(all_rows), "rejected": len(all_bad),
        "unique_utility_ids": len({r["source_utility_id"] for r in all_rows}),
        "state": "NORMALIZED", "indexed": 0, "verified_facilities": 0, "deployed": 0,
        "coverage": "US electricity utility reporters, not an all-facility outage census",
        "limitations": ["Provider territories are not verified site service connections",
                        "Aggregated SAIDI/SAIFI do not establish facility outage/downtime",
                        "Major event inclusion and measurement method must be kept distinct",
                        "No insurance claim, utility coverage or business-interruption loss inference"] }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--zip", dest="archive", type=Path)
    args = p.parse_args()
    print(json.dumps(run(args.year, args.output, args.archive), indent=2))

if __name__ == "__main__":
    main()
