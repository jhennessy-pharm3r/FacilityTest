"""Credentialed independent source review cannot be bypassed with a shared token."""
import json
import pytest
from fastapi.testclient import TestClient

from facilityrisk.app import app
from facilityrisk.db import connect,initialize
from facilityrisk.intelligence import register_frs_candidates,get_intelligence
from facilityrisk.approval import create_proposal,decide_approval
from facilityrisk.security import make_password_hash,verify_password,validate_private_bind

@pytest.fixture
def private_db(tmp_path,monkeypatch):
    db=tmp_path/'approval.sqlite'
    monkeypatch.setenv('FACILITY_RISK_DB',str(db))
    monkeypatch.setenv('FACILITY_RISK_DUAL_REVIEW','1')
    monkeypatch.setenv('FACILITY_RISK_ENABLE_WRITES','1')
    monkeypatch.setenv('FACILITY_RISK_AUTH_TOKEN','service-token-should-never-authorize-a-review-123456')
    users={}
    for user,role in [('reviewerA','reviewer'),('approverB','approver'),
                      ('viewerC','viewer'),('adminD','admin')]:
        passwd='Synthetic-test-only-password-'+user
        users[user]={'role':role,'password_hash':make_password_hash(
            passwd,salt=(b'fixed-test-salt-'+user.encode()).ljust(24,b'0'))}
    monkeypatch.setenv('FACILITY_RISK_USERS_JSON',json.dumps(users))
    with connect(db) as conn:
        initialize(conn)
        conn.execute("""INSERT INTO facilities(id,name,company,fei,latitude,longitude,
                        country,origin,last_imported) VALUES(?,?,?,?,?,?,?,?,?)""",
                     ('site-1','Example Facility','Example Co','2000000100',
                      35.6,-78.1,'United States','fixture','2026-10-22'))
        conn.commit()
    return db

def auth(name):
    return name,'Synthetic-test-only-password-'+name

def test_password_verifier_and_private_external_bind_gate(private_db):
    assert verify_password(auth('reviewerA')[1],
          make_password_hash(auth('reviewerA')[1],salt=b'0123456789abcdef'))
    assert not verify_password('incorrect','malformed')
    assert validate_private_bind('0.0.0.0') is None

def test_two_person_location_proposal_does_not_promote_until_independent_approval(private_db):
    with TestClient(app) as client:
        payload={'precision':'site_verified',
                 'evidence_url':'https://example.org/authoritative-property-map',
                 'note':'Confirmed parcel map and actual manufacturing building'}
        assert client.post('/api/facilities/site-1/location-review',
                           json=payload,auth=auth('viewerC')).status_code==403
        assert client.post('/api/facilities/site-1/location-review',
                           json=payload,headers={'Authorization':'Bearer service-token-should-never-authorize-a-review-123456'}).status_code==403
        proposed=client.post('/api/facilities/site-1/location-review',
                             json=payload,auth=auth('reviewerA'))
        assert proposed.status_code==200,proposed.text
        row=proposed.json()
        assert row['promotion_performed'] is False and row['status']=='pending'
        assert client.get('/api/facilities/site-1/intelligence',
                          auth=auth('reviewerA')).json()['location'] is None
        request_id=row['approval_id']
        self_decide=client.post(f'/api/review-approvals/{request_id}/decide',
                    json={'decision':'approve','note':'Checking the original source record'},
                    auth=auth('reviewerA'))
        assert self_decide.status_code==403
        accepted=client.post(f'/api/review-approvals/{request_id}/decide',
                    json={'decision':'approve','note':'Independently compared parcel and operator'},
                    auth=auth('approverB'))
        assert accepted.status_code==200,accepted.text
        assert accepted.json()['promotion_performed']
        result=client.get('/api/facilities/site-1/intelligence',auth=auth('viewerC')).json()
        assert result['location']['review_valid_for_current_coordinates'] is True
        assert result['location']['reviewer']=='reviewerA'
        assert client.post(f'/api/review-approvals/{request_id}/decide',
                    json={'decision':'approve','note':'Attempt repeated promotion'},
                    auth=auth('approverB')).status_code==422
    with connect(private_db) as db:
        assert db.execute("SELECT COUNT(*) FROM review_approvals WHERE status='approved'").fetchone()[0]==1
        assert db.execute("SELECT COUNT(*) FROM audit_events WHERE action='independent_review_approved'").fetchone()[0]==1

def test_site_moved_between_proposal_and_approval_is_invalidated(private_db):
    with TestClient(app) as client:
        r=client.post('/api/facilities/site-1/location-review',
               json={'precision':'site_verified','evidence_url':'https://example.org/original',
                     'note':'Reviewed original factory point'},
               auth=auth('reviewerA'))
        assert r.status_code==200
        with connect(private_db) as db:
            db.execute("UPDATE facilities SET latitude=36.7 WHERE id='site-1'")
            db.commit()
        decision=client.post('/api/review-approvals/'+r.json()['approval_id']+'/decide',
                  json={'decision':'approve','note':'Source verification performed independently'},
                  auth=auth('approverB'))
        assert decision.status_code==200 and decision.json()['status']=='invalidated'
        assert client.get('/api/facilities/site-1/intelligence',auth=auth('viewerC')).json()['location'] is None

def test_fei_and_regulatory_crosswalk_promotions_require_two_distinct_accounts(private_db):
    with TestClient(app) as client:
        f=client.post('/api/facilities/site-1/fei-review',
              json={'evidence_url':'https://www.fda.gov/','note':'Confirmed original FDA establishment mapping'},
              auth=auth('reviewerA'))
        assert f.status_code==200,f.text
        with connect(private_db) as db:
            assert db.execute("""SELECT COUNT(*) FROM identity_links
                     WHERE namespace='FDA_FEI' AND status='verified'""").fetchone()[0]==0
        a=client.post('/api/review-approvals/'+f.json()['approval_id']+'/decide',
              json={'decision':'approve','note':'Validated source registration independently'},
              auth=auth('approverB'))
        assert a.status_code==200,a.text
        with connect(private_db) as db:
            assert db.execute("""SELECT COUNT(*) FROM identity_links
                     WHERE namespace='FDA_FEI' AND status='verified'""").fetchone()[0]==1
            register_frs_candidates(db,'site-1',[{'registry_id':'110000000123',
                'name':'Example Manufacturing','address':'35 Factory St, NC',
                'latitude':35.6,'longitude':-78.1}], 'https://www.epa.gov/frs')
            candidate=db.execute("SELECT id FROM match_candidates").fetchone()[0]
        proposal=client.post(f'/api/intelligence/candidates/{candidate}/review',
              json={'decision':'accepted','evidence_url':'https://www.epa.gov/frs',
                    'note':'Corroborated source address and exact legal operator'},
              auth=auth('reviewerA'))
        assert proposal.status_code==200,proposal.text
        completed=client.post('/api/review-approvals/'+proposal.json()['approval_id']+'/decide',
              json={'decision':'approve','note':'Independent corroboration of property registry identity'},
              auth=auth('approverB'))
        assert completed.status_code==200,completed.text
        with connect(private_db) as db:
            assert db.execute("""SELECT status FROM identity_links
                WHERE namespace='EPA_FRS'""").fetchone()[0]=='verified'
        revoke=client.post(f'/api/intelligence/candidates/{candidate}/review',
              json={'decision':'rejected','evidence_url':'https://www.epa.gov/frs',
                    'note':'Identified different building operated by another entity'},
              auth=auth('reviewerA'))
        reject=client.post('/api/review-approvals/'+revoke.json()['approval_id']+'/decide',
              json={'decision':'approve','note':'Second investigator confirmed this is not the same site'},
              auth=auth('approverB'))
        assert reject.status_code==200 and reject.json()['status']=='approved'
        with connect(private_db) as db:
            assert db.execute("""SELECT status FROM identity_links
                WHERE namespace='EPA_FRS'""").fetchone()[0]=='rejected'


def test_old_verified_fei_is_stale_after_establishment_identifier_change(private_db):
    from facilityrisk.assessment import build_assessment
    from facilityrisk.intelligence import verify_fei,intelligence_quality
    with connect(private_db) as db:
        verify_fei(db,'site-1','Source reviewer','https://www.fda.gov/',
                   'Initially verified original FDA site identifier')
        assert build_assessment(db,'site-1')['coverage']['regulatory_identity']['status']=='verified'
        db.execute("UPDATE facilities SET fei='2999999999' WHERE id='site-1'")
        db.commit()
        links=get_intelligence(db,'site-1')['identifiers']
        assert any(r['status']=='review_stale' and r['original_status']=='verified' for r in links)
        assert intelligence_quality(db)['stale_verified_fei_links']==1
        assert build_assessment(db,'site-1')['coverage']['regulatory_identity']['status']=='unassessed'
        verify_fei(db,'site-1','Source reviewer','https://www.fda.gov/',
                   'Independently reviewed the replacement FDA FEI and address')
        assert intelligence_quality(db)['verified_current_fei_links']==1
        assert intelligence_quality(db)['stale_verified_fei_links']==0
        assert db.execute("SELECT COUNT(*) FROM identity_links WHERE namespace='FDA_FEI' AND status='verified'").fetchone()[0]==1
