"""Offline, deterministic test gates for identity, causality and security."""
import csv
import json
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from facilityrisk.db import connect,initialize,one
from facilityrisk.app import app
from facilityrisk.intelligence import (register_frs_candidates,decide_candidate,
    review_location,assess_fema_payload,get_intelligence,intelligence_quality,verify_fei)
from facilityrisk.advanced_sources import (records_from_frs,fetch_fema,ingest_fda_inspections_csv,
    source_probe,fetch_verified_echo)
from facilityrisk.case_studies import seed_cases
from facilityrisk.security import validate_private_bind

@pytest.fixture
def db(tmp_path,monkeypatch):
    monkeypatch.setenv('FACILITY_RISK_DB',str(tmp_path/'test.sqlite'))
    with connect() as c:
        initialize(c)
        for fid,name,fei,lat,lon in [
            ('site-baxter-north-cove','Baxter North Cove','1025114',35.834,-82.002),
            ('site-pfizer-rocky-mount','Pfizer Rocky Mount','1021343',36.034,-77.763),
            ('site-amgen-juncos','Amgen Juncos','1000110364',18.236,-65.904)]:
            c.execute('INSERT INTO facilities(id,name,fei,latitude,longitude,country,origin,last_imported) VALUES(?,?,?,?,?,?,?,?)',
                      (fid,name,fei,lat,lon,'United States','fixture','2026-10-21'))
        c.commit()
        yield c


def test_candidate_separate_from_verified_link(db):
    assert register_frs_candidates(db,'site-baxter-north-cove',[
        {'registry_id':'110000000001','name':'BAXTER HEALTHCARE','address':'Marion NC',
         'latitude':35.835,'longitude':-82.003}], 'https://www.epa.gov/frs/frs-api')==1
    q=intelligence_quality(db)
    assert q['frs_candidates_pending']==1 and q['verified_frs_links']==0
    site=get_intelligence(db,'site-baxter-north-cove')
    ident=site['candidates'][0]['id']
    with pytest.raises(ValueError,match='Reviewer'):
        decide_candidate(db,ident,'accepted','analyst','','')
    with pytest.raises(ValueError,match='verified FRS'):
        fetch_verified_echo(db,'site-baxter-north-cove')
    out=decide_candidate(db,ident,'accepted','QA Analyst','https://www.epa.gov/frs/frs-api',
                         'Verified address and registry source manually')
    assert out['decision']=='accepted'
    assert intelligence_quality(db)['verified_frs_links']==1
    assert get_intelligence(db,'site-baxter-north-cove')['identifiers'][-1]['status'] in {'verified','observed'}
    assert db.execute("SELECT COUNT(*) FROM audit_events WHERE action='candidate_accepted'").fetchone()[0]==1


def test_frs_schema_parses_verified_api_fields_and_rejects_bad_schema():
    response={'Results':{'Facilities':[{'RegistryId':'110004455667','FacilityName':'Baxter',
        'LocationAddress':'65 Pitts Station Rd','CityName':'Marion','StateAbbr':'NC',
        'Latitude83':'35.83','Longitude83':'-82.00'}]}}
    matches=records_from_frs(response)
    assert len(matches)==1 and matches[0]['registry_id']=='110004455667'
    assert matches[0]['latitude']==35.83
    with pytest.raises(ValueError,match='schema'):
        records_from_frs({'unexpected':'changed upstream schema'})


def test_solely_nearby_and_unverified_cannot_trigger_fema(db):
    with pytest.raises(ValueError,match='not been manually verified'):
        fetch_fema(db,'site-baxter-north-cove')
    with pytest.raises(ValueError,match='HTTPS'):
        review_location(db,'site-baxter-north-cove','site_verified','file:///data/report','staff')
    review_location(db,'site-baxter-north-cove','site_verified','https://www.baxter.com/site',
                    'staff','Geocoded building footprint')
    class FakeResponse:
        status_code=200
        url='https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query?f=json'
        def raise_for_status(self):pass
        def json(self):return {'features':[{'attributes':{'FLD_ZONE':'AE','SFHA_TF':'T'}}]}
    class FakeSession:
        def get(self,base,**kwargs):return FakeResponse()
    outcome=fetch_fema(db,'site-baxter-north-cove',session=FakeSession())
    assert outcome['status']=='mapped_sfha' and outcome['zone']=='AE'
    assert one(db,"SELECT source FROM hazard_assessments WHERE facility_id='site-baxter-north-cove'")['source']=='FEMA NFHL'
    assert db.execute('SELECT COUNT(*) FROM raw_snapshots').fetchone()[0]==1


def test_unmapped_flood_is_not_low_risk():
    assert assess_fema_payload({'features':[]})[0]=='not_mapped'
    assert assess_fema_payload({'features':[{'attributes':{'FLD_ZONE':'X','SFHA_TF':'F'}}]})[0]=='mapped_outside_sfha'
    with pytest.raises(ValueError):assess_fema_payload({'error':{'message':'Service failed'}})
    with pytest.raises(ValueError):assess_fema_payload({'features':[{'attributes':{'FLD_ZONE':'X'}}]})


def test_fda_csv_import_remains_fei_scoped(db,tmp_path):
    path=tmp_path/'fda.csv'
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['FEI Number','Inspection End Date','Classification','Firm Name'])
        writer.writeheader()
        writer.writerow({'FEI Number':'1025114','Inspection End Date':'2023-10-01','Classification':'VAI','Firm Name':'Baxter'})
        writer.writerow({'FEI Number':'9999999','Inspection End Date':'2024-01-01','Classification':'OAI','Firm Name':'Other'})
    result=ingest_fda_inspections_csv(db,path)
    assert result['linked']==0 and result['identity_pending']==1
    assert result['unmatched_or_incomplete']==1
    assert db.execute("SELECT COUNT(*) FROM evidence WHERE source='FDA inspections (CSV)'").fetchone()[0]==0
    assert db.execute("SELECT status FROM regulatory_observations").fetchone()[0]=='identity_pending'
    verify_fei(db,'site-baxter-north-cove','FDA reviewer',
               'https://www.fda.gov/','Reviewed official FEI and physical establishment')
    second=ingest_fda_inspections_csv(db,path)
    assert second['linked']==1
    assert db.execute("SELECT COUNT(*) FROM evidence WHERE source='FDA inspections (CSV)'").fetchone()[0]==1


def test_case_study_seed_has_no_pre_event_prediction(db):
    out=seed_cases(db)
    assert out['cases_seeded']==3 and out['milestones']==12
    assert intelligence_quality(db)['profiles']==3
    incidents=db.execute('SELECT pre_event_evidence_status FROM historical_events').fetchall()
    assert all('No' in row[0] or 'not establish' in row[0] for row in incidents)
    assert db.execute("SELECT COUNT(*) FROM event_milestones WHERE timing='pre_event'").fetchone()[0]==0


def test_security_requires_password_outside_loopback(monkeypatch):
    monkeypatch.delenv('FACILITY_RISK_AUTH_TOKEN',raising=False)
    with pytest.raises(RuntimeError):validate_private_bind('0.0.0.0')
    monkeypatch.setenv('FACILITY_RISK_AUTH_TOKEN','long-local-test-token-that-is-not-for-production')
    assert validate_private_bind('0.0.0.0') is None
    with TestClient(app) as client:
        assert client.get('/api/health').status_code==200
        assert client.get('/').status_code==401
        assert client.get('/api/overview').status_code==401
        assert client.get('/api/overview',headers={'Authorization':'Bearer long-local-test-token-that-is-not-for-production'}).status_code==200
        assert client.post('/api/facilities/site-baxter-north-cove/profile',json={'sections':{}}).status_code==401
    monkeypatch.delenv('FACILITY_RISK_AUTH_TOKEN',raising=False)


def test_source_probe_not_tested_is_not_reported_live(db):
    class FakeSession:
        def get(self,url,**kwargs):
            raise TimeoutError('blocked for offline QA')
    results=source_probe(db,FakeSession())
    assert any(x['state']=='failed' for x in results)
    assert any(x['state']=='requires_file' for x in results)
    assert db.execute("SELECT COUNT(*) FROM source_health WHERE state='reachable'").fetchone()[0]==0


def test_observed_fei_needs_source_corrob_to_auto_link(db):
    with TestClient(app) as client:
        r=client.get('/api/match-preview?fei=1025114').json()
        assert r['matches'][0]['score']==1 and r['matches'][0]['status']=='candidate_review'
        assert r['matches'][0]['auto_link_allowed'] is False
    with pytest.raises(ValueError,match='reviewer'):
        verify_fei(db,'site-baxter-north-cove','','','')
    v=verify_fei(db,'site-baxter-north-cove','Site Analyst','https://www.fda.gov/','Reviewed physical manufacturing establishment')
    assert v['status']=='verified'
    with TestClient(app) as client:
        assert client.get('/api/match-preview?fei=1025114').json()['matches'][0]['auto_link_allowed'] is True
    assert db.execute("SELECT COUNT(*) FROM audit_events WHERE action='fei_verified'").fetchone()[0]==1


def test_required_auth_fails_closed_even_localhost_without_token(monkeypatch):
    monkeypatch.delenv('FACILITY_RISK_AUTH_TOKEN',raising=False)
    monkeypatch.setenv('FACILITY_RISK_REQUIRE_AUTH','1')
    with TestClient(app) as client:
        assert client.get('/api/health').status_code==200
        assert client.get('/api/overview').status_code==401
        assert client.get('/').status_code==401
    monkeypatch.delenv('FACILITY_RISK_REQUIRE_AUTH',raising=False)


def test_fema_official_alternate_does_not_bypass_location_gate(db):
    class FakeResponse:
        status_code=200
        url='https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer/28/query?f=json'
        def raise_for_status(self):pass
        def json(self):return {'features':[{'attributes':{'FLD_ZONE':'X','SFHA_TF':'F'}}]}
    class AlternateSession:
        def get(self,base,**kwargs):
            if '/arcgis/' in base: raise OSError('Primary route unavailable')
            return FakeResponse()
    # Original site is unreviewed, so even a viable fallback must be blocked.
    with pytest.raises(ValueError,match='manually verified'):
        fetch_fema(db,'site-baxter-north-cove',session=AlternateSession())
    review_location(db,'site-baxter-north-cove','site_verified','https://www.fema.gov/','QA reviewer','Reviewed building point')
    # json_get accepts requests exceptions; synthetic session raises OSError (not requests.ConnectionError),
    # so use a representative Requests connection exception.
    from requests.exceptions import ConnectionError as RequestsConnectionError
    class RequestsSession(AlternateSession):
        def get(self,base,**kwargs):
            if '/arcgis/' in base:raise RequestsConnectionError('Primary unavailable')
            return FakeResponse()
    out=fetch_fema(db,'site-baxter-north-cove',session=RequestsSession())
    assert out['status']=='mapped_outside_sfha'
    assert '/gis/nfhl/' in out['request_url']

def test_changed_coordinates_revoke_old_property_review(db,tmp_path):
    from facilityrisk.db import quality_report
    from facilityrisk.source_extensions import import_geo_csv
    fid='site-baxter-north-cove'
    review_location(db,fid,'site_verified','https://www.fema.gov/','Site reviewer',
                    'Original property point inspected with public record')
    before=get_intelligence(db,fid)
    assert before['location']['precision']=='site_verified'
    assert before['location']['review_valid_for_current_coordinates'] is True
    assert intelligence_quality(db)['verified_site_locations']==1
    db.execute('UPDATE facilities SET latitude=?,longitude=? WHERE id=?',(35.95,-82.02,fid))
    db.commit()
    after=get_intelligence(db,fid)
    assert after['location']['precision']=='review_stale'
    assert after['location']['original_review_precision']=='site_verified'
    assert after['location']['review_valid_for_current_coordinates'] is False
    assert intelligence_quality(db)['verified_site_locations']==0
    assert quality_report(db)['stale_or_legacy_coordinate_reviews']==1
    with pytest.raises(ValueError,match='current point'):
        fetch_fema(db,fid)
    csv_file=tmp_path/'incident.csv'
    csv_file.write_text('id,latitude,longitude,date_start,description\n'
                        'nearby,35.95,-82.02,2025-01-01,Nearby incident\n',encoding='utf-8')
    with pytest.raises(ValueError,match='No independently reviewed'):
        import_geo_csv(db,csv_file,'phmsa')
    review_location(db,fid,'site_verified','https://www.fema.gov/','Site reviewer',
                    'Reviewed updated building site point against authoritative documentation')
    assert intelligence_quality(db)['verified_site_locations']==1
    assert get_intelligence(db,fid)['location']['precision']=='site_verified'
    result=import_geo_csv(db,csv_file,'phmsa')
    assert result['new_candidates']==1
    assert db.execute('SELECT COUNT(*) FROM evidence').fetchone()[0]==0


def test_property_review_rejects_invalid_coordinate_and_clears_downgrade(db):
    fid='site-baxter-north-cove'
    db.execute('UPDATE facilities SET latitude=999 WHERE id=?',(fid,))
    db.commit()
    with pytest.raises(ValueError,match='outside valid geographic bounds'):
        review_location(db,fid,'site_verified','https://example.org/location',
                        'QA inspector','Checked property point')
    assert db.execute('SELECT COUNT(*) FROM location_reviews').fetchone()[0]==0
    db.execute('UPDATE facilities SET latitude=35.834 WHERE id=?',(fid,))
    db.commit()
    review_location(db,fid,'site_verified','https://example.org/location',
                    'QA inspector','Reviewed building')
    assert intelligence_quality(db)['verified_site_locations']==1
    review_location(db,fid,'approximate','','QA inspector',
                    'Previous source withdrawn, precision downgraded')
    point=db.execute('SELECT * FROM location_reviews WHERE facility_id=?',(fid,)).fetchone()
    assert point['reviewed_latitude'] is None
    assert point['reviewed_longitude'] is None
    assert intelligence_quality(db)['verified_site_locations']==0


def test_preexisting_coordinate_review_is_untrusted_until_rereview(db):
    from facilityrisk.db import quality_report
    fid='site-baxter-north-cove'
    db.execute('DROP TABLE location_reviews')
    db.execute("""CREATE TABLE location_reviews (
      facility_id TEXT PRIMARY KEY REFERENCES facilities(id) ON DELETE CASCADE,
      precision TEXT NOT NULL CHECK(precision IN ('city','approximate','site_verified','property_polygon')),
      method TEXT,evidence_url TEXT,reviewer TEXT,verified_at TEXT,note TEXT)""")
    db.execute("""INSERT INTO location_reviews
     VALUES (?,'site_verified','manual','https://example.org/old','Old reviewer',
             '2026-09-01','This predates coordinate-snapshot migration')""",(fid,))
    db.commit()
    # Runs a migration against a real legacy table; no review point is invented.
    initialize(db)
    record=db.execute('SELECT reviewed_latitude,reviewed_longitude FROM location_reviews WHERE facility_id=?',(fid,)).fetchone()
    assert record['reviewed_latitude'] is None and record['reviewed_longitude'] is None
    assert intelligence_quality(db)['verified_site_locations']==0
    assert get_intelligence(db,fid)['location']['precision']=='review_stale'
    assert quality_report(db)['stale_or_legacy_coordinate_reviews']==1
    with pytest.raises(ValueError,match='current point'):
        fetch_fema(db,fid)
    review_location(db,fid,'site_verified','https://example.org/current-property',
                    'New reviewer','Revalidated precise coordinate and property record')
    assert intelligence_quality(db)['verified_site_locations']==1
