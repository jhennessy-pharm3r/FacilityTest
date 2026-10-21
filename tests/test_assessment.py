"""Assessments must remain useful with missing information, never fabricate risk scores."""
import pytest
from fastapi.testclient import TestClient

from facilityrisk.app import app
from facilityrisk.assessment import build_assessment,render_assessment_html,export_assessment
from facilityrisk.db import connect,initialize
from facilityrisk.intelligence import review_location,verify_fei

@pytest.fixture
def conn(tmp_path,monkeypatch):
    path=tmp_path/'assessment.sqlite'
    monkeypatch.setenv('FACILITY_RISK_DB',str(path))
    c=connect(path)
    initialize(c)
    c.execute("""INSERT INTO facilities
      (id,name,company,address,country,fei,latitude,longitude,origin,last_imported)
      VALUES(?,?,?,?,?,?,?,?,?,?)""",
      ('site-a','Acme <Example> Plant','Acme Medical',
       '14 Street & 2nd','United States','1025114',35.83,-82.01,'fixture','2026-10-21'))
    c.execute("""INSERT INTO evidence
      (id,facility_id,source,date_raw,record_type,finding,source_url,
       risk_domain,origin,last_imported)
      VALUES (?,?,?,?,?,?,?,?,?,?)""",
      ('ev1','site-a','SEC EDGAR','2024-04-01','Operations',
       '<script>alert("x")</script>',
       'https://www.sec.gov/ixviewer/doc','Operational resilience',
       'test','2026-10-21'))
    c.execute("""INSERT INTO regulatory_observations
      (id,facility_id,source,source_id,observed_date,observation,status,
       source_url,source_sha256,retrieved_at)
      VALUES(?,?,?,?,?,?,?,?,?,?)""",
      ('obs1','site-a','FDA inspections','1025114','2024-05-01','OAI',
       'identity_pending','https://www.fda.gov','fixture-hash','2026-10-21'))
    c.commit()
    yield c
    c.close()

def test_report_stays_unranked_even_with_evidence_and_fei(conn):
    report=build_assessment(conn,'site-a')
    assert report['evaluation']=='unranked_insufficient_calibration'
    assert report['risk_score'] is None and report['risk_probability'] is None
    assert report['facility_identity']['site_coordinate_verified'] is False
    assert report['coverage']['regulatory_identity']['status']=='unassessed'
    assert report['coverage']['pre_event_visibility']['status']=='unassessed'
    assert report['evidence_total']==1
    assert len(report['regulatory_observations'])==1
    assert report['coverage']['physical_site']['status']=='unassessed'
    assert report['sections'][0]['assessment']=='Not assessed'
    assert not any('low risk' in str(v).lower() for v in report['coverage'].values())

def test_print_html_escapes_source_findings_and_only_links_https(conn,tmp_path):
    report=build_assessment(conn,'site-a')
    html=render_assessment_html(report)
    assert '&lt;script&gt;' in html and '<script>' not in html
    assert 'Acme &lt;Example&gt; Plant' in html and '14 Street &amp; 2nd' in html
    assert 'No loss probability or premium rating' in html
    assert 'href="https://www.sec.gov/ixviewer/doc"' in html
    report['evidence'][0]['source_url']='javascript:alert(1)'
    assert 'href="javascript:' not in render_assessment_html(report)
    filename=tmp_path/'assessment.html'
    saved=export_assessment(conn,'site-a',filename)
    assert saved['risk_score'] is None and filename.exists()
    assert filename.stat().st_size>1000
    with pytest.raises(ValueError,match='html'):export_assessment(conn,'site-a',tmp_path/'wrong.json')

def test_proof_of_site_identity_increases_coverage_not_a_risk_score(conn):
    review_location(conn,'site-a','site_verified','https://example.org/coordinates',
                    'Review analyst','Independently reviewed property point')
    verify_fei(conn,'site-a','FDA analyst','https://www.fda.gov/',
               'Crosschecked FEI physical address against official data')
    report=build_assessment(conn,'site-a')
    assert report['facility_identity']['site_coordinate_verified'] is True
    assert report['coverage']['physical_site']['status']=='verified'
    assert report['coverage']['regulatory_identity']['status']=='verified'
    assert report['risk_score'] is None
    conn.execute("UPDATE facilities SET latitude=36.1 WHERE id='site-a'")
    conn.commit()
    old=build_assessment(conn,'site-a')
    assert old['coverage']['physical_site']['status']=='unassessed'

def test_assessment_api_is_available_only_on_private_backend(conn):
    with TestClient(app) as client:
        response=client.get('/api/facilities/site-a/assessment')
        assert response.status_code==200,response.text
        assert response.json()['risk_score'] is None
        printed=client.get('/api/facilities/site-a/assessment.html')
        assert printed.status_code==200
        assert 'text/html' in printed.headers['content-type']
        assert '&lt;script&gt;' in printed.text
        assert client.get('/api/facilities/missing/assessment').status_code==404
