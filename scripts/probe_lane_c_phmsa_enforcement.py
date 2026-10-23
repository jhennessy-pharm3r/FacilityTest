"""Audit PHMSA's separately published pipeline *enforcement* raw data.

The PHMSA Work Management System enforcement-case dataset may carry native
incident Report_Type/Report_Number references. It is NOT the 30-day pipeline
incident report census or DOT Form 5800.1 transport data. Keep it distinct.
"""
from __future__ import annotations
from collections import Counter
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
from urllib.parse import urlsplit
import requests
try:
    from scripts.build_phmsa_enforcement import build,index_cases
    from scripts.lane_c_enforcement_install import package as package_private,install as install_private,query as query_private
except ModuleNotFoundError:
    from build_phmsa_enforcement import build,index_cases
    from lane_c_enforcement_install import package as package_private,install as install_private,query as query_private

URL = "https://primis.phmsa.dot.gov/enforcement-documents/PHMSA%20Pipeline%20Enforcement%20Raw%20Data.txt"
SOURCE = "PHMSA Pipeline Enforcement Raw Data, Work Management System 2026-10-02"
MAX_BYTES = 120_000_000

def fetch(path):
    sha = hashlib.sha256()
    size = 0
    with requests.get(URL, stream=True, timeout=(20,110),
                      headers={"User-Agent":"FacilityRisk-LaneC-OfficialSourceAudit/1.0",
                               "Accept-Encoding":"identity"}) as response:
        response.raise_for_status()
        endpoint = urlsplit(response.url)
        if endpoint.scheme != "https" or endpoint.hostname != "primis.phmsa.dot.gov":
            raise ValueError("Unexpected host or insecure PHMSA enforcement redirect")
        with path.open("wb") as stream:
            for chunk in response.iter_content(1024*1024):
                if not chunk: continue
                size += len(chunk)
                if size > MAX_BYTES: raise ValueError("Official enforcement file unexpectedly large")
                stream.write(chunk)
                sha.update(chunk)
    if size < 1024:
        raise ValueError("Official enforcement TXT unexpectedly empty")
    return size, sha.hexdigest()

def inspect(path):
    data = path.read_bytes()
    if data[:256].lstrip().lower().startswith((b"<!doctype",b"<html",b"<head")):
        raise ValueError("HTML substituted for official PHMSA TXT export")
    encoding=None
    text=None
    for candidate in ("utf-8-sig","cp1252","latin-1"):
        try:
            text=data.decode(candidate,errors="strict")
            encoding=candidate
            break
        except UnicodeDecodeError:
            pass
    if encoding is None:
        raise ValueError("Cannot decode official PHMSA enforcement text without replacement")
    rows=csv.reader(io.StringIO(text,newline=""),dialect="excel-tab")
    headers=[x.strip().lstrip("\ufeff") for x in next(rows)]
    if len(headers)<4 or len(set(headers))!=len(headers):
        raise ValueError("Unexpected PHMSA raw case export columns")
    counts=Counter()
    nonempty_per_column=Counter()
    null_key_examples=0
    distinct= {}
    case_key_candidates=[]
    report_field_candidates=[]
    for i,h in enumerate(headers):
        name=h.upper().replace(" ","_")
        if "CASE" in name and ("NUM" in name or "ID" in name):
            case_key_candidates.append(i)
        if "REPORT_NUMBER" in name or "REPORT_TYPE" in name or "OPID" in name:
            report_field_candidates.append(i)
    tracked={headers[i]:{"distinct":set(),"nonempty":0} for i in set(case_key_candidates+report_field_candidates)}
    total=0
    for row in rows:
        if not any(x.strip() for x in row):
            continue
        total+=1
        if len(row)!=len(headers):
            counts["wrong_column_count"]+=1
            continue
        for i in range(len(headers)):
            value=row[i].strip()
            if value:
                nonempty_per_column[headers[i]]+=1
                if headers[i] in tracked:
                    tracked[headers[i]]["nonempty"]+=1
                    tracked[headers[i]]["distinct"].add(value)
    if total<25:
        raise ValueError("Unexpectedly few PHMSA enforcement source table rows")
    return {
        "record_grain":"PHMSA WMS enforcement case/action rows, NOT all incidents",
        "text_encoding":encoding,
        "delimiter":"tab",
        "headers":headers,
        "observed_nonempty_rows":total,
        "invalid_column_count_rows":counts["wrong_column_count"],
        "columns_not_empty_counts":dict(sorted(nonempty_per_column.items())),
        "native_candidate_keys":{h:{
           "nonempty":v["nonempty"],
           "distinct_count":len(v["distinct"]),
           "duplicate_occurrences":v["nonempty"]-len(v["distinct"])
           } for h,v in tracked.items()},
        "report_linkage_fields":[headers[i] for i in report_field_candidates],
        "source_report_record_count":"NOT_VERIFIED_SEPARATE_PHMSA_CENSUS",
        "physical_site_links":0
    }
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--private-bundle-dir",type=Path,
        help="Private out-of-repository source bundle; never publish in CI artifact")
    p.add_argument("--install-test-root",type=Path,
        help="Precreated 0700 private dir; smoke-test real case source installer and bounded queries")
    args=p.parse_args()
    if args.install_test_root and not args.private_bundle_dir:
        raise ValueError("PHMSA case installation requires private source bundle")
    args.output.mkdir(parents=True,exist_ok=True)
    audit={"source":SOURCE,"url":URL,
           "retrieved_at":datetime.now(timezone.utc).isoformat(),
           "state":"NOT_TESTED","incident_source_rows":None,
           "phmsa_incident_census_indexed":0,"deployed":0}
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/"phmsa-enforcement.txt"
        try:
            size,sha=fetch(path)
            audit["downloaded_bytes"]=size
            audit["sha256"]=sha
            audit["content"]=inspect(path)
            normalized=Path(directory)/"enforcement-case-rows.csv.gz"
            manifest=args.output/"phmsa-enforcement-normalization.json"
            staged=build(path,normalized,manifest,minimum_rows=1000)
            if staged["raw_sha256"]!=sha or staged["raw_nonempty_rows"]!=audit["content"]["observed_nonempty_rows"]:
                raise ValueError("PHMSA first-party raw SHA/row inventory mismatch")
            indexed=index_cases(normalized,manifest,Path(directory)/"phmsa-enforcement-index.sqlite")
            if indexed["source_case_rows"]!=staged["accepted_case_rows"]:
                raise ValueError("PHMSA normalized/indexed source-case reconciliation failed")
            audit["normalized_case_rows"]=staged["accepted_case_rows"]
            audit["normalized_sha256"]=staged["normalized_sha256"]
            audit["unique_case_numbers"]=staged["native_case_ids"]
            audit["duplicate_native_case_ids"]=staged["duplicate_case_numbers"]
            audit["duplicate_case_activity_composites"]=staged["duplicate_case_activity_composites"]
            audit["report_reference_rows"]=staged["report_reference_rows"]
            audit["distinct_typed_report_references"]=staged["distinct_typed_report_references"]
            audit["source_open_date_range"]=[staged["opened_date_min"],staged["opened_date_max"]]
            audit["unparseable_opened_dates"]=staged["unparseable_or_missing_opened_dates"]
            audit["rejected_case_rows"]=staged["rejected_case_rows"]
            audit["ephemeral_enforcement_index"]=indexed
            if args.private_bundle_dir:
                bundle=package_private(path,normalized,manifest,
                    Path(directory)/"phmsa-enforcement-index.sqlite",
                    args.private_bundle_dir,repo_root=Path(__file__).resolve().parents[1])
                audit["private_enforcement_handoff"]=bundle
                if args.install_test_root:
                    active=install_private(args.private_bundle_dir,args.install_test_root,
                        "real-phmsa-wms-case-smoke",
                        repo_root=Path(__file__).resolve().parents[1])
                    page=query_private(args.install_test_root,page_size=5,
                        repo_root=Path(__file__).resolve().parents[1])
                    if page["total"]!=staged["accepted_case_rows"] or len(page["items"])!=5:
                        raise ValueError("Real installed PHMSA WMS case index query count mismatch")
                    audit["private_install_and_query_smoke"]={
                        "state":"PASS_PRIVATE_TEMPORARY_CASE_INDEX_NOT_PRODUCTION",
                        "indexed_case_rows":active["verified_case_rows"],
                        "verified_report_references":staged["distinct_typed_report_references"],
                        "index_sha256":active["index_sha256"],
                        "readonly_query":"PASS",
                        "authenticated_API_live":False,"app_deployed":0
                    }
            audit["state"]="OFFICIAL_ENFORCEMENT_CASES_CONTENT_VALIDATED_INDEXED_EPHEMERAL_NOT_INCIDENT_CENSUS"
        except Exception as exc:
            audit["state"]="BLOCKED_OR_SCHEMA_UNVERIFIED"
            audit["error"]=type(exc).__name__+": "+str(exc)[:350]
    (args.output/"phmsa-enforcement-inventory.json").write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(audit,indent=2))
    if audit["state"]=="BLOCKED_OR_SCHEMA_UNVERIFIED":
        raise SystemExit("Official PHMSA case-subset distribution not content validated; see manifest")
if __name__=="__main__":
    main()
