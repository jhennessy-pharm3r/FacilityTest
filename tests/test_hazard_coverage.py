"""A single official source lookup cannot clear a facility of all catastrophe perils."""
from facilityrisk.db import connect,initialize
from facilityrisk.hazard_coverage import PERILS,build_peril_coverage
from facilityrisk.assessment import build_assessment,render_assessment_html
from facilityrisk.intelligence import review_location,store_hazard


def test_peril_matrix_does_not_convert_missing_or_unmapped_to_low_risk():
    values=build_peril_coverage([],point_verified=False)
    assert values['status']=='unassessed'
    assert len(values['perils_unassessed'])==len(PERILS)
    assert values['perils_source_screened']==[]
    missing=build_peril_coverage([{
      'peril':'Flood zone','status':'mapped_sfha','source':'FEMA NFHL',
      'valid_for_current_site_point':False
    }],point_verified=True)
    assert missing['status']=='unassessed'
    unknown=build_peril_coverage([{
      'peril':'Flood zone','status':'not_mapped','source':'FEMA NFHL',
      'valid_for_current_site_point':True
    }],point_verified=True)
    assert unknown['status']=='source_checked_unresolved'
    flood=next(v for v in unknown['perils'] if v['key']=='flood')
    assert flood['status']=='source_checked_unresolved'
    assert 'NOT a low-risk' in flood['interpretation']
    assert len(unknown['perils_unassessed'])==len(PERILS)-1
    assert unknown['perils_source_screened']==[]


def test_real_reviewed_flood_still_leaves_other_catastrophe_perils_unassessed(tmp_path):
    c=connect(tmp_path/'risk.sqlite');initialize(c)
    c.execute("""INSERT INTO facilities
       (id,name,address,country,latitude,longitude,origin,last_imported)
       VALUES('facility-1','Riverbank Distribution Hub','100 Riverside St','US',
        35.2,-78.1,'test','2026-10-23')""")
    c.commit()
    review_location(c,'facility-1','site_verified','https://example.org/property-survey',
      'Named reviewer','Independently corroborated exact property point')
    store_hazard(c,'facility-1','Flood zone','mapped_sfha','FEMA NFHL',
        'Regulatory special flood hazard area at source point',
        'https://hazards.fema.gov/arcgis/',zone='AE')
    report=build_assessment(c,'facility-1')
    pc=report['peril_coverage']
    assert pc['status']=='partially_source_screened'
    assert pc['perils_source_screened']==['flood']
    assert len(pc['perils_unassessed'])==len(PERILS)-1
    assert report['coverage']['natural_hazards']['status']=='partially_source_screened'
    assert report['risk_score'] is None
    assert 'unassessed catastrophe perils' in str(report['recommended_actions'])
    html=render_assessment_html(report)
    assert 'Catastrophe peril-by-peril evidence coverage' in html
    assert 'Hurricane / windstorm' in html
    assert 'Flood / river and inland inundation' in html
    # Revising the source point invalidates the earlier approved coordinate,
    # and old FEMA screening MUST NOT count as valid for new geography.
    c.execute("UPDATE facilities SET latitude=36.1 WHERE id='facility-1'")
    c.commit()
    stale=build_assessment(c,'facility-1')
    assert stale['peril_coverage']['status']=='unassessed'
    assert not stale['peril_coverage']['perils_source_screened']
    assert stale['coverage']['natural_hazards']['status']=='unassessed'
    c.close()


def test_categorizes_distinct_perils_and_does_not_infer_from_generic_storm():
    rows=[
      {'peril':'USGS Earthquake','status':'nearby_observed','source':'USGS',
       'valid_for_current_site_point':True},
      {'peril':'WRI Aqueduct water stress','status':'basin_observed','source':'WRI',
       'valid_for_current_site_point':True},
      {'peril':'Major natural catastrophe','status':'source_only','source':'Other',
       'valid_for_current_site_point':True},
      {'peril':'Generic storm event','status':'source_only','source':'Other',
       'valid_for_current_site_point':True},
    ]
    report=build_peril_coverage(rows,point_verified=True)
    assert report['perils_source_screened']==['earthquake','drought_water']
    assert len(report['uncategorized_current_source_perils'])==2
    assert len(report['perils_unassessed'])==len(PERILS)-2
    assert report['status']=='partially_source_screened'
