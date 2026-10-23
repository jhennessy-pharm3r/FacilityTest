"""Private Lane C API boundary: auth, schema, real index checks and no false site merges.

Regression data below are deliberately synthetic. Real official-source
installation and HTTP smoke execute separately in integration CI.
"""
from __future__ import annotations

import base64
import csv
import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from facilityrisk.app import app
from facilityrisk.security import make_password_hash
from facilityrisk.industrial_source_indices import _validate_index
from scripts.lane_c_private_handoff import private_bundle, sha
from scripts.lane_c_install import install as install_incidents
from scripts.build_phmsa_enforcement import REQUIRED,build as build_wms,index_cases
from scripts.lane_c_enforcement_install import package as package_wms,install as install_wms

INDUSTRIES=(
    "food_processing","hospital","school","water_utility","logistics_warehouse",
    "data_center","hotel","retail_store","oil_refinery","pipeline","chemical_plant",
    "pharmaceutical","medical_device","airport","rail_terminal","seaport",
    "hospitality","agriculture","mining","power_generation","telecommunications",
    "manufacturing","research_lab","waste_management","office_complex"
)

def _incidents(tmp_path):
    repo=tmp_path/"checkout"
    repo.mkdir()
    db=tmp_path/"publisher-source.sqlite"
    with sqlite3.connect(db) as conn:
        conn.executescript("""
            CREATE TABLE source_incidents(
             source TEXT NOT NULL,source_id TEXT NOT NULL,publisher_native_id TEXT NOT NULL,
             source_vintage TEXT NOT NULL,incident_date TEXT,city TEXT,state TEXT,
             latitude REAL,longitude REAL,evidence_status TEXT NOT NULL,
             site_link_status TEXT NOT NULL,source_url TEXT NOT NULL,source_json TEXT NOT NULL,
             PRIMARY KEY(source,source_id));
            CREATE TABLE lane_c_review_candidates(
             nrc_source TEXT,nrc_source_id TEXT,csb_source TEXT,csb_source_id TEXT,
             match_rule TEXT,status TEXT NOT NULL);
        """)
        for n,industry in enumerate(INDUSTRIES,1):
            sid=str(100000+n)
            conn.execute("INSERT INTO source_incidents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
              ("nrc_2025",sid,sid,"2025","2025-01-15",
               f"Test City {n}","TX" if n%2 else "MA",
               29.0+n/100,-95.0-n/100,
               "initially_unverified_source_notification",
               "candidate_only_not_matched",
               "https://nrc.uscg.mil/FOIAFiles/CY25.xlsx",
               json.dumps({"synthetic_industry_label":industry,
                           "company_as_reported":"Test Example Only",
                           "review_status":"not_matched"})))
        conn.execute("INSERT INTO source_incidents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("csb","csb:2026-09-01:1","1","2026-09-01","2025-01-15",
             "Test City 1","TX",None,None,
             "public_report_unconfirmed","candidate_only_not_matched",
             "https://www.csb.gov/assets/1/6/Copy_of_Accidental_Release_Events_2026-09-01.xlsx",
             json.dumps({"synthetic_example":True,"company_as_reported":"Example Industries"})))
        conn.execute("INSERT INTO lane_c_review_candidates VALUES(?,?,?,?,?,?)",
            ("nrc_2025","100001","csb","csb:2026-09-01:1",
             "reported_day_company_city_state_text_only","review_candidate_not_corrob"))
    inputs=[]
    raws={}
    for name,n in (("nrc_2025",25),("csb",1)):
        raw=tmp_path/(name+".xlsx")
        raw.write_bytes(b"fixture official source not real - "+name.encode())
        norm=tmp_path/(name+".csv.gz")
        norm.write_bytes(b"fixture gzip placeholder - "+name.encode())
        manifest=tmp_path/(name+".json")
        manifest.write_text(json.dumps({
            "accepted_rows":n,"rejected_rows":0,"year":2025 if name=="nrc_2025" else None,
            "release":"2026-09-01" if name=="csb" else None,
            "raw_sha256":sha(raw),"normalized_sha256":sha(norm)
        }))
        inputs.append((name,norm,manifest))
        raws[name]=raw
    bundle=tmp_path/"incident-bundle"
    private_bundle(db,inputs,raws,bundle,repo_root=repo)
    store=tmp_path/"incident-readonly-store"
    store.mkdir(mode=0o700)
    install_incidents(bundle,store,release_id="test-industrial-2025",repo_root=repo)
    return store

def _enforcement(tmp_path):
    repo=tmp_path/"wms-checkout"
    repo.mkdir()
    raw=tmp_path/"official-wms-case.txt"
    records=[]
    for n,operator_id in ((1,"00123"),(2,"00999")):
        records.append({
            "CPF_Number":f"4000{n}CAO","WMS_Activity_Seq":f"991{n}",
            "Operator_ID":operator_id,"Operator_Name":"Example operator",
            "Pipeline_Type":"Hazardous Liquid","Case_Type":"CAO",
            "Case_Status":"Open","Opened_Date":f"01/0{n}/2026",
            "Report_Type":"Incident","Report_Number":"2026001",
            "Data_as_of":"10/02/2026"
        })
    with raw.open("w",encoding="cp1252",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=REQUIRED,dialect="excel-tab")
        writer.writeheader();writer.writerows(records)
    norm=tmp_path/"wms.csv.gz"
    manifest=tmp_path/"wms.json"
    build_wms(raw,norm,manifest,minimum_rows=2)
    db=tmp_path/"wms.sqlite"
    index_cases(norm,manifest,db)
    bundle=tmp_path/"wms-bundle"
    package_wms(raw,norm,manifest,db,bundle,repo_root=repo)
    store=tmp_path/"wms-readonly-store"
    store.mkdir(mode=0o700)
    install_wms(bundle,store,"test-wms-2026",repo_root=repo)
    return store

@pytest.fixture
def installed(tmp_path,monkeypatch):
    incident_store=_incidents(tmp_path)
    wms_store=_enforcement(tmp_path)
    _validate_index.cache_clear()
    monkeypatch.setenv("FACILITY_RISK_LANE_C_ROOT",str(incident_store))
    monkeypatch.setenv("FACILITY_RISK_PHMSA_WMS_ROOT",str(wms_store))
    monkeypatch.setenv("FACILITY_RISK_DB",str(tmp_path/"insured-workspace.sqlite"))
    monkeypatch.setenv("FACILITY_RISK_REQUIRE_AUTH","1")
    monkeypatch.setenv("FACILITY_RISK_AUTH_TOKEN","Z"*44)
    monkeypatch.delenv("FACILITY_RISK_USERS_JSON",raising=False)
    return incident_store,wms_store

def test_private_api_is_authenticated_and_never_exposes_raw_personal_source_text(installed):
    with TestClient(app) as client:
        for uri in ("/api/source-indices/status","/api/industrial/status",
                    "/api/industrial/observations?source=nrc_2025",
                    "/api/industrial/phmsa-enforcement",
                    "/api/industrial/review-candidates"):
            assert client.get(uri).status_code==401,uri
    with TestClient(app,headers={"Authorization":"Bearer "+"Z"*44}) as client:
        combined=client.get("/api/source-indices/status").json()
        assert combined["industrial_incidents"]["indexed_source_records"]==26
        assert combined["phmsa_wms_enforcement"]["indexed_source_records"]==2
        health=client.get("/api/industrial/status").json()
        assert health["observations"]["source_counts"]=={"nrc_2025":25,"csb":1}
        assert health["observations"]["review_only_pairs"]==1
        assert health["observations"]["production_deployment_verified"] is False
        assert health["primary_phmsa_incidents"]=="NOT_TESTED_OFFICIAL_SOURCE_ACCESS_BLOCKED"
        page=client.get("/api/industrial/observations",params={"source":"nrc_2025","limit":5})
        assert page.status_code==200,page.text
        assert page.json()["total"]==25
        assert len(page.json()["items"])==5
        assert not any("source_json" in row for row in page.json()["items"])
        assert all(row["site_link_status"]=="candidate_only_not_matched" for row in page.json()["items"])
        assert client.get("/api/industrial/observations",params={"source":"nrc_2025","state":"TX"}).json()["total"]==13
        assert client.get("/api/industrial/observations",params={"source":"csb"}).json()["total"]==1
        detail=client.get("/api/industrial/observations/nrc_2025/100001").json()
        assert detail["publisher_native_id"]=="100001"
        assert detail["insured_facility_verification"]=="NOT_PERFORMED"
        assert "company_as_reported" not in detail
        cases=client.get("/api/industrial/phmsa-enforcement",params={"operator_id":"00123"}).json()
        assert cases["total"]==1
        assert cases["source"]=="PHMSA_WMS_ENFORCEMENT_CASES_NOT_INCIDENT_REPORT_CENSUS"
        assert "source_row_json" not in cases["items"][0]
        assert client.get("/api/industrial/review-candidates").status_code==403

def test_invalid_queries_and_missing_ids_fail_safely(installed):
    with TestClient(app,headers={"Authorization":"Bearer "+"Z"*44}) as client:
        assert client.get("/api/industrial/observations?source=nrc_2019").status_code==422
        assert client.get("/api/industrial/observations?source=nrc_2025&limit=101").status_code==422
        assert client.get("/api/industrial/observations?source=nrc_2025&since=2025-99-01").status_code==422
        assert client.get("/api/industrial/observations?source=nrc_2025&state=TX%27%20OR%201=1--").json()["total"]==0
        assert client.get("/api/industrial/observations/nrc_2025/nonexistent").status_code==404
        assert client.get("/api/industrial/phmsa-enforcement?operator_id=00123%27%20OR%201=1--").json()["total"]==0
        assert client.get("/api/industrial/phmsa-enforcement?offset=100001").status_code==422

def test_only_individually_authenticated_reviewer_may_read_candidate_pairs(installed,monkeypatch):
    reviewer_password="reviewer-password-must-be-long"
    viewer_password="viewer-password-must-be-long"
    monkeypatch.setenv("FACILITY_RISK_USERS_JSON",json.dumps({
        "reviewerone":{"role":"reviewer","password_hash":make_password_hash(reviewer_password)},
        "viewerone":{"role":"viewer","password_hash":make_password_hash(viewer_password)}
    }))
    with TestClient(app,headers={"Authorization":"Basic "+base64.b64encode(("viewerone:"+viewer_password).encode()).decode()}) as viewer:
        assert viewer.get("/api/industrial/review-candidates").status_code==403
    with TestClient(app,headers={"Authorization":"Basic "+base64.b64encode(("reviewerone:"+reviewer_password).encode()).decode()}) as reviewer:
        response=reviewer.get("/api/industrial/review-candidates")
        assert response.status_code==200,response.text
        assert response.json()["total"]==1
        assert response.json()["items"][0]["status"]=="review_candidate_not_corrob"
        assert response.json()["classification"]=="REVIEW_ONLY_NOT_INDEPENDENT_CORROBORATION_OR_PHYSICAL_SITE"

def test_all_25_synthetic_industry_profiles_do_not_become_verified_sites(installed):
    # This checks safety behavior across 25 *synthetic* sector examples,
    # NOT a 25-site real-world facility acceptance assessment.
    assert len(set(INDUSTRIES))==25
    with TestClient(app,headers={"Authorization":"Bearer "+"Z"*44}) as client:
        page=client.get("/api/industrial/observations?source=nrc_2025&limit=50").json()
        assert page["total"]==25
        assert all(x["site_link_status"]=="candidate_only_not_matched" for x in page["items"])
        assert all("industry" not in x and "risk_score" not in x for x in page["items"])
        assert client.get("/api/industrial/review-candidates").status_code==403

def test_missing_mount_and_post_install_tamper_fail_closed(installed,monkeypatch):
    incident_root,_=installed
    monkeypatch.delenv("FACILITY_RISK_LANE_C_ROOT")
    with TestClient(app,headers={"Authorization":"Bearer "+"Z"*44}) as client:
        state=client.get("/api/industrial/status").json()["observations"]
        assert state["state"]=="not_configured"
        assert state["indexed_source_records"] is None
        assert client.get("/api/industrial/observations?source=nrc_2025").status_code==503
    monkeypatch.setenv("FACILITY_RISK_LANE_C_ROOT",str(incident_root))
    db=incident_root/"releases/test-industrial-2025/indexes/lane-c-source.sqlite"
    db.chmod(0o600)
    with db.open("ab") as f:f.write(b"tamper")
    _validate_index.cache_clear()
    with TestClient(app,headers={"Authorization":"Bearer "+"Z"*44}) as client:
        assert client.get("/api/industrial/status").json()["observations"]["state"]=="unavailable"
        assert client.get("/api/industrial/observations?source=nrc_2025").status_code==503

def test_injected_active_release_traversal_fails_closed(installed):
    root,_=installed
    pointer=root/"active-release.json"
    pointer.write_text(json.dumps({"release_id":"../../etc",
                                   "index_sha256":"a"*64}))
    with TestClient(app,headers={"Authorization":"Bearer "+"Z"*44}) as client:
        assert client.get("/api/industrial/status").json()["observations"]["state"]=="unavailable"
        assert client.get("/api/industrial/observations?source=nrc_2025").status_code==503

def test_host_acceptance_tool_refuses_non_tls_remote_and_weak_tokens(monkeypatch):
    from scripts.verify_private_host_industrial import verify
    monkeypatch.setenv("FACILITY_RISK_AUTH_TOKEN","Z"*44)
    with pytest.raises(ValueError,match="HTTPS"):
        verify("http://private.example.com")
    monkeypatch.setenv("FACILITY_RISK_AUTH_TOKEN","short")
    with pytest.raises(ValueError,match="strong"):
        verify("http://127.0.0.1:8765")

def test_real_universal_site_identity_review_only_incident_screen(installed,monkeypatch):
    """Twenty-five synthetic sector fixtures; only one registered candidate receives a query."""
    from facilityrisk.universal_registry import import_records
    from facilityrisk.industrial_facility_screen import screen_site
    workspace=Path(__import__("os").environ["FACILITY_RISK_DB"])
    with sqlite3.connect(workspace) as conn:
        conn.row_factory=sqlite3.Row
        import_records(conn,"EPA_FRS",[{
          "source_identifier":"110000000001",
          "name":"Example Industries Test Plant",
          "company":"Example Industries",
          "city":"Test City 1","state":"TX","country":"US",
          "industry":"Industrial manufacturing",
          "latitude":29.01,"longitude":-95.01,
          "address":"123 Synthetic Test Road"
        }],"https://www.epa.gov/frs",vintage="synthetic-test-2026")
        site_id=conn.execute("SELECT site_id FROM universal_source_records WHERE source_identifier='110000000001'").fetchone()[0]
    raw_site={
        "id":site_id,"name":"Example Industries Test Plant",
        "company":"Example Industries","city":"Test City 1","state":"TX",
        "country":"US","latitude":29.01,"longitude":-95.01,
        "coordinate_quality":"source_point_unverified"}
    sample=screen_site(raw_site,radius_km=2,limit=10)
    assert sample["state"]=="REVIEWER_SOURCE_CANDIDATE_SCREEN_COMPLETED"
    assert sample["source_namespaces_reviewed"]==2
    assert sample["candidate_rows_before_display_limit"]>=2
    assert all(r["review_status"]=="POTENTIAL_RELATIONSHIP_ONLY_UNVERIFIED" for r in sample["results"])
    assert all(not r["exact_site_identity_verified"] for r in sample["results"])
    assert all(not r["insured_loss_verified"] for r in sample["results"])
    assert "csb" in {r["source"] for r in sample["results"]}
    assert sample["verified_insured_matches"]==0
    assert sample["complete_historical_incident_coverage"] is False
    assert sample["no_zero_risk_inference"] is True
    assert "source_json" not in str(sample)

    outside=screen_site({**raw_site,"country":"CA"},radius_km=2)
    assert outside["state"]=="NOT_SCREENED_INSUFFICIENT_SOURCE_IDENTITY"
    assert outside["reported_candidate_count"] is None
    missing=screen_site({**raw_site,"city":""},radius_km=2)
    assert missing["reported_candidate_count"] is None

    viewer_password="viewerrandomlongpassword"
    reviewer_password="reviewerlongpasswordhere"
    monkeypatch.setenv("FACILITY_RISK_USERS_JSON",json.dumps({
        "viewerone":{"role":"viewer","password_hash":make_password_hash(viewer_password)},
        "reviewerone":{"role":"reviewer","password_hash":make_password_hash(reviewer_password)}
    }))
    endpoint="/api/universal-facilities/"+site_id+"/industrial-screen"
    with TestClient(app,headers={"Authorization":"Bearer "+"Z"*44}) as service:
        assert service.get(endpoint).status_code==403
    import base64
    viewer_header="Basic "+base64.b64encode(("viewerone:"+viewer_password).encode()).decode()
    reviewer_header="Basic "+base64.b64encode(("reviewerone:"+reviewer_password).encode()).decode()
    with TestClient(app,headers={"Authorization":viewer_header}) as viewer:
        assert viewer.get(endpoint).status_code==403
    with TestClient(app,headers={"Authorization":reviewer_header}) as reviewer:
        response=reviewer.get(endpoint,params={"radius_km":2,"limit":10})
        assert response.status_code==200,response.text
        assert response.json()["candidate_rows_before_display_limit"]>=2
        assert response.json()["verified_insured_matches"]==0
        assert response.json()["phmsa_enforcement_case_grain"]=="SEPARATE_NOT_INCLUDED"
        assert reviewer.get(endpoint,params={"radius_km":70}).status_code==422
        assert reviewer.get("/api/universal-facilities/no-such-site/industrial-screen").status_code==404

