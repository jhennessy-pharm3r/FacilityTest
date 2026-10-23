"""Synthetic unit fixtures for original-document-pinned issuer BI read-only serving.

No data in this file is evidence of original source retrieval; all production
source counts must be validated independently against live issuer publications.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

from facilityrisk.app import app
from facilityrisk.lane_d.install_issuer_financial import (
    SPECS, audit_bundle, install, resolve_current, verify_install,
)


def _issuer_source_fixture(path: Path, kind: str):
    """Build a synthetic source-shaped SQLite/manifest to test fail-closed installer."""
    spec=SPECS[kind]
    path.mkdir(parents=True,exist_ok=True)
    doc_receipts=[]
    for id, sha in spec["docs"].items():
        from facilityrisk.lane_d.ingest_crane_bi_pdf import SOURCE_DOCS
        from facilityrisk.lane_d.ingest_pebblebrook_bi import CASES
        candidates=SOURCE_DOCS if kind=="crane" else CASES
        source=next(i for i in candidates if i["source_id"]==id)
        original_url=source["url"] if kind=="crane" else source["source_url"]
        receipt={"source_id":id,spec["digest_key"]:sha}
        receipt["original_source_url" if kind=="crane" else "original_url"]=original_url
        doc_receipts.append(receipt)
    if kind=="crane":
        manifest={"financial_records_extracted":7,"local_staging_financial_records_indexed":7,
                  "pdf_documents_downloaded_and_verified":2,"pdf_documents_failed_or_blocked":0,
                  "document_provenance":doc_receipts,"independent_carrier_confirmed_claims":0,
                  "durable_backend_indexed":0,"deployed":0}
        schema="""CREATE TABLE source_financial_observations (
           evidence_key TEXT PRIMARY KEY,source_id TEXT,issuer_cik TEXT,underlying_event_key TEXT,
           financial_metric_kind TEXT,reported_amount_usd INTEGER,accounting_period TEXT,
           document_sha256 TEXT,source_pdf_page INTEGER,record_json TEXT)"""
    else:
        manifest={"financial_statement_records_normalized":5,"financial_statement_records_staged_sqlite":5,
                  "downloaded_publisher_documents":2,"failed_sources":[],"published_source_hashes":doc_receipts,
                  "independently_insurer_verified_paid_bi_claims":0,"durable_backend_indexed":0,"deployed":0}
        schema="""CREATE TABLE source_financial_observations (
           evidence_key TEXT PRIMARY KEY,source_id TEXT,event_key TEXT,accounting_period TEXT,
           kind TEXT,amount_usd INTEGER,original_sha256 TEXT,raw_json TEXT)"""
    (path/"manifest.json").write_text(json.dumps(manifest))
    with sqlite3.connect(path/spec["filename"]) as db:
        db.execute(schema)
        for (source,kind_name,period),amount in spec["financials"].items():
            sha=spec["docs"][source]
            key=hashlib.sha256(("fixture-"+source+kind_name+period).encode()).hexdigest()
            if kind=="crane":
                from facilityrisk.lane_d.ingest_crane_bi_pdf import SOURCE_DOCS
                url=next(i["url"] for i in SOURCE_DOCS if i["source_id"]==source)
                details={
                    "evidence_key":key,"native_publication_id":source,
                    "source_document_sha256":sha,"reported_amount_usd":amount,
                    "financial_metric_kind":kind_name,"accounting_period_or_window":period,
                    "underlying_incident_key":"crane-marion-helene-2024",
                    "original_document_url":url,"issuer_reports_received_lost_profit_bi_proceeds":
                        kind_name=="RECEIVED_BI_PROCEEDS_FOR_LOST_PROFITS",
                    "basis":"ISSUER_DISCLARED_ACCOUNTING_PERIOD_TEST_ONLY",
                }
                db.execute("INSERT INTO source_financial_observations VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (key,source,spec["cik"],details["underlying_incident_key"],kind_name,amount,period,
                     sha,24,json.dumps(details)))
            else:
                from facilityrisk.lane_d.ingest_pebblebrook_bi import CASES
                url=next(i["source_url"] for i in CASES if i["source_id"]==source)
                event=("laplaya-hurricane-ian-2022" if "2024" in source
                       else "laplaya-helene-milton-2024")
                details={
                    "evidence_key":key,"source_document_id":source,
                    "document_sha256":sha,"amount_usd":amount,
                    "accounting_period":period,"financial_kind":kind_name,
                    "underlying_event_key":event,"first_party_source_url":url,
                    "issuer_cik":spec["cik"],
                    "inclusion_scope":"SUBSET_OF_2024_FY" if period=="2024_Q4"
                        else "SUBSET_OF_2025_FY" if period=="2025_Q4"
                        else "ANNUAL_RECOGNIZED_AMOUNT",
                }
                db.execute("INSERT INTO source_financial_observations VALUES (?,?,?,?,?,?,?,?)",
                    (key,source,event,period,kind_name,amount,sha,json.dumps(details)))
    return path


@pytest.fixture()
def issuer_api(monkeypatch,tmp_path):
    monkeypatch.setenv("FACILITY_RISK_DB",str(tmp_path/"workspace"/"insured.sqlite"))
    (tmp_path/"workspace").mkdir()
    root=tmp_path/"sources"
    root.mkdir()
    monkeypatch.setenv("FACILITY_RISK_LANE_D_INDEX_ROOT",str(root))
    monkeypatch.setenv("FACILITY_RISK_REQUIRE_AUTH","1")
    monkeypatch.setenv("FACILITY_RISK_AUTH_TOKEN","V"*48)
    client=TestClient(app,headers={"Authorization":"Bearer "+"V"*48})
    yield client,root,monkeypatch,tmp_path
    client.close()


def test_real_source_shape_original_doc_pin_and_distinct_periods(issuer_api):
    client,root,patch,tmp=issuer_api
    for kind in SPECS:
        bundle=_issuer_source_fixture(tmp/("synthetic-"+kind),kind)
        assert audit_bundle(bundle,kind)["source_financial_records"]==SPECS[kind]["rows"]
        installed=install(bundle,root/"issuer_financial",kind)
        assert verify_install(root/"issuer_financial",kind)["index_sha256"]==installed["index_sha256"]
    health=client.get("/api/source-context/lane-d/status").json()["issuer_bi_financial_context"]
    assert health["crane"]["state"]==health["pebblebrook"]["state"]=="verified_private_issuer_financial_context"
    assert health["crane"]["private_indexed_financial_statement_observations"]==7
    assert health["pebblebrook"]["private_indexed_financial_statement_observations"]==5
    assert all(r["independently_insurer_confirmed_paid_claims"]==0 for r in health.values())
    for issuer,count in (("Crane Company",7),("Pebblebrook Hotel Trust",5)):
        from urllib.parse import urlencode
        q=client.get("/api/source-context/issuer-bi?"+urlencode({"issuer":issuer,"limit":20}))
        assert q.status_code==200,q.text
        result=q.json()
        assert result["source_financial_observations_installed"]==count
        assert len(result["data"]["returned_financial_source_observations"])==count
        assert not result["independent_carrier_claim_payment_verified"]
        assert not result["physical_insured_site_or_outage_independently_verified"]
        assert not result["business_interruption_coverage_terms_verified"]
        assert result["do_not_sum_quarter_included_in_annual_or_cumulative_amounts"] is True
    crane=client.get("/api/source-context/issuer-bi?issuer=Crane%20Company").json()
    facts=crane["data"]["returned_financial_source_observations"]
    bi=[i for i in facts if i["cash_received_for_lost_profits_reported_by_issuer"]]
    assert len(bi)==1 and bi[0]["issuer_reported_usd"]==4000000
    assert all(i["carrier_payment_independently_verified"] is False for i in facts)
    assert all(i["facility_power_outage_independently_verified"] is False for i in facts)


def test_missing_private_issuer_source_returns_503_and_unknown_is_422(issuer_api):
    client,_,__,___=issuer_api
    assert client.get("/api/source-context/issuer-bi?issuer=Crane%20Company").status_code==503
    assert client.get("/api/source-context/issuer-bi?issuer=Unknown%20Issuer").status_code==422
    assert client.get("/api/source-context/issuer-bi?issuer=Crane%20Company&event_key=bad").status_code==422
    with TestClient(app) as anonymous:
        assert anonymous.get("/api/source-context/issuer-bi?issuer=Crane%20Company").status_code==401


def test_issuer_original_sha_or_amount_tampering_never_promotes(issuer_api):
    _client,root,_patch,tmp=issuer_api
    kind="crane"
    bundle=_issuer_source_fixture(tmp/"synthetic-crane",kind)
    accepted=install(bundle,root/"issuer_financial",kind)
    current=root/"issuer_financial"/kind/"current.json"
    original_pointer=current.read_bytes()
    manifest=json.loads((bundle/"manifest.json").read_text())
    manifest["document_provenance"][0]["original_pdf_sha256"]="0"*64
    (bundle/"manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match="original hash"):
        install(bundle,root/"issuer_financial",kind)
    assert original_pointer==current.read_bytes()
    (bundle/"manifest.json").write_text(json.dumps({**manifest,
        "document_provenance":[{**r, "original_pdf_sha256":SPECS[kind]["docs"][r["source_id"]]}
            for r in manifest["document_provenance"]]}))
    db=bundle/SPECS[kind]["filename"]
    with sqlite3.connect(db) as conn:
        conn.execute("""UPDATE source_financial_observations SET reported_amount_usd=9000000
                        WHERE financial_metric_kind='RECEIVED_BI_PROCEEDS_FOR_LOST_PROFITS'""")
        conn.commit()
    with pytest.raises(ValueError,match="amount/period drift"):
        install(bundle,root/"issuer_financial",kind)
    assert original_pointer==current.read_bytes()
    assert accepted["source_financial_records"]==7
