"""Isolated source-only SQLite integration, count reconciliations and query guards."""
import csv
import json
import sqlite3
import pytest
from scripts.build_industrial_incidents import digest
from scripts.build_nrc_enriched import FIELDS as NRC_COLUMNS
from scripts.build_csb_incidents import COLUMNS as CSB_COLUMNS
from scripts.industrial_incident_io import gzip_csv_writer
from scripts.index_lane_c_incidents import index_sources, search_source, audit_multiyear_source_coverage

def staged(tmp_path):
    nrc=tmp_path/"nrc.csv.gz"
    csb=tmp_path/"csb.csv.gz"
    nrc_rows=[
        {"source_id":"000001","incident_date":"2025-01-02","incident_city":"Houston",
         "incident_state":"TX","latitude":"29.75","longitude":"-95.3333",
         "report_status":"NRC_initial_notification_unverified",
         "site_link_status":"candidate_only_not_matched",
         "source_document":"https://nrc.uscg.mil/FOIAFiles/CY25.xlsx"},
        {"source_id":"000002","incident_date":"2025-02-03","incident_city":"Cleveland",
         "incident_state":"OH","report_status":"NRC_initial_notification_unverified",
         "site_link_status":"candidate_only_not_matched",
         "source_document":"https://nrc.uscg.mil/FOIAFiles/CY25.xlsx"}]
    csb_rows=[{"source_id":"csb:2026-09-01:7","original_number":"7",
               "incident_date":"2024-05-01","incident_city":"Houston","incident_state":"TX",
               "evidence_status":"csb_reported_accidental_release_unverified_outcome",
               "site_link_status":"candidate_only_not_matched",
               "source_document":"https://www.csb.gov/test.xlsx"}]
    for path,headers,records in [(nrc,NRC_COLUMNS,nrc_rows),(csb,CSB_COLUMNS,csb_rows)]:
        with gzip_csv_writer(path) as file:
            writer=csv.DictWriter(file,fieldnames=headers)
            writer.writeheader()
            for row in records:
                writer.writerow(row)
    nr={"year":2025,"raw_sha256":"a"*64,"normalized_sha256":digest(nrc),
        "accepted_rows":2,"rejected_rows":0,"coordinate_records":1}
    cr={"release":"2026-09-01","raw_sha256":"b"*64,"normalized_sha256":digest(csb),
        "accepted_rows":1,"rejected_rows":0,"raw_data_rows":1}
    nm=tmp_path/"nrc-manifest.json"
    cm=tmp_path/"csb-manifest.json"
    nm.write_text(json.dumps(nr))
    cm.write_text(json.dumps(cr))
    return nrc,nm,csb,cm

def test_source_index_count_identity_query_and_uncertainty(tmp_path):
    nrc,nm,csb,cm=staged(tmp_path)
    db=tmp_path/"private-not-deployed.sqlite"
    audit=index_sources(db,[("nrc",nrc,nm),("csb",csb,cm)],tmp_path/"aggregate-index.json")
    assert audit["state"]=="INDEXED_EPHEMERAL_CI_NOT_DEPLOYED"
    assert audit["quick_check"]=="ok"
    assert audit["total_indexed_ephemeral"]==3
    assert audit["indexed_persistent_production"]==0
    assert audit["deployed_in_app"]==0
    assert audit["sources"]["nrc"]["coordinates_indexed"]==1
    assert audit["sources"]["csb"]["source_id_scope"]=="release-scoped"
    assert search_source(db,source="nrc")["total"]==2
    assert search_source(db,source="nrc",state="TX")["total"]==1
    assert search_source(db,source="nrc",since="2025-02-01")["total"]==1
    assert search_source(db,source="csb")["items"][0]["source_id"]=="csb:2026-09-01:7"
    with sqlite3.connect(db) as c:
        assert c.execute("PRAGMA quick_check").fetchone()[0]=="ok"
        assert c.execute("SELECT COUNT(*) FROM source_incidents WHERE site_link_status='candidate_only_not_matched'").fetchone()[0]==3
        assert c.execute("SELECT COUNT(*) FROM source_incidents WHERE latitude IS NOT NULL").fetchone()[0]==1
        assert c.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name LIKE 'source_incidents_%'").fetchone()[0]>=3
    with pytest.raises(ValueError,match="exists"):
        index_sources(db,[("nrc",nrc,nm)],tmp_path/"no.json")
    with pytest.raises(ValueError,match="paging"):
        search_source(db,source="nrc",page_size=1000)

def test_checksum_refuses_invalid_manifest_and_leaves_no_db(tmp_path):
    nrc,nm,csb,cm=staged(tmp_path)
    data=json.loads(nm.read_text())
    data["normalized_sha256"]="deadbeef"
    nm.write_text(json.dumps(data))
    db=tmp_path/"never-served.sqlite"
    with pytest.raises(ValueError,match="SHA"):
        index_sources(db,[("nrc",nrc,nm),("csb",csb,cm)],tmp_path/"audit.json")
    assert not db.exists()

def test_annual_nrc_namespaces_do_not_merge_identical_native_ids(tmp_path):
    nrc,nm,csb,cm=staged(tmp_path)
    older=tmp_path/"older-2024.json"
    payload=json.loads(nm.read_text())
    payload["year"]=2024
    older.write_text(json.dumps(payload))
    db=tmp_path/"cross-vintage.sqlite"
    report=index_sources(db,[("nrc_2025",nrc,nm),("nrc_2024",nrc,older),
                             ("csb",csb,cm)],tmp_path/"namespaced-audit.json")
    assert report["total_indexed_ephemeral"]==5
    evidence=audit_multiyear_source_coverage(db)
    assert evidence["native_source_id_values_present_in_multiple_yearly_workbooks"]==2
    assert evidence["same_native_id_cross_year_pairs"]==2
    assert evidence["vintage_event_date_and_reported_geography"]["nrc_2025"]["coordinate_rows"]==1
    assert any(x["received_workbook_namespace"]=="nrc_2024" and x["incident_calendar_year"]=="2025" for x in evidence["nrc_event_year_distribution_by_receipt_cohort"])
    assert report["sources"]["nrc_2024"]["indexed_rows_ephemeral"]==2
    assert report["sources"]["nrc_2025"]["indexed_rows_ephemeral"]==2
    assert search_source(db,source="nrc_2024")["items"][0]["source"]=="nrc_2024"
    assert search_source(db,source="nrc_2025")["items"][0]["source"]=="nrc_2025"
    with sqlite3.connect(db) as c:
        # Identical source-native ID, distinct reporting-year observations.
        assert c.execute("SELECT COUNT(*) FROM source_incidents WHERE source_id='000001'").fetchone()[0]==2
    with pytest.raises(ValueError, match="vintage disagree"):
        index_sources(tmp_path/"invalid-annual.sqlite",
                      [("nrc_2022",nrc,nm)],tmp_path/"bad.json")
