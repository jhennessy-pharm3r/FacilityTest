"""Regression tests: non-FDA registry discovery and zero-inference site intake."""
from __future__ import annotations

import csv
import json

import pytest
from fastapi.testclient import TestClient

from facilityrisk.app import app
from facilityrisk.db import connect,initialize
from facilityrisk.intelligence import decide_candidate
from facilityrisk.site_workspace import (SOURCES,intake_site,import_official_registry_csv,
                                        search_external_registry,track_external_registry_site,
                                        stage_identity_candidate)

@pytest.fixture
def db(tmp_path,monkeypatch):
    location=tmp_path/'workspace.sqlite'
    monkeypatch.setenv('FACILITY_RISK_DB',str(location))
    conn=connect(location)
    initialize(conn)
    yield conn
    conn.close()


def _registry_file(tmp_path,rows):
    filename=tmp_path/'official_fixture.csv'
    with filename.open('w',newline='',encoding='utf-8') as fh:
        writer=csv.DictWriter(fh,fieldnames=['NPRI ID','Site','Operator','Street','City','Province','Country'])
        writer.writeheader()
        writer.writerows(rows)
    return filename


def _import(db,tmp_path):
    file=_registry_file(tmp_path,[
       {'NPRI ID':'CA-0042','Site':'Northern Medical Device Plant',
        'Operator':'Example Canada Medical Corp','Street':'111 Plant Road',
        'City':'Ottawa','Province':'ON','Country':'Canada'},
       {'NPRI ID':'CA-0043','Site':'East Pharmaceutical Plant',
        'Operator':'Example Pharma Inc','Street':'220 Factory Street',
        'City':'Quebec','Province':'QC','Country':'Canada'}])
    return import_official_registry_csv(db,file,'CA_NPRI','https://open.canada.ca/',
                id_column='NPRI ID',name_column='Site',company_column='Operator',
                address_column='Street',city_column='City',state_column='Province',
                country_column='Country')


def test_create_any_manual_site_without_auto_merging_or_risk(db):
    a=intake_site(db,{'name':'Galway Pharmaceutical Building A','country':'Ireland',
                      'city':'Galway','company':'Sample Holdings'},'researcher')
    b=intake_site(db,{'name':'Galway Pharmaceutical Building A','country':'Ireland',
                      'city':'Galway','company':'Sample Holdings'},'researcher')
    assert a['facility_id']!=b['facility_id']
    row=db.execute('SELECT * FROM facilities WHERE id=?',(a['facility_id'],)).fetchone()
    assert row['latitude'] is None and row['longitude'] is None and row['fei'] is None
    assert row['site_case']=='Research requested'
    assert db.execute("SELECT COUNT(*) FROM identity_links WHERE facility_id=?",(a['facility_id'],)).fetchone()[0]==0
    assert db.execute("SELECT COUNT(*) FROM audit_events WHERE action='manual_facility_intake'").fetchone()[0]==2
    with pytest.raises(ValueError,match='HTTPS'):
        intake_site(db,{'name':'Test Facility','source_url':'http://untrusted.example'},'analyst')
    with pytest.raises(ValueError,match='three'):
        intake_site(db,{'name':'a'},'analyst')


def test_source_import_search_tracking_and_candidate_review(db,tmp_path):
    res=_import(db,tmp_path)
    assert res['source_entities']==2
    assert res['source_sha256'] and res['invalid_rows']==0
    x=search_external_registry(db,query='Pharmaceutical',country='Canada')
    assert x['total']==1
    assert search_external_registry(db,query='%',country='Canada')['total']==0
    first=search_external_registry(db,query='Medical')['items'][0]
    assert first['source_key']=='CA_NPRI'
    assert first['source_identifier']=='CA-0042'
    assert 'Example Canada' in first['company']
    tracked=track_external_registry_site(db,first['id'],'analyst')
    row=db.execute('SELECT * FROM facilities WHERE id=?',(tracked['facility_id'],)).fetchone()
    assert row['latitude'] is None and row['fei'] is None
    identity=db.execute('SELECT * FROM identity_links WHERE facility_id=?',(tracked['facility_id'],)).fetchone()
    assert identity['status']=='observed' and identity['namespace']=='CA_NPRI'
    assert track_external_registry_site(db,first['id'],'analyst')['facility_id']==tracked['facility_id']
    manual=intake_site(db,{'name':'Northern Medical Device Plant','country':'Canada'},'analyst')
    candidate=stage_identity_candidate(db,manual['facility_id'],first['id'],'analyst')
    before=db.execute('SELECT decision FROM match_candidates WHERE id=?',(candidate['candidate_id'],)).fetchone()
    assert before['decision']=='pending'
    decided=decide_candidate(db,candidate['candidate_id'],'accepted','Second reviewer',
             'https://open.canada.ca/','Evidence confirms same legal operator and physical site')
    assert decided['decision']=='accepted'
    link=db.execute('SELECT status FROM identity_links WHERE facility_id=? AND namespace=?',
                    (manual['facility_id'],'CA_NPRI')).fetchone()
    assert link['status']=='verified'
    assert db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]==0
    assert db.execute("SELECT COUNT(*) FROM historical_events").fetchone()[0]==0


def test_bad_source_data_cannot_mutate_registry(db,tmp_path):
    file=_registry_file(tmp_path,[{'NPRI ID':'CA-1','Site':'One','Country':'Canada'},
                                  {'NPRI ID':'CA-1','Site':'Other','Country':'Canada'}])
    with pytest.raises(ValueError,match='Duplicate source identifier'):
        import_official_registry_csv(db,file,'CA_NPRI','https://open.canada.ca/',
                                     id_column='NPRI ID',name_column='Site',
                                     country_column='Country',address_column='')
    assert search_external_registry(db)['total']==0
    with pytest.raises(ValueError,match='Unsupported'):
        import_official_registry_csv(db,file,'BAD_UNKNOWN','https://example.org/',
                                     id_column='NPRI ID',name_column='Site')


def test_site_intake_and_regulator_api_write_gate(db,tmp_path,monkeypatch):
    with TestClient(app) as client:
        assert client.get('/api/external-registry/sources').status_code==200
        assert len(client.get('/api/external-registry/sources').json()['sources'])==len(SOURCES)
        assert client.post('/api/facilities/intake',json={'name':'Research site'}).status_code==403
        monkeypatch.setenv('FACILITY_RISK_ENABLE_WRITES','1')
        response=client.post('/api/facilities/intake',json={
              'name':'Guangzhou Research Example','country':'China','company':'Example Ltd'})
        assert response.status_code==200,response.text
        assert response.json()['status']=='unverified'
        fid=response.json()['facility_id']
        detail=client.get('/api/facilities/'+fid).json()['facility']
        assert detail['fei'] is None and detail['latitude'] is None
        assert client.get('/api/facilities/'+fid+'/event-candidates').json()['total']==0
        assert client.post('/api/facilities/'+fid+'/identity-candidates',
                           json={'external_id':'no-record'}).status_code==422


def test_external_event_api_stays_in_review_queue(db,tmp_path,monkeypatch):
    from facilityrisk.intelligence import review_location
    from facilityrisk.source_extensions import import_geo_csv
    manual=intake_site(db,{'name':'A Site with Verified Point'},'tester')['facility_id']
    db.execute('UPDATE facilities SET latitude=?,longitude=? WHERE id=?',(46.0,-65.0,manual))
    db.commit()
    review_location(db,manual,'site_verified','https://example.org/verified-map',
                    'Map reviewer','Point checked against cadastral map')
    path=tmp_path/'event.csv'
    with path.open('w',newline='',encoding='utf-8') as fh:
        writer=csv.DictWriter(fh,fieldnames=['id','latitude','longitude','date_start','description'])
        writer.writeheader()
        writer.writerow({'id':'E1','latitude':46.01,'longitude':-65.01,
                         'date_start':'2025-01-01','description':'Nearby incident in another business'})
    result=import_geo_csv(db,path,'phmsa',radius_km=10)
    assert result['new_candidates']==1
    with TestClient(app) as client:
        j=client.get('/api/facilities/'+manual+'/event-candidates').json()
        assert j['total']==1 and j['items'][0]['status']=='pending'
        cid=j['items'][0]['id']
        assert client.post('/api/external-events/'+cid+'/review',
                           json={'decision':'reviewed_relevant','evidence_url':'https://example.org',
                                 'reason':'Neighboring response, not facility loss'}).status_code==403
        monkeypatch.setenv('FACILITY_RISK_ENABLE_WRITES','1')
        bad=client.post('/api/external-events/'+cid+'/review',json={
                           'decision':'reviewed_relevant','evidence_url':'http://bad.test',
                           'reason':'Insufficient corroboration'})
        assert bad.status_code==422
        good=client.post('/api/external-events/'+cid+'/review',json={
                           'decision':'rejected','evidence_url':'https://example.org/event-review',
                           'reason':'The event involved a separate industrial property'})
        assert good.status_code==200,good.text
        assert client.get('/api/facilities/'+manual+'/event-candidates?status=rejected').json()['total']==1
    assert db.execute('SELECT COUNT(*) FROM evidence').fetchone()[0]==0
