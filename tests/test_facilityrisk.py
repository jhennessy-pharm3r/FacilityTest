"""Deterministic offline tests: no external source is represented as live verified."""
from __future__ import annotations
import csv
import json
import os
from pathlib import Path
import sqlite3
import pytest
from fastapi.testclient import TestClient

from facilityrisk.app import app
from facilityrisk.db import connect, initialize, quality_report, one
from facilityrisk.ingest import ingest_workbook, ORIGIN
from facilityrisk.match import preview_match, haversine_km
from facilityrisk.intelligence import review_location
from facilityrisk.connectors import (fetch_usgs, fetch_aqueduct, fetch_echo,
                                     ingest_noaa_csv, SourceAccessError)


@pytest.fixture
def database(tmp_path,monkeypatch):
    path=tmp_path/'facility.sqlite'
    monkeypatch.setenv('FACILITY_RISK_DB',str(path))
    with connect(path) as c:
        initialize(c)
        c.execute('''INSERT INTO facilities(id,name,company,address,country,fei,latitude,longitude,
                   origin,last_imported) VALUES(?,?,?,?,?,?,?,?,?,?)''',
                  ('site-one','Demonstration Site','Example Therapeutics','10 Test Road, Anywhere',
                   'United States','123456789',40.0,-75.0,'Test fixture','2026-10-21'))
        c.execute('''INSERT INTO facilities(id,name,company,address,country,fei,latitude,longitude,
                   origin,last_imported) VALUES(?,?,?,?,?,?,?,?,?,?)''',
                  ('site-north','Arctic Test Site','Test','Arctic Circle',
                   'Canada','123456780',70.0,0.0,'Test fixture','2026-10-21'))
        c.execute('''INSERT INTO evidence(id,facility_id,source,program,date_raw,record_type,finding,
                   source_url,risk_domain,origin,last_imported) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                  ('ev1','site-one','EPA','ECHO','2024-05-01','Compliance finding',
                   'Demonstration environmental finding','https://www.epa.gov',
                   'Environmental compliance','Test fixture','2026-10-21'))
        c.execute('''INSERT INTO sources(id,name,description,url,origin) VALUES(?,?,?,?,?)''',
                  ('epa','EPA ECHO','Test documentation','https://echo.epa.gov','Test fixture'))
        c.commit()
        review_location(c,'site-one','site_verified','https://example.org/map/site-one',
                        'QA reviewer','Building point independently checked')
        review_location(c,'site-north','site_verified','https://example.org/map/site-north',
                        'QA reviewer','Building point independently checked')
    return path


def test_api_routes_and_pagination(database):
    with TestClient(app) as client:
        assert client.get('/').status_code == 200
        assert client.get('/assets/app.js').status_code == 200
        h=client.get('/api/health').json()
        assert h['status']=='ok' and h['version']=='0.6.0'
        summary=client.get('/api/overview').json()
        assert summary['stats']['facilities']==2
        assert summary['stats']['evidence']==1
        page=client.get('/api/facilities?limit=1').json()
        assert len(page['items'])==1 and page['total']==2
        assert client.get('/api/facilities?offset=1&limit=1').json()['total']==2
        assert client.get('/api/facilities?limit=501').status_code==422
        assert client.get('/api/facilities/nope').status_code==404
        assert client.get('/api/facilities/site-one').json()['facility']['fei']=='123456789'
        ev=client.get('/api/evidence?search=Demonstration&limit=1').json()
        assert ev['total']==1 and ev['items'][0]['facility_name']=='Demonstration Site'
        assert client.get('/api/evidence?source=FDA').json()['total']==0
        assert client.get('/api/facilities/site-one/evidence').json()['total']==1
        assert client.get('/api/facilities/nope/evidence').status_code==404
        assert client.get('/api/source-fields').json()['total']==0
        assert client.get('/api/sources').json()['total']==1
        assert client.get('/api/quality').json()['integrity_failures']==[]
        assert not client.get('/api/match-preview?fei=123456789').json()['matches'][0]['auto_link_allowed']


def test_match_requires_verified_identifier():
    sites=[dict(id='a',name='Example Site',address='10 Test Road',fei='111111')]
    a=preview_match(sites,fei='111111')
    assert not a[0]['auto_link_allowed'] and a[0]['score']==1.0
    sites[0]['fei_verified']=True
    assert preview_match(sites,fei='111111')[0]['auto_link_allowed']
    b=preview_match(sites,name='Example Site',address='10 Test Road',fei='222222')
    assert b and b[0]['status']=='candidate_review' and not b[0]['auto_link_allowed']
    assert abs(haversine_km(40,-75,40,-75))<0.01


class FakeResponse:
    def __init__(self,payload,url):self.payload=payload;self.url=url
    def raise_for_status(self):return None
    def json(self):return self.payload


class FakeSession:
    def __init__(self,payload):self.payload=payload;self.calls=[]
    def get(self,url,**kwargs):
        self.calls.append((url,kwargs))
        return FakeResponse(self.payload,url+'?test=1')


def test_usgs_ingest_preserves_proximity_caution(database):
    payload={'features':[
        {'id':'near','properties':{'title':'M 4.5 event near test location','mag':4.5,'time':1728000000000,
                                 'url':'https://earthquake.usgs.gov/earthquakes/eventpage/near'},
         'geometry':{'coordinates':[-75.2,40.1,12.0]}},
        {'id':'far','properties':{'title':'Distant event','mag':6.0,'time':1728000000000},
         'geometry':{'coordinates':[85.0,40.1,10.0]}}]}
    with connect(database) as c:
        summary=fetch_usgs(c,'site-one','2024-01-01','2024-12-31',150,4,session=FakeSession(payload))
        assert summary['events_within_radius']==1
        e=one(c,"SELECT * FROM evidence WHERE source='USGS (live)'")
        assert 'not an insured-site impact' in e['evidence_scope']
        assert e['availability_date'] is None and e['spatial_distance_km']>0
        assert c.execute('SELECT COUNT(*) FROM raw_snapshots').fetchone()[0]==1
        assert fetch_usgs(c,'site-one','2024-01-01','2024-12-31',150,4,session=FakeSession(payload))['events_within_radius']==1
        assert c.execute("SELECT COUNT(*) FROM evidence WHERE source='USGS (live)'").fetchone()[0]==1
        with pytest.raises(ValueError):fetch_usgs(c,'site-one','2024-01-01','2024-12-31',500,4,session=FakeSession(payload))


def test_aqueduct_and_echo_raw_capture(database):
    water={'features':[{'attributes':{'bws_raw':0.68,'bws_score':4.25,'bws_cat':4,'aqid':1501}}]}
    with connect(database) as c:
        result=fetch_aqueduct(c,'site-one',session=FakeSession(water))
        assert result['basin_records']==1
        record=one(c,"SELECT * FROM evidence WHERE source='WRI Aqueduct (live)'")
        assert 'Extremely high' in record['finding']
        assert record['availability_date'] is None
        result=fetch_echo(c,'site-one','110070123456',session=FakeSession({'Results':{'Message':'Success'}}))
        assert result['normalized_risk_records']==0
        assert c.execute('SELECT COUNT(*) FROM raw_snapshots').fetchone()[0]==2
        assert c.execute("SELECT COUNT(*) FROM evidence WHERE source='EPA ECHO DFR'").fetchone()[0]==0
        with pytest.raises(ValueError):fetch_echo(c,'site-one','123456789',session=FakeSession({}))


def test_noaa_nearby_not_site_loss_and_high_latitude(database,tmp_path):
    p=tmp_path/'storm_details.csv'
    with p.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,['EVENT_ID','EVENT_TYPE','BEGIN_LAT','BEGIN_LON','BEGIN_DATE_TIME','EVENT_NARRATIVE'])
        w.writeheader()
        w.writerow(dict(EVENT_ID='100',EVENT_TYPE='Hail',BEGIN_LAT='40.1',BEGIN_LON='-75.1',BEGIN_DATE_TIME='2024-03-12',EVENT_NARRATIVE='Area hail report'))
        w.writerow(dict(EVENT_ID='200',EVENT_TYPE='Snow',BEGIN_LAT='70.0',BEGIN_LON='0.9',BEGIN_DATE_TIME='2024-03-12',EVENT_NARRATIVE='Nearby at high latitude'))
        w.writerow(dict(EVENT_ID='300',EVENT_TYPE='Flood',BEGIN_LAT='',BEGIN_LON='',BEGIN_DATE_TIME='2024-03-12'))
        w.writerow(dict(EVENT_ID='400',EVENT_TYPE='Tornado',BEGIN_LAT='-30',BEGIN_LON='115',BEGIN_DATE_TIME='2024-03-12'))
    with connect(database) as c:
        stats=ingest_noaa_csv(c,p,radius_km=40)
        assert stats['rows_seen']==4 and stats['rows_without_coordinates']==1
        assert stats['records_near_site']==2
        assert c.execute("SELECT COUNT(*) FROM evidence WHERE source='NOAA (CSV)'").fetchone()[0]==0
        rows=c.execute("SELECT * FROM external_event_candidates WHERE source_key='noaa'").fetchall()
        assert len(rows)==2 and all(r['status']=='pending' for r in rows)
        assert stats['new_candidates']==2
        assert ingest_noaa_csv(c,p,radius_km=40)['new_candidates']==0


def test_import_replaces_workbook_evidence_without_removing_live(tmp_path):
    workbook=Path(os.environ.get('FACILITY_RISK_WORKBOOK','/mnt/data/Facility Risk Data Exploration.xlsx'))
    if not workbook.exists(): pytest.skip('Analyst workbook intentionally not committed to repository')
    with connect(tmp_path/'ingest.sqlite') as c:
        initialize(c)
        first=ingest_workbook(c,workbook)
        q=quality_report(c)
        assert first['facilities']==12 and first['evidence']==990
        assert q['evidence']==990 and q['public_references']==31
        assert q['sec_findings']==19 and q['sources']==10
        assert q['geo_matched']==11 and q['unmatched_sec_findings']==11
        assert q['evidence_with_verified_publication_date']==0
        assert q['integrity_failures']==[]
        c.execute('''INSERT INTO evidence(id,facility_id,source,risk_domain,origin,last_imported)
                     VALUES('removed-analyst-record','site-pfizer-rocky-mount','EPA','Environmental compliance',?,?)''',
                  (ORIGIN,'2026-10-21'))
        c.execute('''INSERT INTO evidence(id,facility_id,source,risk_domain,origin,last_imported)
                     VALUES('live-pipeline-record','site-pfizer-rocky-mount','USGS (live)','Natural hazards',?,?)''',
                  ('USGS API fixture','2026-10-21'))
        c.commit()
        second=ingest_workbook(c,workbook)
        q=quality_report(c)
        assert q['evidence']==991  # original 990 plus separately ingested adapter record
        assert one(c,"SELECT id FROM evidence WHERE id='removed-analyst-record'") is None
        assert one(c,"SELECT id FROM evidence WHERE id='live-pipeline-record'") is not None
        assert second['evidence']==990

def test_moved_site_blocks_all_geographic_connectors(database,tmp_path):
    with connect(database) as c:
        c.execute("UPDATE facilities SET latitude=41 WHERE id='site-one'")
        c.commit()
        with pytest.raises(ValueError,match='reviewed current'):
            fetch_usgs(c,'site-one','2024-01-01','2024-12-31',session=FakeSession({'features':[]}))
        with pytest.raises(ValueError,match='reviewed current'):
            fetch_aqueduct(c,'site-one',session=FakeSession({'features':[]}))
        p=tmp_path/'empty-noaa.csv'
        p.write_text('EVENT_ID,EVENT_TYPE,BEGIN_LAT,BEGIN_LON\n1,Wind,41,-75\n')
        # The other, independently reviewed Arctic site is still eligible.
        out=ingest_noaa_csv(c,p)
        assert out['records_near_site']==0
        assert c.execute("SELECT COUNT(*) FROM external_event_candidates WHERE facility_id='site-one'").fetchone()[0]==0
