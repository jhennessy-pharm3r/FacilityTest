"""Official first-party PHMSA published Failure Investigation Report list probe.

Never mix selective investigated/published failures with operator incident
census, WMS enforcement cases, NRC notifications, or insured loss outcomes.
All source row data remain on disposable runner; published artifact is
aggregate provenance/status only.
"""
from __future__ import annotations
from datetime import datetime,timezone
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from urllib.parse import urlsplit
import requests

try:
    from scripts.build_phmsa_failure_investigations import (
        URL,build,index,extract_index
    )
except ModuleNotFoundError:
    from build_phmsa_failure_investigations import URL,build,index,extract_index

MAX_HTML=3_000_000

def download_first_party_html(url,path):
    digest=hashlib.sha256()
    n=0
    with requests.get(url,stream=True,timeout=(15,75),headers={
            "User-Agent":"FacilityRisk-LaneC-OfficialInvestigationAudit/1.0",
            "Accept-Encoding":"identity"}) as response:
        response.raise_for_status()
        endpoint=urlsplit(response.url)
        if endpoint.scheme!="https" or endpoint.hostname!="www.phmsa.dot.gov":
            raise ValueError("PHMSA official detail redirected off first-party HTTPS host")
        if "text/html" not in response.headers.get("Content-Type","").lower():
            raise ValueError("Published PHMSA report catalog returned non-HTML")
        with path.open("wb") as out:
            for chunk in response.iter_content(1024*64):
                if not chunk:continue
                n+=len(chunk)
                if n>MAX_HTML:raise ValueError("PHMSA official document catalog exceeds HTML size cap")
                digest.update(chunk)
                out.write(chunk)
    if n<500:raise ValueError("PHMSA official document catalog unexpectedly small")
    return {"original_bytes":n,"original_sha256":digest.hexdigest(),"source_url":url}

def probe_detail_page(url):
    """Content/status verification only: no unbounded PDFs, no bypass."""
    detail={"url":url,"state":"NOT_TESTED"}
    try:
        with requests.get(url,stream=True,timeout=(10,25),
                          headers={"User-Agent":"FacilityRisk-LaneC-OfficialInvestigations/1.0",
                                   "Accept-Encoding":"identity"}) as response:
            detail["http_status"]=response.status_code
            parsed=urlsplit(response.url)
            if parsed.scheme!="https" or parsed.hostname!="www.phmsa.dot.gov":
                raise ValueError("PHMSA detail link redirected off first party HTTPS host")
            detail["content_type"]=response.headers.get("Content-Type","")
            if response.status_code!=200:
                detail["state"]="FIRST_PARTY_DETAIL_HTTP_"+str(response.status_code)
            elif "html" in detail["content_type"].lower():
                # This confirms only official detail page retrieval, NOT the PDF.
                detail["state"]="OFFICIAL_DETAIL_PAGE_HTTP_200_NOT_PDF_VERIFIED"
            elif "pdf" in detail["content_type"].lower():
                detail["state"]="OFFICIAL_PDF_URL_HTTP_200_DOCUMENT_NOT_PARSED"
            else:
                detail["state"]="OFFICIAL_DETAIL_UNKNOWN_CONTENT_NOT_VERIFIED"
    except Exception as exc:
        detail["state"]="OFFICIAL_DETAIL_NOT_ACCESSIBLE"
        detail["error"]=type(exc).__name__+": "+str(exc)[:240]
    return detail

def run(output):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    audit={"source":"PHMSA official published failure investigation report INDEX",
           "source_url":URL,
           "fetched_at":datetime.now(timezone.utc).isoformat(),
           "state":"NOT_TESTED","indexed_ephemeral":0,"deployed":0,
           "full_operator_incident_census_retrieved":False,
           "confirmed_insured_site_links":0}
    with tempfile.TemporaryDirectory() as workdir:
        temp=Path(workdir)
        raw=temp/"phmsa-failure-investigations.html"
        try:
            audit["official_download"]=download_first_party_html(URL,raw)
            out=temp/"failure-investigation-list.csv.gz"
            m=output/"phmsa-failure-investigation-manifest.json"
            # Source snapshot means as-of source poll UTC day, not
            # publisher-assigned incident or investigation ID.
            source_snapshot=datetime.now(timezone.utc).date().isoformat()
            details=build(raw,out,m,snapshot=source_snapshot,minimum_rows=20)
            repeated=build(raw,temp/"failure-index-repeat.gz",
                           temp/"repeat-manifest.json",snapshot=source_snapshot,minimum_rows=20)
            if details["normalized_sha256"]!=repeated["normalized_sha256"]:
                raise ValueError("Identical PHMSA official HTML produced nonreproducible output")
            db=temp/"failure-investigation-source-only.sqlite"
            sql=index(out,m,db)
            if sql["indexed_publisher_investigation_listings"]!=details["accepted_publisher_index_rows"]:
                raise ValueError("PHMSA official catalog accepted/indexed rows mismatch")
            rows,_,_,_=extract_index(raw.read_bytes(),source_snapshot,min_rows=20)
            sample=[]
            seen=set()
            for row in rows:
                url=row["detail_report_url"]
                if url in seen:continue
                seen.add(url)
                sample.append(probe_detail_page(url))
                if len(sample)>=5:break
            audit.update({
                "state":"OFFICIAL_PUBLISHED_INVESTIGATION_CATALOG_QA_PASS_EPHEMERAL_SQL",
                "validation":details,
                "ephemeral_index":sql,
                "same_source_normalized_sha_repeated":"PASS",
                "first_party_detail_page_samples":sample,
                "first_party_detail_sample_pass":sum(x["state"].startswith("OFFICIAL_DETAIL_PAGE_HTTP_200")
                    or x["state"].startswith("OFFICIAL_PDF_URL_HTTP_200") for x in sample),
                "indexed_ephemeral":sql["indexed_publisher_investigation_listings"],
                "verified_detail_pdf_corpus":False,"deployed":0})
        except Exception as e:
            audit["state"]="SOURCE_BLOCKED_OR_SCHEMA_QA_FAIL"
            audit["error"]=type(e).__name__+": "+str(e)[:480]
        finally:
            (output/"lane-c-phmsa-investigation-audit.json").write_text(
                json.dumps(audit,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({
        "state":audit["state"],
        "official_download":audit.get("official_download"),
        "accepted":audit.get("validation",{}).get("accepted_publisher_index_rows"),
        "rejected":audit.get("validation",{}).get("rejected_index_rows"),
        "ephemeral_index":audit.get("ephemeral_index"),
        "detail_url_samples":audit.get("first_party_detail_page_samples"),
        "source_date_anomalies":audit.get("validation",{}).get("posted_date_earlier_than_failure_date"),
        "failure":audit.get("error"),"deployed":0
    },indent=2))
    if audit["state"]=="SOURCE_BLOCKED_OR_SCHEMA_QA_FAIL":
        raise SystemExit("PHMSA failure investigation listing source/QA blocked; see aggregate artifact")
    return audit

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    run(args.output)
