"""Irish environmental licence catalog is independent of FDA manufacturer identities."""
import pytest
from scripts.build_ireland_leap import make_ireland_catalog
from facilityrisk.registry_catalog import FIELDS

def row(profile='P0500',name='Example Medical Device Facility - P0500',licence='Industrial Emissions Licence'):
    return {'licenceprofileid':'fixture-guid-'+profile,
            'name':name,'profilenumber':profile,
            'activelicencetype':licence,'activelicenceregno':profile+'-01',
            'county':'Galway','town':'Galway','organisationname':'Example Health Company',
            'url':'https://leap.epa.ie/licence-profile/'+profile}

def test_leap_profile_is_licensed_record_not_verified_site():
    doc=make_ireland_catalog({'count':2,'list':[row(),row('L2036','Boston Scientific Clonmel Limited - L2036','Radiological Protection Licence')]},
                              generated_at='2026-10-21T00:00:00Z')
    assert doc['summary']['distinct_source_entities']==2
    assert doc['summary']['countries']==1
    assert doc['summary']['country_counts']=={'IE':2}
    assert doc['sources']['ireland_leap']['status']=='imported'
    entries=[dict(zip(FIELDS,r)) for r in doc['rows']]
    assert all(r['fei']=='' and r['address']=='' for r in entries)
    assert all(r['sector']=='Environmental licence' for r in entries)
    assert entries[0]['source']=='Ireland EPA LEAP'

def test_leap_source_rejects_partial_and_ambiguous_exports():
    with pytest.raises(ValueError,match='count'):make_ireland_catalog({'count':5,'list':[row()]})
    dedup=make_ireland_catalog({'count':2,'list':[row(),row()]})
    assert len(dedup['rows'])==1
    assert dedup['summary']['source_rows']==2
    assert dedup['summary']['repeated_guid_rows']==1
    duplicate_profile=make_ireland_catalog({'count':2,'list':[
        row('S0020','Sea Permit One - S0020'),
        dict(row('S0020','Sea Permit Two - S0020'),licenceprofileid='another-official-guid')
    ]})
    assert len(duplicate_profile['rows'])==2
    assert duplicate_profile['rows'][0][0]!=duplicate_profile['rows'][1][0]
    assert duplicate_profile['summary']['repeated_profile_numbers']==1
    with pytest.raises(ValueError,match='Conflicting LEAP'):
        make_ireland_catalog({'count':2,'list':[
            row(),dict(row(),name='Another establishment with same GUID')
        ]})
    with pytest.raises(ValueError,match='source URL'):
        make_ireland_catalog({'count':1,'list':[dict(row(),url='https://bad.example/profile')]})
    with pytest.raises(ValueError,match='expected'):
        make_ireland_catalog({'count':1,'list':[row()]},min_rows=2)


def test_private_import_of_leap_catalog_does_not_verify_manufacturer(tmp_path):
    import json
    from facilityrisk.db import connect,initialize
    from facilityrisk.site_workspace import import_ireland_leap_catalog,search_external_registry,track_external_registry_site
    snapshot=make_ireland_catalog({'count':1,'list':[row()]},min_rows=1)
    path=tmp_path/'ireland.json'
    path.write_text(json.dumps(snapshot),encoding='utf-8')
    with connect(tmp_path/'facilities.sqlite') as con:
        initialize(con)
        report=import_ireland_leap_catalog(con,path)
        assert report['imported_source_identities']==1
        found=search_external_registry(con,query='Example Medical',source_key='IE_LEAP')
        assert found['total']==1
        tracked=track_external_registry_site(con,found['items'][0]['id'],'reviewer')
        facility=con.execute('SELECT latitude,fei FROM facilities WHERE id=?',
                             (tracked['facility_id'],)).fetchone()
        assert facility['latitude'] is None and facility['fei'] is None
        observed=con.execute('SELECT status FROM identity_links WHERE facility_id=?',
                             (tracked['facility_id'],)).fetchone()
        assert observed['status']=='observed'
        assert con.execute('SELECT COUNT(*) FROM evidence').fetchone()[0]==0
        assert con.execute('SELECT COUNT(*) FROM historical_events').fetchone()[0]==0
