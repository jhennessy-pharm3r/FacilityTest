"""PHMSA reports: official publisher-index document evidence, not an incident census."""
from __future__ import annotations
import csv
import gzip
import json
import sqlite3
from pathlib import Path
import pytest

from scripts.build_phmsa_failure_investigations import (
    extract_index,build,index,validate,agency_date
)

FIXTURE="""<!DOCTYPE html><html><body><main>
<table><thead><tr><th>Operator Name</th><th>Operator Id</th><th>System Type</th>
<th>Apparent Cause</th><th>State</th><th>Failure Date</th><th>Date Posted</th></tr></thead>
<tbody>
<tr><td><a href="/incident-reporting/report-alpha">Alpha Pipeline</a></td><td>1234</td>
<td>Hazardous Liquid</td><td>Natural Force Damage</td><td>KS</td><td>Dec 7, 2022</td><td>Oct 25, 2024</td></tr>
<tr><td><a href="/incident-reporting/report-alpha">Alpha Pipeline</a></td><td>1234</td>
<td>Hazardous Liquid</td><td>Natural Force Damage</td><td>KS</td><td>Dec 7, 2022</td><td>Jan 15, 2025</td></tr>
<tr><td><a href="/incident-reporting/report-beta">Beta Pipeline</a></td><td></td>
<td>Gas Transmission</td><td>Leak</td><td>OCS</td><td>Sept 9/2015</td><td>Jun 6, 2015</td></tr>
<tr><td><a href="https://untrusted.invalid/report">Bad Redirect</a></td><td>222</td>
<td>Hazardous Liquid</td><td>Fire</td><td>TX</td><td>Jan 01, 2020</td><td>Feb 01, 2020</td></tr>
</tbody></table></main></body></html>"""

def test_parses_actual_phmsa_style_headings_and_preserves_revisions(tmp_path):
    rows,summary,states,types=extract_index(FIXTURE.encode(),"2026-10-23",min_rows=3)
    assert summary["source_table_nonempty_rows"]==4
    assert summary["accepted_publisher_index_rows"]==3
    assert summary["rejected_missing_publisher_identity_or_date"]==1
    assert summary["missing_source_operator_id"]==1
    assert summary["posted_date_earlier_than_failure_date"]==1
    assert summary["source_composite_repeated_observations"]==1
    assert summary["distinct_nonempty_operator_ids"]==1
    assert states["OCS"]==1
    assert rows[0]["source_row_number"]==2
    assert rows[0]["operator_id_as_reported"]=="1234"
    assert rows[1]["detail_report_url"]==rows[0]["detail_report_url"]
    assert rows[2]["date_quality"]=="posted_precedes_failure"
    assert all(r["site_link_status"]=="candidate_only_not_matched" for r in rows)

    raw=tmp_path/"index.html"
    raw.write_text(FIXTURE)
    out=tmp_path/"published-list.csv.gz"
    manifest=tmp_path/"qa.json"
    audit=build(raw,out,manifest,snapshot="2026-10-23",minimum_rows=3)
    assert audit["accepted_publisher_index_rows"]==3
    assert audit["rejected_index_rows"]==1
    assert audit["posted_date_earlier_than_failure_date"]==1
    assert validate(out,audit)
    with gzip.open(out,"rt",encoding="utf-8",newline="") as f:
        entries=list(csv.DictReader(f))
    assert len(entries)==3
    assert len(set(x["source_observation_key"] for x in entries))==3
    other=build(raw,tmp_path/"repeat.gz",tmp_path/"m2.json",snapshot="2026-10-23",minimum_rows=3)
    assert audit["normalized_sha256"]==other["normalized_sha256"]

    db=tmp_path/"index.sqlite"
    indexed=index(out,manifest,db)
    assert indexed["indexed_publisher_investigation_listings"]==3
    assert indexed["distinct_operator_ids"]==1
    assert indexed["posted_before_failure_anomalies"]==1
    assert indexed["app_deployed"]==0
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM investigation_catalog WHERE operator_id='1234'").fetchone()[0]==2
        assert conn.execute("SELECT COUNT(*) FROM investigation_catalog WHERE site_link_status='candidate_only_not_matched'").fetchone()[0]==3

def test_fail_closed_on_headings_dates_tamper_or_untrusted_detail(tmp_path):
    assert agency_date("Sept 9/2015")=="2015-09-09"
    assert agency_date("Sep 25, 2022")=="2022-09-25"
    assert agency_date("April 19, 2017")=="2017-04-19"
    assert agency_date("not a date")==""
    with pytest.raises(ValueError,match="headings"):
        extract_index(FIXTURE.replace("Apparent Cause","Something Else").encode(),"2026-10-23",min_rows=2)
    raw=tmp_path/"catalog.html"
    raw.write_text(FIXTURE)
    output=tmp_path/"normalized.gz"
    manifest=tmp_path/"manifest.json"
    report=build(raw,output,manifest,snapshot="2026-10-23",minimum_rows=3)
    output.write_bytes(output.read_bytes()+b"tamper")
    with pytest.raises(ValueError,match="SHA"):
        validate(output,report)

def test_refuses_unverified_minimum_count():
    with pytest.raises(ValueError,match="unexpectedly small"):
        extract_index(FIXTURE.encode(),"2026-10-23",min_rows=4)
