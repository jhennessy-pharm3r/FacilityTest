"""Cross-agency matches are source-only review candidates, not corroborated sites."""
import csv
import gzip
import json
import sqlite3
from scripts.build_industrial_incidents import digest
from scripts.build_nrc_enriched import FIELDS as NRC_FIELDS
from scripts.build_csb_incidents import COLUMNS as CSB_FIELDS
from scripts.industrial_incident_io import gzip_csv_writer
from scripts.index_lane_c_incidents import index_sources
from scripts.lane_c_review_candidates import build_review_candidates, state_code

def _write(path, fields, rows):
    with gzip_csv_writer(path) as stream:
        writer=csv.DictWriter(stream,fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

def test_strict_nrc_csb_review_candidate_not_auto_merge(tmp_path):
    nrc=tmp_path/"nrc.gz"
    csb=tmp_path/"csb.gz"
    _write(nrc,NRC_FIELDS,[{
        "source_id":"00001","incident_date":"2025-03-04",
        "company_as_reported":"Example Manufacturing LLC",
        "incident_city":"Houston","incident_state":"TX",
        "report_status":"NRC_initial_notification_unverified",
        "site_link_status":"candidate_only_not_matched",
        "source_document":"https://nrc.uscg.mil/FOIAFiles/CY25.xlsx"}])
    _write(csb,CSB_FIELDS,[{
        "source_id":"csb:2026-09-01:42","original_number":"42",
        "incident_date":"2025-03-04",
        "company_as_reported":"Example Manufacturing LLC",
        "incident_city":"Houston","incident_state":"Texas",
        "evidence_status":"csb_reported_accidental_release_unverified_outcome",
        "site_link_status":"candidate_only_not_matched",
        "source_document":"https://www.csb.gov/assets/report.xlsx"}])
    nm=tmp_path/"nrc.json"
    cm=tmp_path/"csb.json"
    nm.write_text(json.dumps({"year":2025,"raw_sha256":"a"*64,
        "normalized_sha256":digest(nrc),"accepted_rows":1,"rejected_rows":0,
        "coordinate_records":0}))
    cm.write_text(json.dumps({"release":"2026-09-01","raw_sha256":"b"*64,
        "normalized_sha256":digest(csb),"accepted_rows":1,"rejected_rows":0,
        "raw_data_rows":1}))
    db=tmp_path/"review-only.sqlite"
    index_sources(db,[("nrc_2025",nrc,nm),("csb",csb,cm)],tmp_path/"audit.json")
    report=build_review_candidates(db)
    assert report["review_candidate_pairs"]==1
    assert report["verified_shared_events"]==0
    assert report["insured_physical_site_links"]==0
    assert state_code("Texas")==state_code("TX")
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT status FROM lane_c_review_candidates").fetchone()[0]=="review_candidate_not_corrob"
        assert con.execute("SELECT COUNT(*) FROM source_incidents WHERE site_link_status='candidate_only_not_matched'").fetchone()[0]==2

def test_no_match_without_independent_same_date_and_company(tmp_path):
    # No false joins from date/city alone, and no joins to unknown companies.
    from scripts.lane_c_review_candidates import can_match,normalized_text
    assert not can_match(("2025-01-01","TX","HOUSTON","UNKNOWN"))
    assert not can_match(("2025-01-01","","HOUSTON","REAL COMPANY"))
    assert not can_match(("2025-01-01","TX","HOUSTON","X"))
    assert normalized_text("A, B & Co.")=="A B CO"
