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


def test_npri_arcgis_pagination_and_disallow_partial_response(monkeypatch):
    from scripts.build_canada_npri import refresh
    ids=list(range(1,1602))
    queries=[]
    def endpoint(params):
        queries.append(params)
        if params.get('returnIdsOnly')=='true':
            return {'objectIds':ids}
        selected=[int(x) for x in params['objectIds'].split(',')]
        return {'features':[feature(oid,npri_id=100000+oid) for oid in selected]}
    monkeypatch.setattr('scripts.build_canada_npri.get_json',endpoint)
    catalog=refresh(min_rows=1000)
    assert len(catalog['rows'])==1601
    assert len(queries)==4
    assert [len(q['objectIds'].split(',')) for q in queries[1:]]==[800,800,1]
    assert all(q['returnGeometry']=='false' for q in queries[1:])
    assert all('Latitude' not in q['outFields'] for q in queries[1:])
    def incomplete(params):
        if params.get('returnIdsOnly')=='true':
            return {'objectIds':[5,6]}
        return {'features':[feature(5)]}
    monkeypatch.setattr('scripts.build_canada_npri.get_json',incomplete)
    with pytest.raises(ValueError,match='incomplete'):
        refresh(min_rows=1)


def test_npri_private_review_import_keeps_identifiers_unverified(tmp_path):
    import json
    from facilityrisk.db import connect,initialize
    from facilityrisk.site_workspace import (import_canada_npri_catalog,
                                               search_external_registry,
                                               track_external_registry_site)
    source=make_canada_catalog([feature(5,1234),feature(6,1234)],[5,6])
    filepath=tmp_path/'canada-npri.json'
    filepath.write_text(json.dumps(source),encoding='utf-8')
    with connect(tmp_path/'risk.sqlite') as conn:
        initialize(conn)
        stats=import_canada_npri_catalog(conn,filepath)
        assert stats['imported_source_identities']==2
        matches=search_external_registry(conn,query='Acme',source_key='CA_NPRI')
        assert matches['total']==2
        assert len({item['source_identifier'] for item in matches['items']})==2
        tracked=track_external_registry_site(conn,matches['items'][0]['id'],'researcher')
        site=conn.execute('SELECT latitude,longitude,fei FROM facilities WHERE id=?',
                          (tracked['facility_id'],)).fetchone()
        assert site['latitude'] is None and site['longitude'] is None and site['fei'] is None
        identity=conn.execute('SELECT status,namespace FROM identity_links WHERE facility_id=?',
                              (tracked['facility_id'],)).fetchone()
        assert identity['status']=='observed' and identity['namespace']=='CA_NPRI'
        assert conn.execute('SELECT COUNT(*) FROM evidence').fetchone()[0]==0
        assert conn.execute('SELECT COUNT(*) FROM historical_events').fetchone()[0]==0
        assert import_canada_npri_catalog(conn,filepath)['imported_source_identities']==2
        assert conn.execute('SELECT COUNT(*) FROM external_registry_entities').fetchone()[0]==2

def test_npri_invalid_source_does_not_write(tmp_path):
    import json
    from facilityrisk.db import connect,initialize
    from facilityrisk.site_workspace import import_canada_npri_catalog
    cat=make_canada_catalog([feature(5,1234)],[5])
    cat['rows'][0][FIELDS.index('fei')]='unverified-looking-id'
    output=tmp_path/'modified.json'
    output.write_text(json.dumps(cat),encoding='utf-8')
    with connect(tmp_path/'risk.sqlite') as conn:
        initialize(conn)
        with pytest.raises(ValueError,match='Invalid NPRI'):
            import_canada_npri_catalog(conn,output)
        assert conn.execute('SELECT COUNT(*) FROM external_registry_entities').fetchone()[0]==0
