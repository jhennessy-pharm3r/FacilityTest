"""Lane D: verified issuer-hosted quarterly/annual PDF interruption disclosures.

Source: Crane Company first-party investor relations 2024 10-K + 2025 Q2 10-Q.
Extract ONLY bounded Marion, NC / Hurricane Helene issuer disclosures.
The Q2 2025 filing explicitly reports $4.0m received *for lost profits*;
distinct from cumulative hurricane property recoveries/receivables. This is
issuer-reported BI proceeds, not independently insurer-confirmed policy payment.

SEC EDGAR original access 403 remains separate; issuer-hosted PDF is NOT
misrepresented as an official SEC EDGAR endpoint download.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

SOURCE_DOCS = [
    {
        "source_id": "crane-2024-10k-marion-hurricane",
        "issuer": "Crane Company",
        "issuer_cik": "1944013",
        "url": "https://investors.craneco.com/files/doc_financials/2024/q4/f6175b30-6957-4189-a2c5-c702cb01db08.pdf",
        "filing_form": "10-K",
        "reporting_period_end": "2024-12-31",
        "title_anchor": "FORM 10-K",
        "period_anchor": "December 31, 2024",
    },
    {
        "source_id": "crane-2025-q2-10q-marion-hurricane",
        "issuer": "Crane Company",
        "issuer_cik": "1944013",
        "url": "https://investors.craneco.com/files/doc_financials/2025/q2/8c508b2d-cef1-4edd-b516-c15a46dc1142.pdf",
        "filing_form": "10-Q",
        "reporting_period_end": "2025-06-30",
        "title_anchor": "FORM 10-Q",
        "period_anchor": "June 30, 2025",
    },
]
MAX_PDF_BYTES = 20_000_000
USER_AGENT = "FacilityTest Lane D issuer financial evidence validation (https://github.com/jhennessy-pharm3r/FacilityTest/issues/73)"
SECTION_ANCHOR = r"Marion(?:\s*,\s*NC)?\s+Site\s+Hurricane\s+(?:Damage\s+and\s+)?Recovery"


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def normalized_text(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s).replace("\u00ad", "")).strip()


def affirm(text: str, pattern: str, label: str, max_gap: int = 500):
    if re.search(pattern, text, flags=re.I) is None:
        raise ValueError("Expected source financial anchor absent: " + label)


def financial_facts(case: dict, section: str) -> list[dict]:
    """Strictly classify as published, with period/scope and avoidance of double count."""
    if "2024-10k" in case["source_id"]:
        affirm(section, r"incurred\s+(?:losses\s+and\s+)?expenses\s+of\s*\$?\s*23\.3\s*million", "2024 incurred site damage expenses")
        affirm(section, r"received\s+insurance\s+recoveries\s+of\s*\$?\s*20\.0\s*million", "2024 received recoveries")
        affirm(section, r"insurance\s+receivable\s+of\s*\$?\s*2\.8\s*million", "2024 insurance receivable")
        values = [
            ("INCURRED_PROPERTY_REPAIR_REMEDIATION_EXPENSE", 23_300_000, "2024_FY", "INCURRED_EXPENSE"),
            ("RECEIVED_HURRICANE_INSURANCE_RECOVERY_UNALLOCATED", 20_000_000, "2024_FY", "ISSUER_REPORTS_RECEIVED"),
            ("REMAINING_INSURANCE_RECEIVABLE", 2_800_000, "2024_12_31_BALANCE", "RECEIVABLE_NOT_RECEIVED"),
        ]
    elif "2025-q2" in case["source_id"]:
        affirm(section, r"received\s+insurance\s+proceeds\s+for\s+lost\s+profits\s+of\s*\$?\s*4\.0\s*million", "Q2 insurer loss-of-profits proceeds received")
        affirm(section, r"\b29\.1\s*million\b", "source-published cumulative hurricane damage expenses")
        affirm(section, r"insurance\s+recoveries\s+of\s*\$?\s*25\.0\s*million", "cumulative received recovery")
        affirm(section, r"insurance\s+receivable\s+of\s*\$?\s*3\.6\s*million", "2025 Q2 receivable")
        values = [
            ("RECEIVED_BI_PROCEEDS_FOR_LOST_PROFITS", 4_000_000, "2025_Q2", "ISSUER_REPORTS_RECEIVED_BI_PROCEEDS"),
            ("CUMULATIVE_HURRICANE_DAMAGE_EXPENSE", 29_100_000, "2024_EVENT_THROUGH_2025_06_30", "CUMULATIVE_INCURRED_EXPENSE"),
            ("CUMULATIVE_HURRICANE_INSURANCE_RECOVERY_UNALLOCATED", 25_000_000, "2024_EVENT_THROUGH_2025_06_30", "CUMULATIVE_RECEIVED"),
            ("REMAINING_INSURANCE_RECEIVABLE", 3_600_000, "2025_06_30_BALANCE", "RECEIVABLE_NOT_RECEIVED"),
        ]
    else:
        raise ValueError("Uncurated issuer PDF document")
    return [
        {
            "evidence_key": digest(json.dumps([case["source_id"],kind,period,amount],sort_keys=True).encode()),
            "publisher_issuer": case["issuer"], "issuer_cik":case["issuer_cik"],
            "native_publication_id":case["source_id"],
            "named_issuer_site": "Crane Company manufacturing site, Marion, North Carolina",
            "underlying_incident_key":"crane-marion-helene-2024",
            "hazard": "HURRICANE_HELENE_FLOODING_2024_09",
            "financial_metric_kind":kind,
            "reported_amount_usd":amount, "accounting_period_or_window":period,
            "basis":basis,
            "issuer_reports_received_lost_profit_bi_proceeds":kind=="RECEIVED_BI_PROCEEDS_FOR_LOST_PROFITS",
            "independent_insurer_claim_payment_confirmed":False,
            "independently_confirmed_covered_property_meters":0,
            "actual_site_power_outage_confirmed":False,
            "source_document_sha256":None,
            "source_pdf_page_onebased":None,
            "source_type":"ISSUER_HOSTED_ORIGINAL_FINANCIAL_REPORT_PDF",
            "original_document_url":case["url"],
            "not_sec_edgar_original":True,
            "not_new_incident_per_reporting_period":True,
        } for kind,amount,period,basis in values
    ]


def parse_pages(case: dict, pages: list[str], raw_document_sha: str):
    if not 10<=len(pages)<=250:
        raise ValueError("Unexpected issuer financial report page count")
    cover=normalized_text(pages[0])
    affirm(cover, r"\bCRANE\s+COMPANY\b", "Crane issuer cover")
    affirm(cover, re.escape(case["title_anchor"]), "10-K/10-Q legal form")
    affirm(cover, re.escape(case["period_anchor"]), "filing period")
    sections=[]
    for number,p in enumerate(pages):
        page_text=normalized_text(p)
        match=re.search(SECTION_ANCHOR,page_text,flags=re.I)
        if match:
            sections.append((number,page_text[match.start():]))
    if not sections:
        raise ValueError("Marion site event section not present in original PDF")
    # Select first complete source section; reporting note appears again elsewhere
    # as a reprint in the same filing and must not produce a second case.
    errors=[]
    for idx,body in sections:
        if idx+1<len(pages):
            body+=" "+normalized_text(pages[idx+1])
        body=re.split(r"\b(?:Other\s+Proceedings|Asbestos\s+Liability|Separation|Note\s+13\s*[-:]|Outlook)\b",body,maxsplit=1,flags=re.I)[0]
        try:
            affirm(body,r"\bMarion\b.{0,250}\bHurricane\s+Helene\b","Marion incident identity")
            # Financial context is verified by document-specific site, event,
            # reporting period and exact received/incurred/receivable anchors.
            # A generic coverage phrase may be broken by publisher PDF layout.
            facts=financial_facts(case,body)
        except ValueError as e:
            errors.append(str(e))
            continue
        section_sha=digest(body.encode("utf-8"))
        for fact in facts:
            fact["source_document_sha256"]=raw_document_sha
            fact["source_pdf_page_onebased"]=idx+1
            fact["source_section_text_sha256"]=section_sha
        return facts,{
            "source_id":case["source_id"],
            "issuer":case["issuer"],
            "filing_form":case["filing_form"],
            "issuer_cik":case["issuer_cik"],
            "reporting_period_end":case["reporting_period_end"],
            "original_source_url":case["url"],
            "original_pdf_sha256":raw_document_sha,
            "pdf_page_count":len(pages),
            "reporting_section_page_onebased":idx+1,
            "reporting_section_sha256":section_sha,
            "source_financial_rows":len(facts),
            "issuer_reported_insurance_cash_received_for_lost_profits_usd":sum(
                x["reported_amount_usd"] for x in facts if x["financial_metric_kind"]=="RECEIVED_BI_PROCEEDS_FOR_LOST_PROFITS"
            ),
            "insured_carrier_confirmation":False,
            "source_status":"ISSUER_HOSTED_PDF_PARSED_VERIFIED",
        }
    raise ValueError("Issuer Marion financial note failed anchors: "+ "; ".join(errors))


def inspect_pdf(case:dict,payload:bytes):
    if not payload.startswith(b"%PDF-") or not 3000<len(payload)<=MAX_PDF_BYTES:
        raise ValueError("Expected bounded original issuer-hosted PDF document")
    try:
        from pypdf import PdfReader
        pdf=PdfReader(io.BytesIO(payload),strict=True)
        publicly_openable_with_empty_password=False
        if pdf.is_encrypted:
            # A published PDF may have owner restrictions but a blank user
            # password. Only validate the no-password public reading case.
            # Never guess, brute-force or provide a nonempty password.
            if not pdf.decrypt(""):
                raise ValueError("PDF is access protected by a nonempty password; not authorized")
            publicly_openable_with_empty_password=True
        pages=[page.extract_text(extraction_mode="plain") or "" for page in pdf.pages]
    except ImportError as e:
        raise RuntimeError("pip install pypdf to validate publisher PDF") from e
    facts,receipt=parse_pages(case,pages,digest(payload))
    receipt["pdf_original_bytes"]=len(payload)
    receipt["pdf_opens_with_public_empty_password"]=publicly_openable_with_empty_password
    return facts,receipt


def validate_publisher_distribution_redirect(original_url: str, final_url: str, http_status: int) -> str:
    """Allow only exact issuer-published original PDF or its known Q4 CDN distribution.

    Actual public Crane IR links issue HTTP 302 to Q4 CDN partition 873006999,
    preserving source path. This is ordinary publisher distribution, not SEC 403
    evasion. Never allow arbitrary redirects, host/path tampering, or HTTP.
    """
    if http_status != 200:
        raise ValueError("Issuer PDF download not HTTP 200")
    if final_url == original_url:
        return "ISSUER_HOST_ORIGINAL"
    original=urlparse(original_url)
    destination=urlparse(final_url)
    if (original.scheme!="https" or original.hostname!="investors.craneco.com"
        or destination.scheme!="https" or destination.hostname!="s21.q4cdn.com"
        or destination.path!="/873006999"+original.path
        or destination.query or destination.fragment):
        raise ValueError("Unapproved issuer document distribution redirect: "+str(destination.hostname))
    return "ISSUER_LINK_PUBLISHED_Q4_CDN_873006999"


def fetch_pdf(case:dict):
    url=case["url"]
    parsed_url=urlparse(url)
    if parsed_url.scheme!="https" or parsed_url.hostname!="investors.craneco.com" or not parsed_url.path.lower().endswith(".pdf"):
        raise ValueError("Not an approved Crane original issuer financial PDF")
    with urlopen(Request(url,headers={"User-Agent":USER_AGENT,"Accept":"application/pdf"}),timeout=75) as response:
        distribution=validate_publisher_distribution_redirect(url,response.geturl(),response.status)
        actual_distribution_url=response.geturl()
        raw=response.read(MAX_PDF_BYTES+1)
    facts,receipt=inspect_pdf(case,raw)
    receipt["publisher_distribution_method"]=distribution
    receipt["original_issuer_link_redirected_to"]=actual_distribution_url
    return facts,receipt


def run(out:Path,cases:list[dict]|None=None,min_sources:int=2):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    cases=SOURCE_DOCS if cases is None else cases
    accepted,receipts,failed=[],[],[]
    for case in cases:
        try:
            facts,receipt=fetch_pdf(case)
        except (ValueError,HTTPError,URLError,OSError,TimeoutError) as exc:
            failed.append({"source_id":case["source_id"],"url":case["url"],"error":str(exc)[:250]})
            continue
        accepted.extend(facts)
        receipts.append(receipt)
    with (out/"issuer_disclosed_financial_observations.jsonl").open("w",encoding="utf-8") as handle:
        for fact in accepted:
            handle.write(json.dumps(fact,sort_keys=True,ensure_ascii=False)+"\n")
    db_path=out/"crane_issuer_financial_staging.sqlite"
    with sqlite3.connect(db_path) as db:
        db.execute("""CREATE TABLE source_financial_observations (
            evidence_key TEXT PRIMARY KEY,source_id TEXT,issuer_cik TEXT,
            underlying_event_key TEXT,financial_metric_kind TEXT,
            reported_amount_usd INTEGER,accounting_period TEXT,
            document_sha256 TEXT,source_pdf_page INTEGER,record_json TEXT
        )""")
        db.executemany("INSERT INTO source_financial_observations VALUES (?,?,?,?,?,?,?,?,?,?)",[
            (x["evidence_key"],x["native_publication_id"],x["issuer_cik"],
             x["underlying_incident_key"],x["financial_metric_kind"],x["reported_amount_usd"],
             x["accounting_period_or_window"],x["source_document_sha256"],
             x["source_pdf_page_onebased"],json.dumps(x,sort_keys=True)) for x in accepted
        ])
        db.commit()
        assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        indexed=db.execute("SELECT COUNT(*) FROM source_financial_observations").fetchone()[0]
        if indexed!=len(accepted):
            raise ValueError("Issuer PDF financial source rows did not reconcile")
    report={
        "publisher":"Crane Company investor relations",
        "source":"ISSUER_HOSTED_PRIMARY_FINANCIAL_REPORT_PDF",
        "download_time_utc":datetime.now(timezone.utc).isoformat(),
        "expected_documents":len(cases),
        "pdf_documents_downloaded_and_verified":len(receipts),
        "pdf_documents_failed_or_blocked":len(failed),
        "financial_records_extracted":len(accepted),
        "rejected_or_blocked":failed,
        "local_staging_financial_records_indexed":indexed,
        "distinct_underlying_reported_hurricane_events":len({r["underlying_incident_key"] for r in accepted}),
        "document_provenance":receipts,
        "issuer_reported_received_lost_profits_bi_usd":sum(
            r["reported_amount_usd"] for r in accepted if r["financial_metric_kind"]=="RECEIVED_BI_PROCEEDS_FOR_LOST_PROFITS"
        ),
        "this_is_issuer_reported_received_bi_proceeds":True,
        "independent_carrier_confirmed_claims":0,
        "insurer_policy_contracts_reviewed":0,
        "independently_verified_meters_or_site_outages":0,
        "durable_backend_indexed":0,
        "deployed":0,
        "limitations":[
            "An issuer-hosted 10-K/10-Q PDF is a primary issuer copy, not an SEC-hosted EDGAR source retrieval",
            "Year-to-date/cumulative property recovery and incurred costs are not incrementally addable to prior fiscal-year total",
            "Received Hurricane property recovery is not necessarily business-interruption lost-profit proceeds",
            "Q2 2025 issuer-reported $4m of received lost-profit proceeds is separately typed and not added to cumulative damage recoveries",
            "No independent insurer claim payment confirmation; no policy exclusions/limits verified; no insured site outage inferred",
            "A $3.6m insurance receivable is not a received paid claim",
        ]
    }
    (out/"manifest.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    if len(receipts)<min_sources:
        raise RuntimeError("Original issuer PDF source gate not met: "+json.dumps(failed))
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--min-sources",type=int,default=2)
    args=parser.parse_args()
    print(json.dumps(run(args.output,min_sources=args.min_sources),indent=2))


if __name__=="__main__":
    main()
