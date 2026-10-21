"""Canada NPRI ArcGIS bulk-source fixture checks; no claimed factory risk or pollution loss."""
import pytest
from scripts.build_canada_npri import make_canada_catalog, normalize_feature
from facilityrisk.registry_catalog import FIELDS

def feature(objectid=5,npri_id=1234,year=2024,name='Acme Quebec Devices'):
    return {'attributes':{'OBJECTID_1':objectid,'NpriID':npri_id,'ReportYear':year,
            'FacilityName':name,'CompanyName':'Acme Holdings Inc',
            'Address1':'123 rue industrielle','City':'Montreal',
            'ProvinceCode':'QC','NAICS__Code_SCIAN':339112,
            'SectorDescriptionEn':'Other Manufacturing',
            'Latitude':45.6,'Longitude':-73.7}}

def test_npri_arcgis_catalog_keeps_source_identity_unrated():
    f1=feature()
    f2=feature(6,1235,name='Acme Devices Building B')
    cat=make_canada_catalog([f1,f2],[5,6],min_rows=2,
                            generated_at='2026-10-21T00:00:00Z')
    assert cat['summary']['distinct_source_entities']==2
    assert cat['summary']['reported_years']=={'2024':2}
    rows=[dict(zip(FIELDS,row)) for row in cat['rows']]
    assert all(r['sector']=='Environmental reporting' for r in rows)
    assert all(r['source']=='Canada NPRI' and r['country']=='CA' for r in rows)
    assert all(not r['fei'] for r in rows)
    assert all('2024' in r['activities'] for r in rows)
    assert '45.6' not in str(cat)
    assert '-73.7' not in str(cat)
    assert all('Acme' in r['name'] for r in rows)

def test_npri_arcgis_incomplete_or_duplicate_source_rejected():
    f=feature()
    with pytest.raises(ValueError,match='Incomplete'):
        make_canada_catalog([f],[5,6])
    with pytest.raises(ValueError,match='Repeated'):
        make_canada_catalog([f,f],[5])
    with pytest.raises(ValueError,match='Duplicate requested'):
        make_canada_catalog([f],[5,5])
    with pytest.raises(ValueError,match='below|Unexpectedly small'):
        make_canada_catalog([f],[5],min_rows=2)
    with pytest.raises(ValueError,match='outside'):
        make_canada_catalog([f],[99])
    with pytest.raises(ValueError,match='missing stable'):
        normalize_feature({'attributes':{'OBJECTID_1':9,'FacilityName':'Missing NPRI ID'}})

def test_npri_same_public_npri_id_on_separate_object_records_stays_separate():
    # Never merge reported objects by company or by a weak display label.
    data=make_canada_catalog([feature(5,1234),feature(6,1234)],
                             [5,6])
    assert len(data['rows'])==2
    assert data['summary']['repeated_npri_identifiers']==1
