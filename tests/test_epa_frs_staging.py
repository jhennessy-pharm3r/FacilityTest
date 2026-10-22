import csv
import gzip
import io
import json
import zipfile

from scripts.build_epa_frs import build,normalize_row
from facilityrisk.universal_registry import import_records,search,statistics
from facilityrisk.db import initialize
import sqlite3

def test_official_frs_archive_to_universal_search(tmp_path):
    archive=tmp_path/'official.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('NATIONAL_SINGLE.csv',
           'REGISTRY_ID,PRIMARY_NAME,LOCATION_ADDRESS,CITY_NAME,STATE_CODE,COUNTRY_NAME,LATITUDE83,LONGITUDE83,NAICS_CODE\n'
           '110000000001,Redfield Warehouse,1 Dock St,Boston,MA,United States,42.1,-71.0,493110\n'
           '110000000002,Regional Hospital,2 Center St,Albany,NY,United States,42.6,-73.7,622110\n'
           ',Missing ID,3 Invalid St,Albany,NY,United States,42,-73,000000\n')
        z.writestr('README.txt','Source documentation')
    dest=tmp_path/'frs.csv.gz'
    result=build(archive,dest,max_rows=0,min_rows=2)
    assert result['read_rows']==3 and result['valid_records']==2
    assert result['rejected_rows']==1 and result['complete_source']
    with gzip.open(dest,'rt',encoding='utf-8') as f:
        rows=list(csv.DictReader(f))
    assert rows[0]['source_identifier']=='110000000001'
    assert rows[0]['country']=='US'
    assert rows[1]['industry']=='622110'
    c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row;initialize(c)
    imported=import_records(c,'EPA_FRS',rows,'https://www.epa.gov/frs/epa-frs-facilities-state-single-file-csv-download')
    assert imported['valid']==2
    assert search(c,q='Regional Hospital')['total']==1
    assert search(c,industry='622110')['total']==1
    assert statistics(c)['site_candidates']==2
    c.close()

def test_frs_sample_must_not_be_reported_complete(tmp_path):
    archive=tmp_path/'test.zip'
    with zipfile.ZipFile(archive,'w') as z:
        z.writestr('NATIONAL_SINGLE.csv','REGISTRY_ID,PRIMARY_NAME\n1,A\n2,B\n')
    out=build(archive,tmp_path/'sample.csv.gz',max_rows=1,min_rows=1)
    assert out['read_rows']==1 and not out['complete_source']

def test_upstream_schema_drift_rejected(tmp_path):
    archive=tmp_path/'wrong.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('national.csv','OTHER,FIELDS\n1,A\n')
    import pytest
    with pytest.raises(ValueError,match='schema changed'):
        build(archive,tmp_path/'bad.csv.gz',min_rows=1)
    assert not (tmp_path/'bad.csv.gz').exists()

def test_missing_industry_is_unclassified():
    r=normalize_row({'REGISTRY_ID':'1','PRIMARY_NAME':'Plant','COUNTRY_NAME':'Canada'})
    assert r['country']==''
    assert r['industry']=='Unclassified'
