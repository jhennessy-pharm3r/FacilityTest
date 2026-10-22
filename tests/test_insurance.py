from facilityrisk.insurance import taxonomy,facility_screening

def test_coverage_taxonomy_is_not_verified_insurance():
    coverage=taxonomy()
    by_id={row['id']:row for row in coverage}
    assert len(coverage)>=18
    for k in ('property','bi','utility','cbi','non_damage_bi',
              'parametric_flood','parametric_wind','parametric_outage'):
        assert k in by_id
        assert by_id[k]['verified_coverage']=='unknown'
        assert by_id[k]['review_requirements']

def test_parametric_is_suitability_only():
    report=facility_screening(hazards=['flood','wildfire'],utility_dependency=True)
    assert set(report['potentially_relevant_coverages'])=={
        'flood','wildfire','utility','parametric_outage'}
    assert report['verified_coverages']==[]
    assert report['coverage_verification']=='unassessed'
    assert facility_screening(hazards=['none'])['potentially_relevant_coverages']==[]

def test_insurance_api_reference_no_policy_assertion():
    from fastapi.testclient import TestClient
    from facilityrisk.app import app
    client=TestClient(app)
    r=client.get('/api/insurance/coverage-types')
    assert r.status_code==200
    assert len(r.json()['coverages'])>=18
    r=client.get('/api/insurance/screen',params={
        'hazard':'hurricane,earthquake','utility_dependent':'true'})
    assert r.status_code==200
    d=r.json()
    assert {'windstorm','earthquake','utility','parametric_outage'}<=set(
        d['potentially_relevant_coverages'])
    assert d['verified_coverages']==[]
