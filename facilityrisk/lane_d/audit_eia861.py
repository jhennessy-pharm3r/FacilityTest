"""Independent source-row/index audit for official Lane D EIA-861 staging.

Unlike the importer, this verifier independently re-opens original Excel/CSV
source sheets, compares accepted original cell strings and row digests against
JSONL and SQLite staging, and records geographies/nulls/duplicate candidates.
Never claims site verification or production installation.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import zipfile

from .ingest_eia861 import cell, row_digest, table_rows, sha256


DATASETS = ("reliability", "state_total", "service_territory")
NULLS = {"", ".", "n/a", "na", "nan", "none", "null", "--"}


def file_hash(path):
    hash_obj = hashlib.sha256()
    with Path(path).open("rb") as inp:
        for chunk in iter(lambda: inp.read(1024*1024), b""):
            hash_obj.update(chunk)
    return hash_obj.hexdigest()


def audit(archive, folder):
    archive, folder = Path(archive), Path(folder)
    manifest = json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    if file_hash(archive) != manifest["archive_sha256"]:
        raise ValueError("Original archive hash does not match normalized manifest")
    by_kind = {}
    with zipfile.ZipFile(archive) as source:
        for member in manifest["members"]:
            raw = source.read(member["path"])
            if sha256(raw) != member["sha256"]:
                raise ValueError("Original EIA member SHA-256 changed")
        original_rows = {}
        for sheet in manifest["sheets"]:
            member_name = sheet["source_member"]
            for name, rows in table_rows(member_name, source.read(member_name)):
                if name == sheet["source_sheet"]:
                    original_rows[(member_name,name)] = rows
                    if len(rows) != sheet["physical_row_count"]:
                        raise ValueError("Actual workbook sheet row count differs from recorded")
                    break
            else:
                raise ValueError("Source worksheet not found in original ZIP")
    states, counties = set(), set()
    invalid_measurements = []
    missing_country_coords, no_metrics = 0, 0
    null_fields = Counter()
    natural = Counter()
    sha_by_kind, count_by_kind = {}, {}
    row_ids = set()
    for kind in DATASETS:
        path = folder/("eia861_" + kind + ".jsonl")
        sha_by_kind[kind] = file_hash(path)
        count_by_kind[kind] = 0
        with path.open("r",encoding="utf-8") as infile:
            for raw_line in infile:
                rec = json.loads(raw_line)
                count_by_kind[kind] += 1
                rowid = rec["ingestion_row_key"]
                if rowid in row_ids:
                    raise ValueError("Duplicate staged ingestion key")
                row_ids.add(rowid)
                if rec["source_kind"] != kind or rec["facility_match_status"] != "NOT_ASSESSED":
                    raise ValueError("Source-kind/facility review-state corruption")
                original = original_rows[(rec["source_member"],rec["source_sheet"])]
                source_row = original[rec["source_sheet_row"]-1]
                fields = [cell(c) for c in source_row]
                if fields != rec["raw_cells"]:
                    raise ValueError("Accepted data does not match original EIA XLSX cells")
                if row_digest(fields) != rec["row_sha256"]:
                    raise ValueError("Source row SHA-256 fails reproduction")
                state = rec["reported_state"]
                if not re.fullmatch(r"[A-Z]{2}",state):
                    raise ValueError("Invalid state code accepted")
                states.add(state)
                if kind=="service_territory":
                    county=rec.get("reported_county")
                    if county:
                        counties.add((state,county))
                    else:
                        null_fields["empty_service_county"]+=1
                    natural[(rec["source_utility_id"],state,county)]+=1
                if kind=="reliability":
                    if rec.get("missing_reliability_metrics"):
                        no_metrics+=1
                    schema=next(s["columns"] for s in manifest["sheets"]
                                if s["source_member"]==rec["source_member"]
                                and s["source_sheet"]==rec["source_sheet"])
                    for i, meta in enumerate(schema):
                        label = meta["label"].lower()
                        if not any(x in label for x in ("saidi","saifi","caidi")):
                            continue
                        val=fields[i].lower() if i<len(fields) else ""
                        if val in NULLS:
                            continue
                        try:
                            decimal=Decimal(val.replace(",",""))
                            if decimal.is_nan() or decimal<0 or decimal.is_infinite():
                                raise InvalidOperation
                        except InvalidOperation:
                            invalid_measurements.append({
                                "worksheet":rec["source_sheet"], "row":rec["source_sheet_row"],
                                "column":meta["column_1based"], "value":val})
    if count_by_kind != manifest["accepted_by_source_kind"]:
        raise ValueError("Normalized JSONL count disagreement")
    if sum(count_by_kind.values())!=manifest["accepted"]:
        raise ValueError("Accepted count does not reconcile")
    rejected = [json.loads(line) for line in (folder/"eia861_rejected.jsonl").read_text(encoding="utf-8").splitlines()]
    if len(rejected)!=manifest["rejected"]:
        raise ValueError("Source rejections do not reconcile")
    rejected_by_reason=Counter()
    for rec in rejected:
        raw = original_rows[(rec["source_member"],rec["source_sheet"])]
        fields = [cell(v) for v in raw[rec["source_sheet_row"]-1]]
        if fields != rec["raw_cells"] or row_digest(fields)!=rec["row_sha256"]:
            raise ValueError("Rejected source row does not match official origin")
        rejected_by_reason[rec["reason"]]+=1
    if dict(rejected_by_reason)!=manifest["rejection_reasons"]:
        raise ValueError("Actual rejection reasons differ from manifest")
    duplicate_territory_keys={str(k):v for k,v in natural.items() if v>1}
    with sqlite3.connect(folder/"lane_d_eia861_staging.sqlite") as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise ValueError("SQLite index integrity check failed")
        indexed=db.execute("SELECT source_kind,COUNT(*) FROM source_observations GROUP BY source_kind").fetchall()
        indexed_by_kind=dict(indexed)
        if indexed_by_kind != count_by_kind:
            raise ValueError("SQLite count differs from normalized JSONL")
        indexed_ids={r[0] for r in db.execute("SELECT ingestion_row_key FROM source_observations")}
        if indexed_ids != row_ids:
            raise ValueError("Local index IDs not reproducible from normalized rows")
        # Independently match source row fingerprint and provenance for each index entry.
        indexed_fingerprints={(r[0],r[1],r[2],r[3]) for r in db.execute(
            "SELECT ingestion_row_key,source_member,source_sheet,row_sha256 FROM source_observations")}
    if len(indexed_fingerprints)!=len(row_ids):
        raise ValueError("Index provenance is not unique")
    if invalid_measurements:
        raise ValueError("Official reliability workbook contains nonnumeric or negative metric values: "
                         + json.dumps(invalid_measurements[:5]))
    return {
        "source": "EIA861_INDEPENDENT_ORIGINAL_TO_STAGING_AUDIT",
        "archive_sha256": manifest["archive_sha256"],
        "archive_bytes": archive.stat().st_size,
        "reporting_year": manifest["reporting_year"],
        "original_sheets_audited":len(original_rows),
        "actual_accepted":count_by_kind,
        "actual_rejected":len(rejected),
        "rejected_reasons":dict(rejected_by_reason),
        "staged_indexed":indexed_by_kind,
        "normalized_jsonl_sha256":sha_by_kind,
        "geographic_state_codes":sorted(states),
        "distinct_state_codes":len(states),
        "distinct_state_county_pairs":len(counties),
        "missing_service_county":null_fields["empty_service_county"],
        "service_territory_duplicate_native_keys_count":len(duplicate_territory_keys),
        "service_territory_duplicate_native_keys_examples":list(duplicate_territory_keys.items())[:20],
        "reliability_rows_without_metrics":no_metrics,
        "invalid_reliability_numeric_metrics":len(invalid_measurements),
        "source_or_index_mismatches":0,
        "local_index_integrity_check":"ok",
        "physical_insured_site_matches_verified":0,
        "deployed":0,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--zip",type=Path,required=True)
    p.add_argument("--normalized",type=Path,required=True)
    p.add_argument("--receipt",type=Path,required=True)
    args=p.parse_args()
    report=audit(args.zip,args.normalized)
    args.receipt.parent.mkdir(parents=True,exist_ok=True)
    args.receipt.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__ == "__main__":
    main()
