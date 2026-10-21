"""Research is explicit, synchronous, permissioned, and evidence-gated."""
import pytest
from fastapi.testclient import TestClient

from facilityrisk.app import app
from facilityrisk.db import connect,initialize
from facilityrisk.intelligence import review_location
from facilityrisk.research import (checklist,start_research,research_history,
                                   run_source,SourceNotEligible)

@pytest.fixture
def conn(tmp_path,monkeypatch):
    p=tmp_path/'research.sqlite'
    monkeypatch.setenv('FACILITY_RISK_DB',str(p))
    monkeypatch.delenv('FACILITY_RISK_ENABLE_SOURCE_REQUESTS',raising=False)
    monkeypatch.delenv('FACILITY_RISK_ENABLE_WRITES',raising=False)
    c=connect(p);initialize(c)
    c.execute("""INSERT INTO facilities
       (id,name,company,country,fei,latitude,longitude,origin,last_imported)
       VALUES(?,?,?,?,?,?,?,?,?)""",
       ('site-a','Sample Manufacturing','Test Co','United States',
        '123456789',40.1,-75.1,'fixture','2026-10-21'))
    c.commit()
    yield c
    c.close()

def test_plan_created_without_making_any_external_requests(conn):
    plan=checklist(conn,'site-a')
    assert plan['jurisdiction']=='US'
    states={x['source_key']:x['state'] for x in plan['checks']}
    assert states['fema_flood']=='not_eligible'
    assert states['wri_water']=='not_eligible'
    assert states['epa_echo']=='not_eligible'
    out=start_research(conn,'site-a','QA user')
    assert out['status']=='planned'
    assert out['background_work_scheduled'] is False
    assert len(out['plan']['checks'])>=10
    history=research_history(conn,'site-a')
    assert history['plans'][0]['id']==out['research_run_id']
    assert history['attempts']==[]
    assert conn.execute("SELECT COUNT(*) FROM raw_snapshots").fetchone()[0]==0
    with pytest.raises(ValueError,match='Unknown facility'):
        checklist(conn,'not-here')

def test_live_source_queries_require_two_independent_gates(conn,monkeypatch):
    with pytest.raises(ValueError,match='disabled'):
        run_source(conn,'site-a','fema_flood','QA user')
    monkeypatch.setenv('FACILITY_RISK_ENABLE_SOURCE_REQUESTS','1')
    with pytest.raises(SourceNotEligible,match='Source not eligible'):
        run_source(conn,'site-a','fema_flood','QA user')
    review_location(conn,'site-a','site_verified','https://example.org/property-map',
                    'QA user','Reviewed property coordinates')
    mocked=[]
    def fake_fema(database,facility_id):
        mocked.append(facility_id)
        return {'status':'not_mapped','warning':'No polygon does not establish low risk'}
    monkeypatch.setattr('facilityrisk.advanced_sources.fetch_fema',fake_fema)
    out=run_source(conn,'site-a','fema_flood','QA user')
    assert mocked==['site-a']
    assert out['status']=='ingested'
    assert out['result']['status']=='not_mapped'
    assert len(research_history(conn,'site-a')['attempts'])==1
    assert conn.execute("SELECT COUNT(*) FROM audit_events WHERE action='research_source_attempt'").fetchone()[0]==1
    assert conn.execute('SELECT COUNT(*) FROM evidence').fetchone()[0]==0

def test_fema_screening_stops_when_reviewed_coordinates_change(conn,monkeypatch):
    monkeypatch.setenv('FACILITY_RISK_ENABLE_SOURCE_REQUESTS','1')
    review_location(conn,'site-a','site_verified','https://example.org/point',
                    'Reviewer','Reviewed current building')
    conn.execute("UPDATE facilities SET latitude=41.0 WHERE id='site-a'")
    conn.commit()
    with pytest.raises(SourceNotEligible,match='property point'):
        run_source(conn,'site-a','fema_flood','Analyst')

def test_research_private_api_write_guard(conn,monkeypatch):
    with TestClient(app) as client:
        result=client.get('/api/facilities/site-a/research')
        assert result.status_code==200
        assert result.json()['current_checklist']['jurisdiction']=='US'
        assert client.post('/api/facilities/site-a/research').status_code==403
        monkeypatch.setenv('FACILITY_RISK_ENABLE_WRITES','1')
        created=client.post('/api/facilities/site-a/research')
        assert created.status_code==200,created.text
        assert created.json()['background_work_scheduled'] is False
        no_external=client.post('/api/facilities/site-a/research/run-source',
                   json={'source':'fema_flood'})
        assert no_external.status_code==422
        not_found=client.get('/api/facilities/unknown/research')
        assert not_found.status_code==404
