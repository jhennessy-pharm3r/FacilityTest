"""Irish environmental licence catalog is independent of FDA manufacturer identities."""
import pytest
from scripts.build_ireland_leap import make_ireland_catalog
from facilityrisk.registry_catalog import FIELDS

def row(profile='P0500',name='Example Medical Device Facility - P0500',licence='Industrial Emissions Licence'):
    return {'licenceprofileid':'b9014b7f-a1f2-4000-9121-009933220011',
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
    with pytest.raises(ValueError,match='Repeated'):
        make_ireland_catalog({'count':2,'list':[row(),row()]})
    with pytest.raises(ValueError,match='source URL'):
        make_ireland_catalog({'count':1,'list':[dict(row(),url='https://bad.example/profile')]})
    with pytest.raises(ValueError,match='expected'):
        make_ireland_catalog({'count':1,'list':[row()]},min_rows=2)
