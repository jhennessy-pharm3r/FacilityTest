import csv
import sqlite3
import pytest
from scripts.import_universal import csv_rows
from facilityrisk.universal_registry import import_records, search, statistics

def test_csv_import_uses_canonical_source_identifier_header(tmp_path):
    p=tmp_path/'frs.csv'
    p.write_text('source_identifier,name,company,address,city,country,industry\n'
                 'FRS123,Harbour Freight Terminal,Port Corp,12 Dock Rd,Halifax,CA,Transport\n'
                 'FRS124,Regional Hospital,Hospital Corp,11 Health St,Moncton,CA,Healthcare\n',
                 encoding='utf-8')
    mapping={k:k for k in ('source_identifier','name','company','address','city','country','industry')}
    rows=list(csv_rows(p,mapping))
    assert len(rows)==2 and rows[0]['source_identifier']=='FRS123'
    c=sqlite3.connect(':memory:')
    c.row_factory=sqlite3.Row
    out=import_records(c,'EPA_FRS',iter(rows),'https://www.epa.gov/frs',vintage='2026-10')
    assert out['read']==out['valid']==2
    assert statistics(c)['source_identities']==2
    assert search(c,q='hospital')['total']==1
    assert search(c,country='CA')['total']==2
    c.close()

def test_csv_import_rejects_missing_identifier_header(tmp_path):
    p=tmp_path/'wrong.csv'
    p.write_text('id,name\n1,Unknown\n',encoding='utf-8')
    with pytest.raises(ValueError,match='Mapping requires real source ID'):
        list(csv_rows(p,{'source_identifier':'source_identifier','name':'name'}))
