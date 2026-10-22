import json
import sqlite3
from scripts.import_universal import geojsonseq_rows
from facilityrisk.universal_registry import import_records,search
from facilityrisk.db import initialize

def test_overture_geojsonseq_record_separator_and_source_identity(tmp_path):
    p=tmp_path/'overture.geojsonseq'
    first={'type':'Feature','id':'GERS-1',
       'geometry':{'type':'Point','coordinates':[-63.56,44.65]},
       'properties':{'names':{'primary':'Downtown Warehouse'},
                     'categories':{'primary':'warehouse'},
                     'addresses':[{'freeform':'1 Main St','country':'CA',
                                   'region':'NS','locality':'Halifax'}],
                     'confidence':0.84}}
    second={'type':'Feature','id':'GERS-2',
       'geometry':{'type':'Point','coordinates':[-71.06,42.36]},
       'properties':{'names':{'primary':'General Hospital'},
                     'categories':{'primary':'hospital'},
                     'addresses':[{'freeform':'2 Hospital Rd','country':'US',
                                   'region':'MA','locality':'Boston'}]}}
    p.write_text('\x1e'+json.dumps(first)+'\n'+json.dumps(second)+'\n',encoding='utf-8')
    rows=list(geojsonseq_rows(p))
    assert len(rows)==2
    assert rows[0]['source_identifier']=='GERS-1'
    assert rows[0]['name']=='Downtown Warehouse'
    assert rows[0]['latitude']==44.65 and rows[0]['longitude']==-63.56
    assert rows[1]['industry']=='hospital'
    c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row;initialize(c)
    import_records(c,'OVERTURE',iter(rows),'https://docs.overturemaps.org/',vintage='2026-10')
    assert search(c,q='Warehouse')['total']==1
    assert search(c,q='Hospital')['total']==1
    assert search(c,country='CA')['total']==1
    assert search(c)['total']==2
    c.close()


def test_current_overture_2026_taxonomy_and_category_fallback(tmp_path):
    path=tmp_path/'current.geojsonseq'
    records=[
        {'type':'Feature','geometry':{'type':'Point','coordinates':[-6.2,53.3]},
         'properties':{'id':'GERS-HOSPITAL','names':{'primary':'City Hospital'},
                       'basic_category':'hospital','taxonomy':{'primary':'general_hospital'},
                       'addresses':[{'country':'IE'}]}},
        {'type':'Feature','geometry':{'type':'Point','coordinates':[-6.21,53.31]},
         'properties':{'id':'GERS-FACTORY','names':{'primary':'Chemical Manufacturing Site'},
                       'basic_category':'factory','taxonomy':{'primary':'chemical_factory'},
                       'addresses':[{'country':'IE'}]}},
        {'type':'Feature','geometry':{'type':'Point','coordinates':[-6.22,53.32]},
         'properties':{'id':'GERS-WAREHOUSE','names':{'primary':'Distribution Warehouse'},
                       'basic_category':'warehouse',
                       'addresses':[{'country':'IE'}]}}
    ]
    path.write_text('\n'.join(json.dumps(row) for row in records),encoding='utf-8')
    actual=list(geojsonseq_rows(path))
    assert [r['industry'] for r in actual]==['general_hospital','chemical_factory','warehouse']
    assert [r['source_identifier'] for r in actual]==['GERS-HOSPITAL','GERS-FACTORY','GERS-WAREHOUSE']
