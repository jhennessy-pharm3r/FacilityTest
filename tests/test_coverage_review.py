"""Policy evidence must never silently become verified insurance coverage."""
import pytest
from facilityrisk.db import connect,initialize
from facilityrisk.coverage_review import (create_policy,save_term,propose_term_review,
    decide_term_review,facility_policy_snapshot,compare_hazards_and_coverage)

@pytest.fixture
def db(tmp_path):
    c=connect(tmp_path/'policy.sqlite')
    initialize(c)
    c.execute("""INSERT INTO facilities
       (id,name,company,country,origin,last_imported)
       VALUES('policy-site','Distribution center','Carrier','US','test','2026-10-22')""")
    c.commit()
    yield c
    c.close()

def make_policy(c):
    return create_policy(c,'policy-site',{
        'insurer':'Sample Insurer','policy_reference':'example-1',
        'start_date':'2026-01-01','end_date':'2027-01-01',
        'location_schedule_reference':'Schedule item 17',
        'total_insured_value':1200000},'reviewerA')['policy_id']

def test_policy_approval_and_stale_revision(db):
    policy=make_policy(db)
    term=save_term(db,policy,{'coverage_id':'flood','limits':500000,'waiting_hours':48,
        'trigger_description':'Conditional physical damage at scheduled address'},'reviewerA')
    assert facility_policy_snapshot(db,'policy-site')['verified_current_coverage_count']==0
    proposal=propose_term_review(db,term['term_id'],{
        'proposed_status':'verified_conditional','document_reference':'secure-internal-doc-1',
        'document_sha256':'a'*64,'rationale':'Section 14 and declarations reviewed against scheduled location'
    },'reviewerA')
    with pytest.raises(ValueError,match='own proposal'):
        decide_term_review(db,proposal['review_id'],'approve','reviewerA',
                           'Independent evidence review performed')
    approved=decide_term_review(db,proposal['review_id'],'approve','approverB',
                  'Independently reviewed supplied contractual reference')
    assert approved['status']=='approved'
    assert facility_policy_snapshot(db,'policy-site')['verified_current_coverage_count']==1
    save_term(db,policy,{'coverage_id':'flood','limits':400000},'reviewerA')
    assert facility_policy_snapshot(db,'policy-site')['verified_current_coverage_count']==0
    proposal2=propose_term_review(db,term['term_id'],{
        'proposed_status':'verified_excluded','document_reference':'secure-internal-doc-1',
        'document_sha256':'b'*64,'rationale':'Flood exclusion expressly appears in the revised terms'
    },'reviewerA')
    save_term(db,policy,{'coverage_id':'flood','limits':300000},'reviewerA')
    assert decide_term_review(db,proposal2['review_id'],'approve','approverB',
         'Confirm old proposal is no longer current')['status']=='invalidated'
    assert facility_policy_snapshot(db,'policy-site')['verified_current_coverage_count']==0

def test_invalid_input_and_no_hazard_inference(db):
    policy=make_policy(db)
    with pytest.raises(ValueError,match='End date'):
        create_policy(db,'policy-site',{'insurer':'x','policy_reference':'y',
           'start_date':'2027-01-01','end_date':'2026-01-01',
           'location_schedule_reference':'ref'},'reviewerA')
    with pytest.raises(ValueError,match='outside accepted bounds'):
        save_term(db,policy,{'coverage_id':'flood','limits':'NaN'},'reviewerA')
    with pytest.raises(ValueError,match='Unknown insurance'):
        save_term(db,policy,{'coverage_id':'not-real'},'reviewerA')
    result=compare_hazards_and_coverage(db,'policy-site')
    assert result['site_coordinate_verified'] is False
    assert result['current_screened_perils']==[]
    assert result['risk_score'] is None
    assert result['insured_loss_estimate'] is None

def test_private_api_approval_is_not_available_to_anonymous_or_local_shared_user(db,monkeypatch):
    from fastapi.testclient import TestClient
    from facilityrisk.app import app
    monkeypatch.setenv('FACILITY_RISK_DB',str(db.execute('PRAGMA database_list').fetchone()[2]))
    with TestClient(app) as client:
        assert client.get('/api/facilities/policy-site/policies').status_code==200
        r=client.post('/api/facilities/policy-site/policies',json={
           'insurer':'x','policy_reference':'y','start_date':'2026-01-01',
           'end_date':'2027-01-01','location_schedule_reference':'item 1'})
        assert r.status_code==403


def test_document_reviewed_exclusion_not_counted_as_available_coverage(db):
    from facilityrisk.assessment import build_assessment,render_assessment_html
    policy=make_policy(db)
    term=save_term(db,policy,{'coverage_id':'flood','exclusions':'Flood explicitly excluded'},'reviewerA')
    proposed=propose_term_review(db,term['term_id'],{
      'proposed_status':'verified_excluded','document_reference':'secure-policy-archive-1',
      'document_sha256':'f'*64,
      'rationale':'Flood exclusion verified against applicable declarations and named terms'
    },'reviewerA')
    result=decide_term_review(db,proposed['review_id'],'approve','approverB',
      'Independent confirmation of express flood exclusion wording')
    assert result['status']=='approved'
    snapshot=facility_policy_snapshot(db,'policy-site')
    assert snapshot['document_reviewed_current_terms_count']==1
    assert snapshot['verified_excluded_current_terms_count']==1
    assert snapshot['verified_current_coverage_count']==0
    report=build_assessment(db,'policy-site')
    assert report['coverage']['insurance_terms']['status']=='document_reviewed_terms'
    html=render_assessment_html(report)
    assert 'Insurance contracts and coverage review' in html
    assert 'verified_excluded' in html
    assert 'secure-policy-archive-1' in html
    assert 'No verified current-property hazard and policy crosswalk' in html
