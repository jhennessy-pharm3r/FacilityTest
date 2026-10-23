"""Every BI scenario amount is an analyst assumption, never insured recovery."""
import base64
import json
import math

import pytest
from fastapi.testclient import TestClient

from facilityrisk.app import app
from facilityrisk.bi_scenarios import calculate_components,facility_scenarios,save_scenario
from facilityrisk.db import connect,initialize
from facilityrisk.security import make_password_hash


@pytest.fixture
def db(tmp_path,monkeypatch):
    database=tmp_path/'bi-scenarios.sqlite'
    monkeypatch.setenv('FACILITY_RISK_DB',str(database))
    c=connect(database)
    initialize(c)
    c.execute("""INSERT INTO facilities (id,name,origin,last_imported)
       VALUES('facility-1','Distribution facility','fixture','2026-10-23')""")
    c.execute("""INSERT INTO facilities (id,name,origin,last_imported)
       VALUES('facility-2','Other operator','fixture','2026-10-23')""")
    c.commit()
    yield c
    c.close()


def scenario():
    return dict(scenario_name='Grid outage with temporary generator',
      interruption_cause='utility_failure',affected_dependency='grid_power',
      scenario_description='Five day blackout with a partial restart',
      assumption_basis='Analyst stress scenario, no actual event or insured loss proven',
      gross_outage_days=5,margin_at_risk_daily_usd=12000,
      outage_mitigation_fraction=0.25,
      recovery_ramp_days=2,recovery_average_capacity=0.5,
      extra_expense_usd=15000,stock_spoilage_usd=4000,
      property_repair_usd=None)


def test_operating_margin_and_restart_calculation_is_not_payout():
    calculated=calculate_components(scenario())
    assert calculated['equivalent_lost_operating_days']==4.75
    assert calculated['illustrative_lost_contribution_margin_usd']==57000
    assert calculated['additional_expense_components_usd']['extra_expense']==15000
    assert calculated['gross_combined_claim_usd'] is None
    assert calculated['verified_insured_recovery_usd'] is None
    assert calculated['verified_coverage_status']=='unknown'
    assert 'utility' in calculated['coverage_topics_to_review']
    assert 'parametric_outage' in calculated['coverage_topics_to_review']


def test_private_scenario_saved_and_amended_with_audit_and_report(db):
    from facilityrisk.assessment import build_assessment,render_assessment_html
    new=save_scenario(db,'facility-1',scenario(),'reviewerA')
    assert new['revision']==1 and new['confirmed_policy_recovery'] is None
    result=facility_scenarios(db,'facility-1')
    assert result['count']==1
    assert result['scenarios'][0]['illustration']['illustrative_lost_contribution_margin_usd']==57000
    assert result['total_insured_recovery_usd'] is None
    report=build_assessment(db,'facility-1')
    assert report['coverage']['interruption_scenarios']['status']=='analyst_illustrations'
    assert report['risk_score'] is None
    assert '57,000' not in render_assessment_html(report) or 'unverified' in render_assessment_html(report)
    assert 'Grid outage with temporary generator' in render_assessment_html(report)
    updated=scenario()
    updated['gross_outage_days']=2
    revision=save_scenario(db,'facility-1',updated,'reviewerA',new['scenario_id'])
    assert revision['revision']==2
    assert facility_scenarios(db,'facility-1')['scenarios'][0]['illustration']['illustrative_lost_contribution_margin_usd']==30000
    assert facility_scenarios(db,'facility-2')['count']==0
    with pytest.raises(ValueError,match='Unknown facility scenario'):
        save_scenario(db,'facility-2',updated,'reviewerA',new['scenario_id'])
    actions=db.execute("""SELECT COUNT(*) FROM audit_events WHERE
        action LIKE 'interruption_assumption_%'""").fetchone()[0]
    assert actions==2


def test_bad_financial_assumptions_refused(db):
    data=scenario()
    for field,value in [('margin_at_risk_daily_usd',-1),
                        ('gross_outage_days',float('inf')),
                        ('outage_mitigation_fraction',1.5),
                        ('recovery_ramp_days',-1),
                        ('recovery_average_capacity',float('nan')),
                        ('extra_expense_usd',-25),
                        ('margin_at_risk_daily_usd','not a number')]:
        candidate={**data,field:value}
        with pytest.raises(ValueError):
            save_scenario(db,'facility-1',candidate,'reviewerA')
    with pytest.raises(ValueError,match='Unrecognized interruption'):
        save_scenario(db,'facility-1',{**data,'interruption_cause':'unsupported'},'reviewerA')
    with pytest.raises(ValueError,match='Individually authenticated'):
        save_scenario(db,'facility-1',data,'local-development')
    assert facility_scenarios(db,'facility-1')['count']==0


def test_private_api_write_requires_individual_auth_and_rejects_approver_writes(db,monkeypatch):
    users={'reviewerA':{'role':'reviewer',
             'password_hash':make_password_hash('reporting-password-2026-researcher')},
           'approverB':{'role':'approver',
             'password_hash':make_password_hash('reporting-password-2026-approver')}}
    monkeypatch.setenv('FACILITY_RISK_USERS_JSON',json.dumps(users))
    monkeypatch.setenv('FACILITY_RISK_REQUIRE_AUTH','1')
    monkeypatch.setenv('FACILITY_RISK_ENABLE_WRITES','1')
    monkeypatch.setenv('FACILITY_RISK_DUAL_REVIEW','1')
    def auth(account,password):
        return {'Authorization':'Basic '+base64.b64encode(
            (account+':'+password).encode()).decode()}
    reviewer=auth('reviewerA','reporting-password-2026-researcher')
    approver=auth('approverB','reporting-password-2026-approver')
    with TestClient(app) as client:
        assert client.get('/api/facilities/facility-1/interruption-scenarios').status_code==401
        assert client.get('/api/facilities/facility-1/interruption-scenarios',
                          headers=reviewer).json()['count']==0
        forbidden=client.post('/api/facilities/facility-1/interruption-scenarios',
                              headers=approver,json=scenario())
        assert forbidden.status_code==403
        created=client.post('/api/facilities/facility-1/interruption-scenarios',
                            headers=reviewer,json=scenario())
        assert created.status_code==200,created.text
        updated=client.patch('/api/facilities/facility-1/interruption-scenarios/'+created.json()['scenario_id'],
                             headers=reviewer,json={**scenario(),'gross_outage_days':3})
        assert updated.status_code==200,updated.text
        fetched=client.get('/api/facilities/facility-1/interruption-scenarios',
                           headers=reviewer)
        assert fetched.json()['scenarios'][0]['revision']==2
        assert fetched.json()['total_insured_recovery_usd'] is None
