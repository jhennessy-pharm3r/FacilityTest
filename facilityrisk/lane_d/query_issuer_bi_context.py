"""Lane D source-only financial interruption evidence query for Lane E coordinator.

Read-only adapter over separate Crane (issuer-hosted quarterly PDF) and
Pebblebrook (issuer-hosted public results release) staging indexes. Reports
issuer-disclosed accounting facts, NOT an insurance claim registry, physical
site downtime, metered utility outages, or validated policyholder recoveries.

Never sum Q4 subset+FY or cumulative FY+earlier FY; never sum repair expense,
insurance receivables, insurer cash receipts and recognized income together.
Every observation has an original issuer document provenance SHA-256 and source
event/period/basis. No fuzzy corporate entity reconciliation or auto site join.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
from urllib.parse import quote

VALID_ISSUERS = ("Crane Company", "Pebblebrook Hotel Trust")


def _readonly(path):
    p=Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return sqlite3.connect("file:"+quote(str(p),safe="/")+"?mode=ro",uri=True)


def _crane(db,limit,event_key):
    where=" WHERE underlying_event_key=?" if event_key else ""
    params=[event_key] if event_key else []
    n=db.execute("SELECT COUNT(*) FROM source_financial_observations"+where,params).fetchone()[0]
    sql=("SELECT evidence_key,source_id,issuer_cik,underlying_event_key,"
         "financial_metric_kind,reported_amount_usd,accounting_period,"
         "document_sha256,source_pdf_page,record_json FROM source_financial_observations"
         +where+" ORDER BY accounting_period,financial_metric_kind,evidence_key LIMIT ?")
    items=[]
    for key,document,cik,event,kind,amount,period,sha,page,raw in db.execute(sql,params+[limit]):
        original=json.loads(raw)
        if (original.get("evidence_key")!=key
            or original.get("source_document_sha256")!=sha
            or original.get("reported_amount_usd")!=amount
            or original.get("accounting_period_or_window")!=period
            or original.get("underlying_incident_key")!=event):
            raise ValueError("Crane indexed row is inconsistent with preserved source evidence")
        items.append({
            "source_document_id":document,
            "evidence_key":key,
            "source_cik":cik,
            "underlying_issuer_reported_event_key":event,
            "accounting_period":period,
            "financial_metric_kind":kind,
            "issuer_reported_usd":amount,
            "reporting_basis":original["basis"],
            "source_document_url":original["original_document_url"],
            "source_document_sha256":sha,
            "source_pdf_page_onebased":page,
            "financial_data_class":"FIRST_PARTY_ISSUER_FINANCIAL_DISCLOSURE",
            "cash_received_for_lost_profits_reported_by_issuer":bool(original["issuer_reports_received_lost_profit_bi_proceeds"]),
            "carrier_payment_independently_verified":False,
            "policy_coverage_independently_verified":False,
            "facility_power_outage_independently_verified":False,
            "facility_loss_usd_independently_verified":False,
            "site_match_state":"ISSUER_NAMED_SITE_NOT_INDEPENDENTLY_INSURED_PROPERTY_MATCHED",
        })
    return n,items


def _pebblebrook(db,limit,event_key):
    where=" WHERE event_key=?" if event_key else ""
    params=[event_key] if event_key else []
    n=db.execute("SELECT COUNT(*) FROM source_financial_observations"+where,params).fetchone()[0]
    sql=("SELECT evidence_key,source_id,event_key,accounting_period,kind,"
         "amount_usd,original_sha256,raw_json FROM source_financial_observations"
         +where+" ORDER BY accounting_period,kind,evidence_key LIMIT ?")
    items=[]
    for key,source,event,period,kind,amount,sha,raw in db.execute(sql,params+[limit]):
        original=json.loads(raw)
        if (original.get("evidence_key")!=key
            or original.get("document_sha256")!=sha
            or original.get("amount_usd")!=amount
            or original.get("accounting_period")!=period
            or original.get("underlying_event_key")!=event):
            raise ValueError("Pebblebrook indexed row is inconsistent with preserved source evidence")
        items.append({
            "source_document_id":source,
            "evidence_key":key,
            "source_cik":original["issuer_cik"],
            "underlying_issuer_reported_event_key":event,
            "accounting_period":period,
            "financial_metric_kind":kind,
            "issuer_reported_usd":amount,
            "reporting_basis":original["inclusion_scope"],
            "source_document_url":original["first_party_source_url"],
            "source_document_sha256":sha,
            "source_pdf_page_onebased":None,
            "financial_data_class":"FIRST_PARTY_ISSUER_RECOGNIZED_BI_INCOME",
            "cash_received_for_lost_profits_reported_by_issuer":False,
            "carrier_payment_independently_verified":False,
            "policy_coverage_independently_verified":False,
            "facility_power_outage_independently_verified":False,
            "facility_loss_usd_independently_verified":False,
            "site_match_state":"ISSUER_NAMED_SITE_NOT_INDEPENDENTLY_INSURED_PROPERTY_MATCHED",
        })
    return n,items


def get_issuer_bi_context(*,crane_db=None,pebblebrook_db=None,issuer=None,event_key=None,limit=40):
    if crane_db is None and pebblebrook_db is None:
        raise ValueError("Provide at least one reviewed issuer original-source staging index")
    if issuer is not None and issuer not in VALID_ISSUERS:
        raise ValueError("Only unambiguous first-party issuer names are permitted")
    if event_key is not None and (not isinstance(event_key,str)
                                 or not 5 <= len(event_key)<=100
                                 or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in event_key)):
        raise ValueError("Native curated event key required, not a fuzzy location/name query")
    if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=100:
        raise ValueError("Limit must be an integer between 1 and 100")
    results=[]
    examined={}
    for name,path,fn in (
        ("Crane Company",crane_db,_crane),
        ("Pebblebrook Hotel Trust",pebblebrook_db,_pebblebrook),
    ):
        if path is None or issuer is not None and issuer!=name:
            continue
        with _readonly(path) as db:
            total,observations=fn(db,limit,event_key)
        examined[name]={
            "source_financial_observations_in_stage":total,
            "returned":len(observations),
            "truncated":total>len(observations),
        }
        for row in observations:
            row["issuer"]=name
            results.append(row)
    return {
        "query_state":"ISSUER_REPORTED_FINANCIAL_CONTEXT_NOT_INSURER_CLAIM_VALIDATION",
        "source_kind_counts":examined,
        "returned_financial_source_observations":results,
        "records_are_not_independently_verified_paid_insurance_claims":True,
        "independently_verified_insurer_payment_records":0,
        "independently_verified_facility_power_outages":0,
        "deployed":0,
        "guardrails":[
            "Never sum a quarterly component with its annual total or a prior-year historical context row",
            "Never add cumulative receipts/expense/receivable balances across reporting dates or classify them as net insurance loss",
            "Crane reported receipt of BI lost-profit proceeds; an insurer policy/payment confirmation remains separate and unavailable",
            "Pebblebrook published BI insurance income recognized, not independently verified insurer cash paid",
            "The primary issuer site named in a document is not a verified insured property/meter match",
            "This curated cross-industry case study is not a national claims or facility-outage census",
            "No utility outage or electricity account association should be inferred from hurricane property damage",
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--crane-db",type=Path)
    p.add_argument("--pebblebrook-db",type=Path)
    p.add_argument("--issuer",choices=VALID_ISSUERS)
    p.add_argument("--event-key")
    p.add_argument("--limit",type=int,default=40)
    a=p.parse_args()
    print(json.dumps(get_issuer_bi_context(crane_db=a.crane_db,
        pebblebrook_db=a.pebblebrook_db,issuer=a.issuer,event_key=a.event_key,limit=a.limit),
        indent=2,ensure_ascii=False))


if __name__=="__main__":
    main()
