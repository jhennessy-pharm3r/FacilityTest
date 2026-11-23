"""Refresh-monitor only: compare official first-party source probes to approved baselines.

Never install a changed NRC/CSB/PHMSA source automatically. NRC 2026 is a
PROVISIONAL receipt workbook (not incident date/year) and may change daily.
The monitor may request manual review; it never downgrades the last verified
private index, never turns an HTTP 403 into zero incidents, and never publishes
raw source rows, host names or credentials.
"""
from __future__ import annotations
from datetime import datetime,timezone
import argparse
import json
from pathlib import Path

BASELINE={
 "nrc_current":{"vintage":"2026","accepted":17827,
  "raw_sha256":"d4da14c0e8a67b230b2dcdd000b24df1e0e7f6ca30d422a8e49b4f3e80ba1155"},
 "csb_current":{"release":"2026-09-01","source_rows":675},
 "phmsa_enforcement":{"accepted_cases":5089,
  "raw_sha256":"23d8d5c62dd93f848ba3f22d4fc24d0c7f3d90b750aea2ac7223168401725bb7"},
 "source_record_warning":"NRC/CSB observations and PHMSA enforcement cases are not confirmed insured site claims"
}

def compare(nrc_audit,phmsa_audit,baseline=BASELINE):
    """Pure monitor decision, no hardcoded claims of deployed or site coverage."""
    findings=[]
    blockers=[]
    def signal(source,status,reason,**extra):
        findings.append({"source":source,"status":status,"reason":reason,**extra})
        if status in ("BLOCKED","SCHEMA_QA_FAILURE"):
            blockers.append(source)
    nrc=nrc_audit.get("current_year_nrc") or {}
    expected=baseline["nrc_current"]
    accepted=nrc.get("accepted")
    if not isinstance(accepted,int) or accepted<=0 or not nrc.get("raw_sha256"):
        signal("USCG_NRC_CY2026","BLOCKED","Actual accepted source rows or raw SHA-256 unavailable",error=nrc.get("error"))
    elif accepted < round(expected["accepted"]*.85):
        signal("USCG_NRC_CY2026","SCHEMA_QA_FAILURE","Unexpected publisher row collapse",accepted=accepted,
               previous_verified=expected["accepted"])
    elif nrc["raw_sha256"]!=expected["raw_sha256"] or accepted!=expected["accepted"]:
        signal("USCG_NRC_CY2026","REVIEW_REQUIRED","Provisional official source bytes/row count changed; re-download all, verify and install new immutable release only after QA",
               accepted=accepted,previous_verified=expected["accepted"],
               raw_sha256=nrc["raw_sha256"],publisher_vintage="2026 OPEN_PARTIAL")
    else:
        signal("USCG_NRC_CY2026","UNCHANGED","Official provisional original matches pinned tested cohort",
               accepted=accepted,raw_sha256=nrc["raw_sha256"])
    csb=nrc_audit.get("csb_current_release") or {}
    latest=nrc_audit.get("csb_release_catalog") or {}
    latest_day=latest.get("latest_filename_date")
    current_day=baseline["csb_current"]["release"]
    if latest.get("state")=="BLOCKED":
        signal("CSB_PUBLISHER_LANDING","BLOCKED","Official quarterly release discovery inaccessible",error=latest.get("error"))
    elif latest_day and latest_day>current_day:
        signal("CSB_PUBLISHER_LANDING","REVIEW_REQUIRED","Official CSB later quarterly release listed; old row Number is not cross-vintage immutable",
               newest_official_release=latest_day,pinned_release=current_day)
    elif not latest_day:
        signal("CSB_PUBLISHER_LANDING","REVIEW_REQUIRED","Official latest release link not proven, independent audit needed",
               pinned_release=current_day)
    else:
        signal("CSB_PUBLISHER_LANDING","UNCHANGED","No later publicly enumerated CSB vintage",pinned_release=current_day)
    if not isinstance(csb.get("release_rows_with_unique_number"),int):
        signal("CSB_CURRENT_2026_09","BLOCKED","Published September source rows/schema unavailable",error=csb.get("error"))
    elif (csb["release_rows_with_unique_number"]!=baseline["csb_current"]["source_rows"]):
        signal("CSB_CURRENT_2026_09","REVIEW_REQUIRED","Pinned CSB release Number/row count changed: manual identity correction review",
               reported=csb["release_rows_with_unique_number"],previous=baseline["csb_current"]["source_rows"])
    else:
        signal("CSB_CURRENT_2026_09","UNCHANGED","Pinned quarterly row count matches verified release",
               rows=csb["release_rows_with_unique_number"])
    wms=phmsa_audit or {}
    case_rows=wms.get("normalized_case_rows")
    cases_baseline=baseline["phmsa_enforcement"]
    if (wms.get("state")!="OFFICIAL_ENFORCEMENT_CASES_CONTENT_VALIDATED_INDEXED_EPHEMERAL_NOT_INCIDENT_CENSUS"
        or not isinstance(case_rows,int) or not wms.get("sha256")):
        signal("PHMSA_WMS_ENFORCEMENT","BLOCKED","Official WMS case-only source not independently verified",
               error=wms.get("error"))
    elif case_rows < round(cases_baseline["accepted_cases"]*.85):
        signal("PHMSA_WMS_ENFORCEMENT","SCHEMA_QA_FAILURE","Published enforcement cases unexpectedly collapsed",
               reported=case_rows,previous=cases_baseline["accepted_cases"])
    elif case_rows!=cases_baseline["accepted_cases"] or wms["sha256"]!=cases_baseline["raw_sha256"]:
        signal("PHMSA_WMS_ENFORCEMENT","REVIEW_REQUIRED","Published first-party enforcement subset changed; do not reinterpret as incident reports",
               reported=case_rows,previous=cases_baseline["accepted_cases"],raw_sha256=wms["sha256"])
    else:
        signal("PHMSA_WMS_ENFORCEMENT","UNCHANGED","Official WMS enforcement cases match pinned baseline",
               count=case_rows,raw_sha256=wms["sha256"])
    actions=sorted(set(x["status"] for x in findings))
    status="SOURCE_BLOCKED_NEEDS_OPERATOR" if blockers else (
           "OFFICIAL_SOURCE_REVIEW_REQUIRED" if "REVIEW_REQUIRED" in actions else
           "OFFICIAL_SOURCES_MATCH_VERIFIED_BASELINE")
    return {
      "checked_at":datetime.now(timezone.utc).isoformat(),
      "state":status,
      "publisher_source_health":findings,
      "requires_operator_source_review":status!="OFFICIAL_SOURCES_MATCH_VERIFIED_BASELINE",
      "record_classes":["NRC report notifications","CSB accidental-release source rows","PHMSA WMS enforcement case records"],
      "primary_phmsa_incident_reports":"NOT_TESTED_ACCESS_BLOCKED",
      "durable_private_database_promoted":False,
      "app_deployed_records":0,
      "insured_facility_links_confirmed":0,
      "zero_source_reports_never_means_zero_incident_risk":True,
      "recommended_action":"Preserve last verified release. Inspect official source, native keys, raw/normalized SHA and schema before audited refresh."
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--current-audit",type=Path,required=True)
    p.add_argument("--wms-audit",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--strict",action="store_true",
       help="Fail CI if publisher is blocked, a release changes, or schema/count anomalies appear")
    a=p.parse_args()
    first=json.loads(a.current_audit.read_text(encoding="utf-8"))
    second=json.loads(a.wms_audit.read_text(encoding="utf-8"))
    decision=compare(first,second)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(decision,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(decision,indent=2))
    if a.strict and decision["requires_operator_source_review"]:
        raise SystemExit("Official source changed or blocked; preserve last validated release and inspect aggregate JSON")

if __name__=="__main__":
    main()
