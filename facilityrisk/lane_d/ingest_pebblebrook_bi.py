"""Lane D: public hotel-sector issuer-recognized business interruption income.

Pebblebrook original investor-relations releases: 2024 and 2025 annual results.
Disaggregates Q4 components INSIDE annual BI income to prevent double counts.
Recognized accounting income is not necessarily insurer cash paid; no policy,
meter link or independently carrier-confirmed insured-loss figure is invented.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlparse
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
from .ingest_issuer_release import ReadableHTML

CASES=[
 {
  "source_id":"pebblebrook-fy2024-release-20250226",
  "source_url":"https://investor.pebblebrookhotels.com/news-1/news-releases/news-details/2025/Pebblebrook-Hotel-Trust-Reports-2024-Results-and-Provides-2025-Outlook/default.aspx",
  "expected_title":"Pebblebrook Hotel Trust Reports 2024 Results and Provides 2025 Outlook",
  "release_date":"February 26, 2025",
  "reporting_year":2024,
 },
 {
  "source_id":"pebblebrook-fy2025-release-20260225",
  "source_url":"https://investor.pebblebrookhotels.com/news-1/news-releases/news-details/2026/Pebblebrook-Hotel-Trust-Reports-2025-Results-and-Provides-2026-Outlook/default.aspx",
  "expected_title":"Pebblebrook Hotel Trust Reports 2025 Results and Provides 2026 Outlook",
  "release_date":"February 25, 2026",
  "reporting_year":2025,
 },
]
MAX_BYTES=6_000_000
PUB="investor.pebblebrookhotels.com"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def source_text(data):
    p=ReadableHTML()
    p.feed(data.decode("utf-8-sig",errors="replace"))
    return re.sub(r"\s+"," ",p.text()).strip()


def require(txt,phrase):
    if phrase.lower() not in txt.lower():
        raise ValueError("Missing original issuer income anchor: "+phrase)


def inspect(case,html,origin_url,status):
    if status!=200 or origin_url!=case["source_url"]:
        raise ValueError("Issuer original publication redirect/status differs")
    if not (500<len(html)<MAX_BYTES) or b"<html" not in html[:5000].lower():
        raise ValueError("Invalid issuer HTML source bytes")
    txt=source_text(html)
    require(txt,case["expected_title"])
    require(txt,case["release_date"])
    require(txt,"LaPlaya")
    require(txt,"business interruption")
    if case["reporting_year"]==2024:
        for key in (
            "Hurricane Ian",
            "additional $5.4 million",
            "BI income in 2024 to $23.8 million",
            "$33.0 million of BI income recognized in 2023",
        ):
            require(txt,key)
        facts=[
            ("RECOGNIZED_BI_INSURANCE_INCOME",23_800_000,"2024_FY","laplaya-hurricane-ian-2022","ANNUAL_RECOGNIZED_AMOUNT"),
            ("RECOGNIZED_BI_INSURANCE_INCOME_Q4_COMPONENT",5_400_000,"2024_Q4","laplaya-hurricane-ian-2022","SUBSET_OF_2024_FY"),
            ("RECOGNIZED_BI_INSURANCE_INCOME_PRIOR_YEAR",33_000_000,"2023_FY","laplaya-hurricane-ian-2022","REPORTED_PRIOR_YEAR_CONTEXT"),
        ]
        excerpt_anchor="BI income in 2024 to $23.8 million"
    else:
        for key in ("Hurricanes Helene and Milton","recognized $3.1 million","full-year BI insurance recovery to $12.7 million","claims now fully settled"):
            require(txt,key)
        facts=[
            ("RECOGNIZED_BI_INSURANCE_INCOME",12_700_000,"2025_FY","laplaya-helene-milton-2024","ANNUAL_RECOGNIZED_AMOUNT"),
            ("RECOGNIZED_BI_INSURANCE_INCOME_Q4_COMPONENT",3_100_000,"2025_Q4","laplaya-helene-milton-2024","SUBSET_OF_2025_FY"),
        ]
        excerpt_anchor="full-year BI insurance recovery to $12.7 million"
    doc_hash=digest(html)
    anchor_pos=txt.lower().find(excerpt_anchor.lower())
    excerpt=txt[max(0,anchor_pos-200):anchor_pos+len(excerpt_anchor)+250]
    records=[
       {
        "evidence_key":digest(json.dumps([case["source_id"],kind,period,amount],sort_keys=True).encode()),
        "source_document_id":case["source_id"],
        "first_party_source_url":case["source_url"],
        "document_sha256":doc_hash,
        "source_text_sha256":digest(txt.encode()),
        "evidence_anchor_sha256":digest(excerpt.encode()),
        "issuer":"Pebblebrook Hotel Trust","issuer_cik":"1474098",
        "named_site":"LaPlaya Beach Resort & Club, Naples, Florida",
        "underlying_event_key":event,
        "financial_kind":kind,"amount_usd":amount,"accounting_period":period,
        "inclusion_scope":basis,
        "financial_status":"ISSUER_RECOGNIZED_BUSINESS_INTERRUPTION_INSURANCE_INCOME",
        "cash_received_by_issuer_independently_verified":False,
        "carrier_claim_payment_independently_verified":False,
        "underlying_site_outage_verified":False,
        "policy_coverage_verified":False,
        "source_document_type":"FIRST_PARTY_ISSUER_RESULTS_PRESS_RELEASE"
       } for kind,amount,period,event,basis in facts
    ]
    receipt={
        "source_id":case["source_id"],"issuer":"Pebblebrook Hotel Trust",
        "release_date":case["release_date"],"reporting_year":case["reporting_year"],
        "original_url":case["source_url"],
        "downloaded_bytes":len(html),"original_sha256":doc_hash,
        "extracted_text_sha256":digest(txt.encode()),
        "evidence_section_sha256":digest(excerpt.encode()),
        "accepted_source_financial_rows":len(records),
        "publisher_claim_cash_paid_verified":False,
    }
    return records,receipt


def retrieve(case):
    url=case["source_url"]
    target=urlparse(url)
    if target.scheme!="https" or target.hostname!=PUB:
        raise ValueError("Not authorized original issuer hostname")
    req=Request(url,headers={"User-Agent":"FacilityTest Lane D real source validation","Accept":"text/html"})
    with urlopen(req,timeout=50) as resp:
        if resp.status!=200 or resp.geturl()!=url:
            raise ValueError("Original public issuer press release URL not returned")
        contents=resp.read(MAX_BYTES+1)
    return inspect(case,contents,url,200)


def run(folder,cases=None,min_sources=2):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    cases=CASES if cases is None else cases
    accepted,source_receipts,failures=[],[],[]
    for case in cases:
        try:
            records,receipt=retrieve(case)
        except (ValueError,HTTPError,URLError,TimeoutError,OSError) as exc:
            failures.append({"source_id":case["source_id"],"error":str(exc)[:240],"url":case["source_url"]})
            continue
        accepted.extend(records)
        source_receipts.append(receipt)
    with (folder/"source_financial_observations.jsonl").open("w",encoding="utf-8") as f:
        for item in accepted:
            f.write(json.dumps(item,sort_keys=True)+"\n")
    with sqlite3.connect(folder/"issuer_bi_income_staging.sqlite") as db:
        db.execute("""CREATE TABLE source_financial_observations (
            evidence_key TEXT PRIMARY KEY,source_id TEXT,event_key TEXT,
            accounting_period TEXT,kind TEXT,amount_usd INTEGER,
            original_sha256 TEXT,raw_json TEXT
        )""")
        db.executemany("INSERT INTO source_financial_observations VALUES (?,?,?,?,?,?,?,?)",[
            (r["evidence_key"],r["source_document_id"],r["underlying_event_key"],
             r["accounting_period"],r["financial_kind"],r["amount_usd"],
             r["document_sha256"],json.dumps(r,sort_keys=True)) for r in accepted
        ])
        db.commit()
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise RuntimeError("PEB source staging integrity failed")
        indexed=db.execute("SELECT count(*) FROM source_financial_observations").fetchone()[0]
    if indexed!=len(accepted):
        raise RuntimeError("PEB reported issuer BI rows vs index mismatch")
    manifest={
        "source":"PEBBLEBROOK_FIRST_PARTY_BI_RESULTS",
        "downloaded_utc":datetime.now(timezone.utc).isoformat(),
        "attempted_documents":len(cases),
        "downloaded_publisher_documents":len(source_receipts),
        "failed_sources":failures,
        "financial_statement_records_normalized":len(accepted),
        "financial_statement_records_staged_sqlite":indexed,
        "published_source_hashes":source_receipts,
        "distinct_named_storm_event_groups":len({r["underlying_event_key"] for r in accepted}),
        "verified_annual_income_2024_ian_usd":sum(r["amount_usd"] for r in accepted
             if r["underlying_event_key"]=="laplaya-hurricane-ian-2022" and r["accounting_period"]=="2024_FY"),
        "verified_annual_income_2025_helene_milton_usd":sum(r["amount_usd"] for r in accepted
             if r["underlying_event_key"]=="laplaya-helene-milton-2024" and r["accounting_period"]=="2025_FY"),
        "independently_insurer_verified_paid_bi_claims":0,
        "independently_verified_site_outages":0,
        "durable_backend_indexed":0,
        "deployed":0,
        "limitations":[
            "Recognized BI insurance income in issuer accounts is not necessarily a cash-paid insurance claim",
            "2024 Hurricane Ian-related and 2025 Helene/Milton-related accounting income are different storms/periods",
            "2024 Q4 $5.4m is included in 2024 $23.8m; 2025 Q4 $3.1m is included in FY2025 $12.7m",
            "Prior 2023 $33m is historical context, not included in 2024 or 2025 totals",
            "Original public issuer pages are not EDGAR filings and do not corroborate meter outage duration",
            "No insurer policy wording/carrier-level loss payment or insured building utility details validated",
        ],
    }
    (folder/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    if len(source_receipts)<min_sources:
        raise RuntimeError("Original issuer HTML source coverage gate failed: "+json.dumps(failures))
    return manifest


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--min-sources",type=int,default=2)
    args=parser.parse_args()
    print(json.dumps(run(args.output,min_sources=args.min_sources),indent=2))


if __name__=="__main__":
    main()
