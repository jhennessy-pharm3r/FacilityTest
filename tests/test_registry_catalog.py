"""Facility-wide search and canonical registration identity coverage.

All test establishments below are synthetic fixtures; no assumed underwriting risk.
"""
import json
import zipfile
from pathlib import Path
from fastapi.testclient import TestClient
import pytest
from facilityrisk.app import app
from facilityrisk.db import connect,initialize
from facilityrisk.registry_catalog import (FIELDS,normalize_device,normalize_drug,parse_drug_zip,
    make_catalog,validate_catalog,import_catalog,registry_search)
from scripts.build_catalog import drug_zip_url


def device(name,fei,city='Albany',types=None,owner='Test Medical'):
    return {'registration':{'name':name,'fei_number':fei,'registration_number':'998001',
        'city':city,'state_code':'NY','iso_country_code':'US','address_line_1':'1 Medical Way',
        'owner_operator':{'firm_name':owner},'reg_expiry_date_year':'2026'},
        'establishment_type':types or ['Manufacture Medical Device']}


def test_device_normalization_dedup_and_roles():
    a=normalize_device(device('Test Assembly','3000123401'))
    b=normalize_device(device('Test Assembly','3000123401',types=['Sterilize Medical Device for Another Party (Contract Sterilizer)']))
    third=normalize_device(device('Another Site','3000123402','Rochester'))
    assert a['country']=='US' and a['fei']=='3000123401' and a['source_records']==1
    cat=make_catalog([a,b,third],{'fda_device':{'status':'imported'}})
    validate_catalog(cat)
    assert cat['summary']['source_rows']==3
    assert cat['summary']['distinct_source_entities']==2
    combined=[dict(zip(FIELDS,r)) for r in cat['rows'] if r[6]=='3000123401'][0]
    assert 'Sterilize Medical Device' in combined['activities']
    assert 'Manufacture Medical Device' in combined['activities']
    assert not ('email' in json.dumps(cat).lower() or 'bus_phone' in json.dumps(cat).lower())


def test_drug_normalizer_uses_headered_zip(tmp_path):
    src=tmp_path/'drugs.zip'
    with zipfile.ZipFile(src,'w') as z:
        z.writestr('registered.txt','Establishment Name|FEI Number|Country|City|Address Line 1|Firm Name\nACME PHARMA|3000555000|US|BOSTON|2 PHARMA RD|ACME CORP\n')
    rows=list(parse_drug_zip(src))
    assert len(rows)==1 and rows[0]['sector']=='Pharmaceutical'
    assert rows[0]['name']=='ACME PHARMA'
    assert rows[0]['fei']=='3000555000'
    assert normalize_drug({'Establishment Name':'Unknown'}) is None
    with zipfile.ZipFile(tmp_path/'bad.zip','w') as z:z.writestr('unrecognized.csv','Foo,Bar\nA,B')
    with pytest.raises(ValueError,match='recognizable'):list(parse_drug_zip(tmp_path/'bad.zip'))


def test_drug_zip_href_is_official_only():
    valid='<a href="https://www.accessdata.fda.gov/data/registration/drug.zip">Drug establishment annual registration status download file (zip format)</a>'
    assert drug_zip_url(valid).endswith('drug.zip')
    invalid='<a href="https://example.com/data.zip">Drug establishment annual registration status download file (zip format)</a>'
    with pytest.raises(ValueError,match='unexpected'):drug_zip_url(invalid)


def test_all_facility_catalog_local_api_and_track(tmp_path,monkeypatch):
    path=tmp_path/'registry.sqlite';monkeypatch.setenv('FACILITY_RISK_DB',str(path))
    a=normalize_device(device('Acme Medical Inc','3000123401'))
    b=normalize_device(device('Acme Devices Galway','3000123402',city='GALWAY'))
    b.update(country='IE')
    c=normalize_drug({'Establishment Name':'Acme Bio Ireland','FEI Number':'3000123403','Country':'IE','City':'Cork','Address':'1 Port St'})
    entries=make_catalog([a,b,c],{'fda_device':{'status':'imported'},'fda_drug':{'status':'imported'}})
    source=tmp_path/'registry.json';source.write_text(json.dumps(entries),encoding='utf-8')
    with connect(path) as con:
        initialize(con)
        assert import_catalog(con,source)['imported_facilities']==3
        r=registry_search(con,'Acme',country='IE')
        assert r['total']==2
        assert registry_search(con,'3000123401')['total']==1
        assert registry_search(con,'Acme',sector='Pharmaceutical')['total']==1
    with TestClient(app) as client:
        r=client.get('/api/registry?q=Acme')
        assert r.status_code==200 and r.json()['total']==3
        assert client.get('/api/registry/status').json()['records']==3
        assert client.get('/api/registry?q=Galway').json()['total']==1
        rid=r.json()['items'][0]['id']
        assert client.get('/api/registry/'+rid).json()['id']==rid
        assert client.post('/api/registry/'+rid+'/track').status_code==403
        monkeypatch.setenv('FACILITY_RISK_ENABLE_WRITES','1')
        tracked=client.post('/api/registry/'+rid+'/track')
        assert tracked.status_code==200
        fid=tracked.json()['facility_id']
        detail=client.get('/api/facilities/'+fid).json()['facility']
        assert detail['latitude'] is None and detail['longitude'] is None
        assert 'not yet independently verified' in detail['research_summary']
        intel=client.get('/api/facilities/'+fid+'/intelligence').json()
        assert not any(x['status']=='verified' for x in intel['identifiers'])


def test_catalog_validator_rejects_duplicates():
    d=make_catalog([normalize_device(device('Test','3000000001'))],{})
    d['rows'].append(d['rows'][0])
    with pytest.raises(ValueError,match='duplicate'):validate_catalog(d)

def test_realistic_decrs_windows1252_tsv_and_no_contacts(tmp_path):
    """DECRS may use cp1252, prefixed headers, and an extra trailing tab."""
    src=tmp_path/'drls_reg.zip'
    content=(' Firm Name\\tFEI Number\\tDUNS Number\\tFirm Address\\tCountry\\tBusiness Operation\\tExpiration Date\\tAgent Email\\t\\n'
             'PHARMACIE QUÉBEC\\t0000000360\\t001234567\\t1 RUE DU CANAL\\tCANADA\\tManufacture\\t2026-12-31\\tprivate@example.net\\t\\n')
    with zipfile.ZipFile(src,'w') as z:
        z.writestr('drls_reg.txt',content.encode('cp1252'))
    got=list(parse_drug_zip(src))
    assert len(got)==1
    assert got[0]['fei']=='0000000360'
    assert got[0]['name']=='PHARMACIE QUÉBEC'
    assert got[0]['registration_number']=='001234567'
    assert got[0]['country']=='CANADA'
    assert got[0]['address']=='1 RUE DU CANAL'
    assert 'private@example.net' not in json.dumps(got)
    assert got[0]['expiry_year']=='2026-12-31'


def test_import_keeps_last_successful_drug_snapshot_on_source_failure(tmp_path,monkeypatch):
    from scripts.build_catalog import run
    path=tmp_path/'catalog.json'
    sample=normalize_device(device('Sample Medical','3000221001'))
    drug=normalize_drug({'Firm Name':'Example Pharmaceuticals','FEI':'0011100001','Country':'US'})
    # Build a synthetic previous publication of sufficient size for safety gate.
    prior=make_catalog([sample]+[dict(drug,id='drug-'+str(i),fei=str(i)) for i in range(5001)],
                       {'fda_drug':{'status':'imported'},'fda_device':{'status':'imported'}})
    path.write_text(json.dumps(prior),encoding='utf-8')
    device_zip=tmp_path/'device.zip'
    with zipfile.ZipFile(device_zip,'w') as z:
        z.writestr('device.json',json.dumps({'results':[device('Sample Medical','3000221001')]}))
    monkeypatch.setattr('scripts.build_catalog.get_bytes',lambda url: (_ for _ in ()).throw(OSError('source unavailable')))
    monkeypatch.setattr('scripts.build_catalog.download_zip',lambda url: (_ for _ in ()).throw(OSError('source unavailable')))
    monkeypatch.setattr('scripts.build_catalog.device_records',lambda paths: iter([sample]))
    updated=run(path,device_archives=[device_zip])
    assert updated['sources']['fda_drug']['status']=='stale_preserved'
    assert updated['sources']['fda_drug']['preserved_site_records']==5001
    assert updated['summary']['by_sector']['Pharmaceutical']==5001
