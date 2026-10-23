"""Cross-source ID agreement audit only, no canonical facility merge.

ECHO REGISTRY_ID and TRI "3. FRS ID" are regulator-reported source keys.
Exact key equality is a candidate relation, NOT reviewed physical property.
"""
import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

def sha(path):
    digest=hashlib.sha256()
    with Path(path).open("rb") as data:
        for chunk in iter(lambda:data.read(1048576),b""):digest.update(chunk)
    return digest.hexdigest()

def candidate_audit(echo_zip,tri_csv,report_year):
    if not isinstance(report_year,int) or not 1987<=report_year<=2024:
        raise ValueError("Published year required")
    archive=Path(echo_zip)
    tri=Path(tri_csv)
    if not archive.is_file() or not tri.is_file():
        raise FileNotFoundError("Both original official source files are required")
    with ZipFile(archive) as z:
        targets=[member for member in z.namelist() if member.endswith("ECHO_EXPORTER.csv")]
        if len(targets)!=1:raise ValueError("Exact official ECHO_EXPORTER.csv archive member required")
        with z.open(targets[0]) as raw:
            reader=csv.DictReader(io.TextIOWrapper(raw,encoding="utf-8-sig",errors="replace",newline=""))
            if "REGISTRY_ID" not in (reader.fieldnames or []):
                raise ValueError("Official ECHO REGISTRY_ID missing")
            registry=set()
            echo_rows=echo_keyless=echo_duplicates=0
            for row in reader:
                echo_rows+=1
                key=(row.get("REGISTRY_ID") or "").strip()
                if not key:echo_keyless+=1
                elif key in registry:echo_duplicates+=1
                else:registry.add(key)
    with tri.open(encoding="utf-8-sig",errors="replace",newline="") as f:
        reader=csv.DictReader(f)
        if not {"1. YEAR","2. TRIFD","3. FRS ID"}.issubset(reader.fieldnames or []):
            raise ValueError("Official native TRI year, TRIFD and FRS source ID fields required")
        rows=missing_frs=missing_trifd=year_mismatch=matching=not_in_echo=0
        distinct_native_tri=set()
        all_frs=set();matched_frs=set();unmatched_frs=set()
        tri_without_key=set();linked_tri=set()
        for row in reader:
            rows+=1
            if (row.get("1. YEAR") or "").strip()!=str(report_year):year_mismatch+=1
            native=(row.get("2. TRIFD") or "").strip()
            frs=(row.get("3. FRS ID") or "").strip()
            if not native:missing_trifd+=1
            else:distinct_native_tri.add(native)
            if not frs:
                missing_frs+=1
                if native:tri_without_key.add(native)
            else:
                all_frs.add(frs)
                if frs in registry:
                    matching+=1
                    matched_frs.add(frs)
                    if native:linked_tri.add(native)
                else:
                    not_in_echo+=1;unmatched_frs.add(frs)
    if year_mismatch:
        raise ValueError(f"TRI file does not match requested year: {year_mismatch} records")
    if not echo_rows or not rows or missing_trifd:
        raise ValueError("ECHO/TRI source identity audit not complete; missing native IDs")
    if echo_rows!=len(registry)+echo_keyless+echo_duplicates:
        raise AssertionError("ECHO native identity reconciliation failure")
    if rows!=matching+not_in_echo+missing_frs:
        raise AssertionError("TRI reported FRS key reconciliation failure")
    return dict(
        source_pair="EPA ECHO FRS registry-ID vs TRI annual reported FRS ID",
        source_year=report_year,
        source_grain="One ECHO FRS identity and per-chemical TRI reports; neither is reviewed physical site",
        original_echo_sha256=sha(archive),original_tri_sha256=sha(tri),
        echo_raw_rows=echo_rows,echo_native_registry_ids=len(registry),
        echo_rows_missing_registry_id=echo_keyless,echo_duplicate_native_registry_ids=echo_duplicates,
        tri_raw_reports=rows,tri_distinct_native_trifd=len(distinct_native_tri),
        tri_missing_reported_frs_id_rows=missing_frs,
        tri_reports_exact_frs_key_in_echo=matching,
        tri_reports_frs_key_absent_in_echo=not_in_echo,
        distinct_tri_reported_frs_ids=len(all_frs),
        distinct_tri_reported_frs_ids_in_echo=len(matched_frs),
        distinct_tri_reported_frs_ids_not_in_echo=len(unmatched_frs),
        distinct_tri_reporters_with_exact_frs_key_match=len(linked_tri),
        distinct_tri_reporters_with_at_least_one_missing_frs_key=len(tri_without_key),
        original_source_identity_relation="EXACT_REGULATOR_ID_ONLY_REVIEW_REQUIRED",
        physical_property_matches_verified=0,insurance_losses_verified=0,
        production_deployed_records=0,
        caveat="FRS source identifier agreement is a review-only candidate relation, not a verified site/parcel/property, clean risk or insurance claim"
    )
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--echo-zip",required=True)
    p.add_argument("--tri-csv",required=True)
    p.add_argument("--year",type=int,required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    result=candidate_audit(args.echo_zip,args.tri_csv,args.year)
    path=Path(args.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("VERIFIED_OFFICIAL_SOURCE_ID_CANDIDATES",json.dumps(result,sort_keys=True))
if __name__=="__main__":main()
