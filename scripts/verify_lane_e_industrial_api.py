"""Smoke actual first-party Lane C publisher indexes through authenticated FastAPI.

Run ONLY after the private Lane C installers have reproduced and installed the
real official NRC/CSB and PHMSA WMS sources onto a *temporary runner* mount.
No source-row, ID, coordinate, or personal-text data is written to output.
All published evidence is aggregate count/digest/latency only.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import base64
import json
import os
from pathlib import Path
import secrets
import sys
import time
from fastapi.testclient import TestClient

# Support direct script invocation in a clean GitHub Actions checkout.
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

EXPECTED_NRC=429122
EXPECTED_CSB=674
EXPECTED_WMS=5089
EXPECTED_REVIEWS=135
YEARS=tuple(range(2010,2027))

def run(incidents,wms,output):
    root_a=Path(incidents).resolve()
    root_b=Path(wms).resolve()
    if not root_a.is_dir() or not root_b.is_dir() or root_a==root_b:
        raise ValueError("Two DISTINCT real private source release roots are required")
    os.environ["FACILITY_RISK_LANE_C_ROOT"]=str(root_a)
    os.environ["FACILITY_RISK_PHMSA_WMS_ROOT"]=str(root_b)
    os.environ["FACILITY_RISK_REQUIRE_AUTH"]="1"
    os.environ["FACILITY_RISK_ENABLE_WRITES"]="0"
    os.environ["FACILITY_RISK_DB"]=str(Path(incidents).parent/"fresh-api-test-workspace.sqlite")
    token=secrets.token_urlsafe(48)
    os.environ["FACILITY_RISK_AUTH_TOKEN"]=token

    from facilityrisk.app import app
    from facilityrisk.security import make_password_hash

    results={"checked_at":datetime.now(timezone.utc).isoformat(),
             "stage":"REAL_OFFICIAL_SOURCE_TEMPORARY_PRIVATE_BACKEND_API_SMOKE_NOT_PRODUCTION",
             "authenticated_private_api_checked":False,
             "production_host_deployed":False,
             "verified_insured_site_matches":0,
             "insured_claims_or_losses_verified":0,
             "sources":{},
             "performance_milliseconds":{},
             "no_source_rows_or_pii_exported":True}
    with TestClient(app) as anon:
        for url in ("/api/industrial/status","/api/industrial/observations?source=nrc_2025",
                    "/api/industrial/phmsa-enforcement","/api/industrial/review-candidates"):
            if anon.get(url).status_code!=401:
                raise AssertionError("Unauthenticated industrial index API must return 401")
    with TestClient(app,headers={"Authorization":"Bearer "+token}) as client:
        combined=client.get("/api/source-indices/status")
        assert combined.status_code==200,combined.text
        meta=combined.json()
        observed=meta["industrial_incidents"]
        cases=meta["phmsa_wms_enforcement"]
        assert observed["state"]=="ready_private",observed
        assert cases["state"]=="ready_private",cases
        assert observed["indexed_source_records"]==EXPECTED_NRC+EXPECTED_CSB,observed
        assert cases["indexed_source_records"]==EXPECTED_WMS,cases
        assert observed["review_only_pairs"]==EXPECTED_REVIEWS
        assert cases["incident_census_status"]=="NOT_TESTED_ACCESS_BLOCKED"
        assert observed["production_deployment_verified"] is False
        assert cases["production_deployment_verified"] is False
        assert len(observed["source_counts"])==18
        assert client.get("/api/industrial/review-candidates").status_code==403

        for year in YEARS:
            namespace="nrc_"+str(year)
            expected=observed["source_counts"][namespace]
            start=time.perf_counter()
            response=client.get("/api/industrial/observations",
                params={"source":namespace,"limit":2,"offset":0})
            latency=round((time.perf_counter()-start)*1000,1)
            assert response.status_code==200,response.text
            row=response.json()
            assert row["total"]==expected
            assert len(row["items"])==2
            assert all(x["site_link_status"]=="candidate_only_not_matched" for x in row["items"])
            assert all("source_json" not in x for x in row["items"])
            if latency>12000:
                raise AssertionError("Private source API slow (>12s) for "+namespace)
            results["sources"][namespace]={"indexed":expected,"private_API_query":"PASS"}
            results["performance_milliseconds"][namespace]=latency
        assert sum(results["sources"][k]["indexed"] for k in results["sources"])==EXPECTED_NRC

        current=client.get("/api/industrial/observations",params={"source":"csb","limit":2})
        assert current.status_code==200,current.text
        assert current.json()["total"]==EXPECTED_CSB
        assert all(r["latitude"] is None for r in current.json()["items"])
        results["sources"]["csb"]={"indexed":EXPECTED_CSB,"private_API_query":"PASS"}

        phmsa=client.get("/api/industrial/phmsa-enforcement",params={"limit":3})
        assert phmsa.status_code==200,phmsa.text
        assert phmsa.json()["total"]==EXPECTED_WMS
        assert len(phmsa.json()["items"])==3
        assert phmsa.json()["source"]=="PHMSA_WMS_ENFORCEMENT_CASES_NOT_INCIDENT_REPORT_CENSUS"
        assert all("source_row_json" not in r for r in phmsa.json()["items"])
        results["sources"]["phmsa_wms_enforcement_cases"]={"indexed":EXPECTED_WMS,
                                                             "private_API_query":"PASS",
                                                             "not_pipeline_accident_census":True}

        first=current.json()["items"][0]
        detail=client.get("/api/industrial/observations/csb/"+first["source_id"])
        assert detail.status_code==200,detail.text
        assert detail.json()["insured_facility_verification"]=="NOT_PERFORMED"
        assert client.get("/api/industrial/observations?source=nrc_2025&limit=1000").status_code==422
        assert client.get("/api/industrial/observations?source=nrc_2025&since=2025-99-99").status_code==422
        assert client.get("/api/industrial/observations?source=nrc_1999").status_code==422
        assert client.get("/api/industrial/observations/nrc_2025/not-a-source-id").status_code==404

        viewer_name="private-reader"
        reviewer_name="private-source-reviewer"
        viewer_pass=secrets.token_urlsafe(32)
        reviewer_pass=secrets.token_urlsafe(32)
        os.environ["FACILITY_RISK_USERS_JSON"]=json.dumps({
            viewer_name:{"role":"viewer","password_hash":make_password_hash(viewer_pass)},
            reviewer_name:{"role":"reviewer","password_hash":make_password_hash(reviewer_pass)}
        })
        with TestClient(app,headers={"Authorization":"Basic "+base64.b64encode((viewer_name+":"+viewer_pass).encode()).decode()}) as viewer:
            assert viewer.get("/api/industrial/review-candidates").status_code==403
        with TestClient(app,headers={"Authorization":"Basic "+base64.b64encode((reviewer_name+":"+reviewer_pass).encode()).decode()}) as reviewer:
            pairs=reviewer.get("/api/industrial/review-candidates",params={"limit":3})
            assert pairs.status_code==200,pairs.text
            assert pairs.json()["total"]==EXPECTED_REVIEWS
            assert all(p["status"]=="review_candidate_not_corrob" for p in pairs.json()["items"])
        results.update({"source_namespaces":18,"accepted_source_observations":EXPECTED_NRC+EXPECTED_CSB,
                        "phmsa_enforcement_case_rows":EXPECTED_WMS,
                        "cross_regulator_review_only_pairs":EXPECTED_REVIEWS,
                        "nrc_csb_index_sha256":observed["index_sha256"],
                        "phmsa_wms_index_sha256":cases["index_sha256"],
                        "authenticated_private_api_checked":True,
                        "role_restricted_review_candidates":"PASS",
                        "unknown_or_invalid_queries_fail_closed":"PASS",
                        "production_host_deployed":False,
                        "primary_phmsa_pipeline_hazmat_census":"NOT_TESTED_HTTP403"})
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(results,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in results.items()
           if k not in ("sources","performance_milliseconds")},indent=2))
    return results

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--incidents-root",type=Path,required=True)
    p.add_argument("--wms-root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    run(a.incidents_root,a.wms_root,a.output)
