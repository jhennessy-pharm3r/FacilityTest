"""Campuses, buildings, units and source points are not synonymous with insured sites."""
import pytest

from facilityrisk.db import connect, initialize
from facilityrisk.physical_assets import (create_asset,revise_asset,facility_assets,
    propose_asset_review,decide_asset_review,asset_review_queue)


@pytest.fixture
def conn(tmp_path,monkeypatch):
    path=tmp_path/'physical-assets.sqlite'
    monkeypatch.setenv('FACILITY_RISK_DB',str(path))
    db=connect(path)
    initialize(db)
    db.execute("""INSERT INTO facilities
      (id,name,company,address,country,latitude,longitude,origin,last_imported)
      VALUES('site-a','Northern manufacturing campus','Northern Group','1 Industry Way',
        'CA',45.1,-64.2,'fixture','2026-10-23')""")
    db.execute("""INSERT INTO facilities
      (id,name,country,origin,last_imported)
      VALUES('site-b','Other hospital','US','fixture','2026-10-23')""")
    db.commit()
    yield db
    db.close()


def test_campus_building_and_review_are_not_property_geocode_validation(conn):
    campus=create_asset(conn,'site-a',{
      'asset_type':'campus','name':'North campus','address':'1 Industry Way',
      'country':'CA','source_url':'https://example.org/campus'},'analystA')
    building=create_asset(conn,'site-a',{
      'asset_type':'building','parent_asset_id':campus['asset_id'],
      'name':'Production building B','address':'1 Industry Way, B',
      'country':'CA','latitude':45.1,'longitude':-64.2,
      'reported_operator':'Northern Group','reported_parent':'Observed Corporate Parent',
      'source_record_ref':'source-2026-001'},'analystA')
    report=facility_assets(conn,'site-a')
    assert report['total_assets']==2
    assert report['identity_corroborated_assets']==0
    assert report['reviewed_property_coordinates']==0
    assert all(x['coordinate_quality']=='source_observed_unverified' for x in report['assets'])
    with pytest.raises(ValueError,match='same investigated facility'):
        create_asset(conn,'site-b',{
          'asset_type':'building','name':'Other unit','parent_asset_id':campus['asset_id']},'analystA')
    req=propose_asset_review(conn,building['asset_id'],{
      'proposed_status':'identity_corroborated',
      'review_evidence_url':'https://example.org/independent-site-map',
      'rationale':'The source plan shows a separately identifiable production building B at this campus'
    },'analystA')
    assert req['status']=='pending'
    with pytest.raises(ValueError,match='own proposal'):
        decide_asset_review(conn,req['review_id'],'approve','analystA',
           'Independent evidence review')
    decision=decide_asset_review(conn,req['review_id'],'approve','approverB',
           'Reviewed physical campus plan and distinct building address')
    assert decision['asset_identity_promoted'] is True
    assert decision['coordinate_verified'] is False
    assert facility_assets(conn,'site-a')['identity_corroborated_assets']==1
    assert facility_assets(conn,'site-a')['reviewed_property_coordinates']==0
    updated=revise_asset(conn,building['asset_id'],{
      'address':'1 Industry Way, Building B (corrected)'},'analystA')
    assert updated['status']=='candidate'
    assert facility_assets(conn,'site-a')['identity_corroborated_assets']==0


def test_asset_revision_invalidates_stale_independent_review(conn):
    site=create_asset(conn,'site-a',{
      'asset_type':'leased_unit','name':'Rented laboratory','country':'CA'},'analystA')
    req=propose_asset_review(conn,site['asset_id'],{
      'proposed_status':'identity_corroborated','review_evidence_url':'https://example.org/lease',
      'rationale':'The lease describes the individual enclosed unit under the same campus owner'
    },'analystA')
    revise_asset(conn,site['asset_id'],{'name':'Updated laboratory unit'},'analystA')
    decision=decide_asset_review(conn,req['review_id'],'approve','approverB',
        'Old lease references the prior description, so reject promotion')
    assert decision['status']=='invalidated'
    assert decision['asset_identity_promoted'] is False
    assert facility_assets(conn,'site-a')['identity_corroborated_assets']==0
    assert asset_review_queue(conn,'invalidated','site-a')['items'][0]['id']==req['review_id']


def test_source_coordinate_validation_and_private_api_write_gate(conn):
    from fastapi.testclient import TestClient
    from facilityrisk.app import app
    with pytest.raises(ValueError,match='complete point'):
        create_asset(conn,'site-a',{'asset_type':'building','name':'Unclear',
                     'latitude':45.0},'analystA')
    with pytest.raises(ValueError,match='Invalid source-reported'):
        create_asset(conn,'site-a',{'asset_type':'building','name':'Unclear',
                     'latitude':float('nan'),'longitude':-64.0},'analystA')
    with TestClient(app) as client:
        assert client.get('/api/facilities/site-a/assets').status_code==200
        request=client.post('/api/facilities/site-a/assets',
            json={'asset_type':'building','name':'Unaudited warehouse'})
        assert request.status_code==403
        assert client.get('/api/facilities/missing/assets').status_code==404
