"""Deterministic source-monitor decisions; fixtures contain NO official report rows."""
from __future__ import annotations
from scripts.monitor_lane_c_official_refresh import compare,BASELINE

def _audit():
    return {
        "current_year_nrc":{
            "state":"PARTIAL_CURRENT_CALENDAR_YEAR_MASTER_ROWS_STAGED_NOT_INDEXED",
            "accepted":BASELINE["nrc_current"]["accepted"],
            "raw_sha256":BASELINE["nrc_current"]["raw_sha256"]
        },
        "csb_release_catalog":{
            "state":"LIVE_OFFICIAL_PAGE_INVENTORIED",
            "latest_filename_date":"2026-09-01"
        },
        "csb_current_release":{"release_rows_with_unique_number":675}
    }

def _wms():
    return {
        "state":"OFFICIAL_ENFORCEMENT_CASES_CONTENT_VALIDATED_INDEXED_EPHEMERAL_NOT_INCIDENT_CENSUS",
        "sha256":BASELINE["phmsa_enforcement"]["raw_sha256"],
        "normalized_case_rows":5089
    }

def test_pinned_sources_match_without_deployment_claim():
    q=compare(_audit(),_wms())
    assert q["state"]=="OFFICIAL_SOURCES_MATCH_VERIFIED_BASELINE"
    assert not q["requires_operator_source_review"]
    assert q["app_deployed_records"]==0
    assert q["durable_private_database_promoted"] is False
    assert all(x["status"]=="UNCHANGED" for x in q["publisher_source_health"])

def test_nrc_provisional_change_requests_manual_revalidation_not_auto_merge():
    a=_audit()
    a["current_year_nrc"]["raw_sha256"]="a"*64
    a["current_year_nrc"]["accepted"]=17950
    q=compare(a,_wms())
    assert q["state"]=="OFFICIAL_SOURCE_REVIEW_REQUIRED"
    assert q["publisher_source_health"][0]["status"]=="REVIEW_REQUIRED"
    assert q["primary_phmsa_incident_reports"]=="NOT_TESTED_ACCESS_BLOCKED"
    assert q["insured_facility_links_confirmed"]==0

def test_new_csb_quarter_does_not_reuse_native_row_id_without_review():
    a=_audit()
    a["csb_release_catalog"]["latest_filename_date"]="2026-12-01"
    q=compare(a,_wms())
    assert q["requires_operator_source_review"]
    assert any(r["status"]=="REVIEW_REQUIRED" for r in q["publisher_source_health"])

def test_403_and_content_collapse_fail_closed_not_zero_incidents():
    a=_audit()
    a["current_year_nrc"]["accepted"]=0
    w=_wms()
    w["state"]="BLOCKED_OR_SCHEMA_UNVERIFIED"
    w["error"]="HTTPError: 403 Forbidden"
    q=compare(a,w)
    assert q["state"]=="SOURCE_BLOCKED_NEEDS_OPERATOR"
    assert q["requires_operator_source_review"]
    assert q["app_deployed_records"]==0
    assert not any(r["status"]=="UNCHANGED" for r in q["publisher_source_health"]
                   if r["source"] in ("USCG_NRC_CY2026","PHMSA_WMS_ENFORCEMENT"))

def test_changed_wms_does_not_claim_any_new_pipeline_incidents():
    w=_wms()
    w["normalized_case_rows"]=5100
    q=compare(_audit(),w)
    assert q["requires_operator_source_review"]
    assert q["record_classes"][-1]=="PHMSA WMS enforcement case records"
    assert q["primary_phmsa_incident_reports"]=="NOT_TESTED_ACCESS_BLOCKED"

