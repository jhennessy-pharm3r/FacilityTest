"""Operator acceptance of an ACTUALLY RUNNING authenticated private Lane E host.

Read-only checks only; use FACILITY_RISK_AUTH_TOKEN from an approved protected
environment (never command-line secret). This cannot substitute for verified
production SSO, tenancy or physical insured-site reviews.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
import requests

def verify(base,*,expected_observations=429796,expected_wms_cases=5089):
    url=base.rstrip("/")
    parsed=urlsplit(url)
    if (parsed.scheme not in ("http","https") or not parsed.hostname or
        (parsed.hostname not in ("127.0.0.1","::1","localhost") and parsed.scheme!="https")):
        raise ValueError("Non-loopback private source API must have HTTPS")
    token=os.environ.get("FACILITY_RISK_AUTH_TOKEN","")
    if len(token)<24:
        raise ValueError("Set strong FACILITY_RISK_AUTH_TOKEN in protected environment")
    session=requests.Session()
    session.trust_env=False
    def get(path,auth=True,params=None):
        resp=session.get(url+path,headers={
            **({"Authorization":"Bearer "+token} if auth else {}),
            "Accept":"application/json"},params=params,timeout=(5,25))
        return resp
    unauthorized=get("/api/industrial/status",auth=False)
    if unauthorized.status_code!=401:
        raise ValueError("Host industrial endpoints do not fail closed without credentials")
    results=get("/api/industrial/status")
    results.raise_for_status()
    payload=results.json()
    first=payload.get("observations",{})
    second=payload.get("phmsa_enforcement",{})
    if first.get("state") not in ("ready_private","ready_private_partial") or second.get("state")!="ready_private":
        raise ValueError("Required installed source release unavailable on this host")
    if (first.get("indexed_source_records")!=expected_observations or
        second.get("indexed_source_records")!=expected_wms_cases):
        raise ValueError("Installed source counts differ from approved publisher snapshot")
    source_counts=first.get("source_counts",{})
    missing=first.get("missing_nrc_source_years",[])
    years=[f"nrc_{year}" for year in range(2010,2027)]
    if (not isinstance(missing,list) or missing!=[year for year in years if year not in source_counts] or
        len(source_counts)!=18-len(missing) or "csb" not in source_counts or "nrc_2025" not in source_counts or
        first.get("state")!=("ready_private_partial" if missing else "ready_private") or
        not isinstance(first.get("review_only_pairs"),int) or first["review_only_pairs"]<0):
        raise ValueError("Official source coverage/identity audit inconsistent; missing years must be explicit")
    for year in missing:
        check=get("/api/industrial/observations",params={"source":year,"limit":1})
        if check.status_code!=503:
            raise ValueError("Missing original publisher year must be unavailable (503), not zero source rows")
    if payload.get("physical_facility_matches_verified")!=0:
        raise ValueError("Unreviewed facility-link status unexpectedly promoted")
    events=get("/api/industrial/observations",params={"source":"nrc_2025","limit":3})
    events.raise_for_status()
    if events.json()["total"]!=first["source_counts"]["nrc_2025"]:
        raise ValueError("Running incident API count mismatches active release")
    if any(x["site_link_status"]!="candidate_only_not_matched" or "source_json" in x
           for x in events.json()["items"]):
        raise ValueError("Raw industrial report/private site status exposed")
    cases=get("/api/industrial/phmsa-enforcement",params={"limit":3})
    cases.raise_for_status()
    if cases.json()["total"]!=expected_wms_cases:
        raise ValueError("Running PHMSA case API count mismatches separate WMS index")
    reviewer=get("/api/industrial/review-candidates")
    if reviewer.status_code!=403:
        raise ValueError("Service bearer token must not bypass individual reviewer authorization")
    return {
      "checked_at":datetime.now(timezone.utc).isoformat(),
      "stage":"OPERATOR_INITIATED_RUNNING_PRIVATE_HOST_READONLY_API_CHECK",
      "observations":first["indexed_source_records"],
      "phmsa_wms_enforcement_cases":second["indexed_source_records"],
      "source_namespaces":len(source_counts),
      "missing_original_nrc_years":missing,
      "full_historic_nrc_coverage_verified":not missing,
      "official_nrc_2010_2026_source_gate":"BLOCKED_PARTIAL" if missing else "ALL_YEARS_AVAILABLE",
      "cross_agency_pairs_review_only":first["review_only_pairs"],
      "read_only_authenticated_queries":"PASS",
      "missing_credentials_401":"PASS",
      "service_account_reviewer_403":"PASS",
      "physical_site_links_validated":0,
      "production_SSO_tenant_security_acceptance":"SEPARATELY_REQUIRED",
      "primary_phmsa_pipeline_incident_reports":"NOT_TESTED_ACCESS_BLOCKED",
      "note":"API is usable on THIS configured host; no claim of insurer production approval or insured losses."
    }

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--base",default="http://127.0.0.1:8765",
                   help="Private loopback or HTTPS backend base URL; never public GitHub Pages")
    p.add_argument("--expected-observations",type=int,default=429796)
    p.add_argument("--expected-wms-cases",type=int,default=5089)
    p.add_argument("--output",type=Path,
                   help="Optional local-only aggregate QA JSON; no token, IP or source rows written")
    a=p.parse_args()
    result=verify(a.base,expected_observations=a.expected_observations,
                  expected_wms_cases=a.expected_wms_cases)
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))
