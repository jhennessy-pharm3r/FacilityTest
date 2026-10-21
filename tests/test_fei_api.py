"""FDA-issued FEI credentials unlock observation only; no automatic validation."""
import json
import pytest
from fastapi.testclient import TestClient

from facilityrisk.app import app
from facilityrisk.db import connect,initialize
from facilityrisk.fei_api import lookup_fei,normalize_response

class Response:
    status_code=200
    def __init__(self,fei='3000123401'):
        self.fei=fei
    def raise_for_status(self):pass
    def json(self):
        return {'STATUSCODE':400,'MESSAGE':'Success','RESULT':{
             'FEINUMBER':int(self.fei),
             'LEGALNAME':'Example Medical Devices LLC',
             'MERGEDFIRMINDICATOR':False,
             'physicaladdress':{'FIRMADDRESS1':'25 Research Avenue',
                'FIRMCITY':'Boston','FIRMSTATE':'MA','FIRMCOUNTRY':'US',
                'VALIDATIONSTATUS':'VALID'}}}

class Session:
    def __init__(self,fei='3000123401'):
        self.calls=[]
        self.fei=fei
    def get(self,url,params=None,headers=None,timeout=None):
        self.calls.append((url,params,headers,timeout))
        assert headers['Authorization-User']=='fixture-user'
        assert headers['Authorization-Key']=='fixture-key'
        assert 'api_key' not in url.lower() and timeout==30
        return Response(self.fei)

@pytest.fixture
def db(tmp_path,monkeypatch):
    dbpath=tmp_path/'fei.sqlite'
    monkeypatch.setenv('FACILITY_RISK_DB',str(dbpath))
    conn=connect(dbpath)
    initialize(conn)
    conn.execute("""INSERT INTO facilities(id,name,company,country,fei,origin,last_imported)
        VALUES ('site-validated-research','Test Research Site','Example Medical','US',
                '3000123401','synthetic-fixture','2026-10-21')""")
    conn.commit()
    initialize(conn)
    yield conn
    conn.close()

def test_lookup_requires_fda_credentials_before_network(db,monkeypatch):
    monkeypatch.delenv('FACILITY_RISK_FEI_AUTH_USER',raising=False)
    monkeypatch.delenv('FACILITY_RISK_FEI_AUTH_KEY',raising=False)
    with pytest.raises(ValueError,match='credentials not configured'):
        lookup_fei(db,'site-validated-research','researcher',Session())
    assert db.execute('SELECT COUNT(*) FROM raw_snapshots').fetchone()[0]==0

def test_source_response_is_not_a_verified_site(db,monkeypatch):
    monkeypatch.setenv('FACILITY_RISK_FEI_AUTH_USER','fixture-user')
    monkeypatch.setenv('FACILITY_RISK_FEI_AUTH_KEY','fixture-key')
    client=Session()
    result=lookup_fei(db,'site-validated-research','FDA test reviewer',client)
    assert result['review_status']=='observed_unverified'
    assert result['fei']=='3000123401'
    assert result['legal_name']=='Example Medical Devices LLC'
    assert result['physical_address']['city']=='Boston'
    assert 'https://' in client.calls[0][0]
    assert db.execute('SELECT COUNT(*) FROM raw_snapshots').fetchone()[0]==1
    observed=db.execute("""SELECT status FROM identity_links
       WHERE facility_id='site-validated-research' AND namespace='FDA_FEI'""").fetchone()
    assert observed['status']=='observed'
    assert db.execute('SELECT COUNT(*) FROM hazard_assessments').fetchone()[0]==0
    assert db.execute('SELECT COUNT(*) FROM historical_events').fetchone()[0]==0
    assert db.execute('SELECT COUNT(*) FROM evidence').fetchone()[0]==0
    snapshot=db.execute('SELECT response_json FROM raw_snapshots').fetchone()[0]
    assert 'fixture-key' not in snapshot and 'fixture-user' not in snapshot
    assert json.loads(snapshot)['review_status']=='observed_unverified'

def test_fei_response_mismatch_rejected_and_not_archived(db,monkeypatch):
    monkeypatch.setenv('FACILITY_RISK_FEI_AUTH_USER','fixture-user')
    monkeypatch.setenv('FACILITY_RISK_FEI_AUTH_KEY','fixture-key')
    with pytest.raises(ValueError,match='differs'):
        lookup_fei(db,'site-validated-research','researcher',Session('3000123402'))
    assert db.execute('SELECT COUNT(*) FROM raw_snapshots').fetchone()[0]==0
    with pytest.raises(ValueError,match='RESULT'):
        normalize_response({'RESULT':None},'3000123401')
    with pytest.raises(ValueError,match='Unknown facility'):
        lookup_fei(db,'no-such-site','researcher',Session())

def test_api_requires_explicit_write_gate_and_credentials(db,monkeypatch):
    monkeypatch.setenv('FACILITY_RISK_FEI_AUTH_USER','fixture-user')
    monkeypatch.setenv('FACILITY_RISK_FEI_AUTH_KEY','fixture-key')
    monkeypatch.delenv('FACILITY_RISK_ENABLE_WRITES',raising=False)
    with TestClient(app) as client:
        assert client.post('/api/facilities/site-validated-research/fei-lookup').status_code==403
        monkeypatch.setenv('FACILITY_RISK_ENABLE_WRITES','1')
        monkeypatch.delenv('FACILITY_RISK_FEI_AUTH_KEY',raising=False)
        assert client.post('/api/facilities/site-validated-research/fei-lookup').status_code==503
