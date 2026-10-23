import sqlite3
from pathlib import Path
from facilityrisk.universal_registry import (import_records,search,detail,statistics,
    review_source_link,track_for_research)
from facilityrisk.db import initialize

def db():
    c=sqlite3.connect(':memory:')
    c.row_factory=sqlite3.Row
    initialize(c)
    return c

def test_cross_industry_search_and_no_false_dedupe():
    c=db()
    source='https://www.epa.gov/frs'
    us=[{'id':'FRS1','name':'Cobalt Chemical Works','company':'Cobalt','city':'Pittsburgh',
         'state':'PA','country':'US','industry':'Chemical manufacturing','latitude':40.42,'longitude':-79.97},
        {'id':'FRS2','name':'General Hospital','company':'General Healthcare','city':'Boston',
         'country':'US','industry':'Healthcare'},
        {'id':'','name':'bad'},{'id':'FRS3','name':'Factory','latitude':999,'longitude':30}]
    a=import_records(c,'EPA_FRS',iter(us),source,vintage='2026')
    assert a=={'source':'EPA_FRS','read':4,'valid':3,'new_source_identities':3,'rejected':1,'vintage':'2026'}
    assert search(c)['total']==3
    assert search(c,q='Cobalt')['total']==1
    assert search(c,q='hospital')['total']==1
    assert search(c,country='US',industry='Healthcare')['total']==1
    assert search(c,source='EPA_FRS')['total']==3
    assert search(c,q='FRS2')['total']==1
    assert search(c,q='missing')['total']==0
    invalid=search(c,q='Factory')['items'][0]
    assert invalid['latitude'] is None and invalid['longitude'] is None
    old=search(c,q='Cobalt')['items'][0]['id']
    import_records(c,'OVERTURE',[{'id':'place1','name':'Cobalt Chemical Works',
        'city':'Pittsburgh','country':'US','industry':'industrial'}],
        'https://docs.overturemaps.org/')
    assert search(c)['total']==4
    assert detail(c,old)['source_identities'][0]['source_identifier']=='FRS1'
    assert statistics(c)['source_identities']==4
    c.close()

def test_refresh_preserves_reviewed_site_and_identity_link():
    c=db()
    url='https://www.epa.gov/frs'
    r={'id':'11','name':'Original Warehouse','country':'US','address':'1 Main St'}
    import_records(c,'EPA_FRS',[r],url)
    before=search(c,q='Original')['items'][0]['id']
    other={'id':'A1','name':'Original Warehouse','country':'US'}
    import_records(c,'OVERTURE',[other],'https://docs.overturemaps.org/')
    target=search(c,source='OVERTURE')['items'][0]['id']
    try:
        review_source_link(c,source_key='OVERTURE',source_identifier='A1',
            target_site_id=before,evidence_url='https://example.com/verification',
            rationale='Independent address and property corroboration',reviewer='alice',approver='alice')
        assert False,'Same person should not self-approve'
    except ValueError:
        pass
    d=review_source_link(c,source_key='OVERTURE',source_identifier='A1',
        target_site_id=before,evidence_url='https://example.com/verification',
        rationale='Independent address and property corroboration',reviewer='alice',approver='bob')
    assert d['linked_to']==before
    assert statistics(c)['site_candidates']==1
    assert len(detail(c,before)['source_identities'])==2
    import_records(c,'EPA_FRS',[{'id':'11','name':'Renamed Warehouse','address':'2 Main St',
        'country':'US'}],url,vintage='2027')
    assert len(detail(c,before)['source_identities'])==2
    assert search(c,q='Renamed')['total']==1
    assert search(c,q='Original')['total']==0
    assert c.execute('SELECT COUNT(*) FROM universal_identity_decisions').fetchone()[0]==1
    c.close()

def test_api_facilities_are_unassessed(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from facilityrisk.app import app
    from facilityrisk import db as d
    path=tmp_path/'data.sqlite'
    monkeypatch.setenv('FACILITY_RISK_DB',str(path))
    c=d.connect();d.initialize(c)
    import_records(c,'OVERTURE',[{'id':'loc-x','name':'New Public Library','country':'CA',
       'industry':'Public service'}],'https://docs.overturemaps.org/')
    c.close()
    client=TestClient(app)
    response=client.get('/api/universal-facilities',params={'q':'Library'})
    assert response.status_code==200 and response.json()['total']==1
    row=response.json()['items'][0]
    detail_response=client.get('/api/universal-facilities/'+row['id'])
    assert detail_response.status_code==200
    assert detail_response.json()['risk_status']=='unassessed'
    assert detail_response.json()['insured_coverage_status']=='unknown'
    assert client.post('/api/universal-facilities/'+row['id']+'/track').status_code in (401,403)


def test_indexed_prefix_source_lookup_and_safe_queries():
    conn=db()
    records=[
      {'id':'FEI30000001','name':'North Shore Manufacturing','country':'US','industry':'Factory'},
      {'id':'FEI30000002','name':'Regional Clinic','country':'CA','industry':'Healthcare'},
      {'id':'OTHER001','name':'Redwood Warehouse','country':'US','industry':'Transport'}
    ]
    import_records(conn,'TEST',records,'https://example.com/registry')
    # Source identifiers are located by case-insensitive prefix without
    # requiring the number/identifier in the visible facility name.
    assert search(conn,q='FEI30000001')['total']==1
    assert search(conn,q='fei300')['total']==2
    assert search(conn,q='OTHER')['total']==1
    assert search(conn,q='manufact')['total']==1
    assert search(conn,q='Regional Clinic')['total']==1
    assert search(conn,country='US')['total']==2
    plans=[r[3] for r in conn.execute(
        'EXPLAIN QUERY PLAN SELECT site_id FROM universal_source_records WHERE source_identifier LIKE ?',
        ('FEI300%',)).fetchall()]
    assert any('idx_universal_source_identifier_lookup' in text for text in plans),plans
    assert search(conn,q='FEI%')['total']==0,'User wildcard must not enumerate other IDs'
    conn.close()


def test_private_universal_api_accepts_combined_source_industry_country_filters(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from facilityrisk.app import app
    from facilityrisk.db import connect,initialize
    db_file=tmp_path/'combined-filters.sqlite'
    monkeypatch.setenv('FACILITY_RISK_DB',str(db_file))
    with connect(db_file) as c:
        initialize(c)
        import_records(c,'EPA_FRS',[
            {'id':'110000099991','name':'General Warehouse','country':'US','industry':'493110'},
            {'id':'110000099992','name':'General Hospital','country':'US','industry':'622110'}
        ],'https://www.epa.gov/frs')
        import_records(c,'OVERTURE',[
            {'id':'place999','name':'General Warehouse','country':'CA','industry':'493110'}
        ],'https://docs.overturemaps.org/')
    with TestClient(app) as client:
        found=client.get('/api/universal-facilities',params={
          'q':'General','country':'US','industry':'493110','source':'EPA_FRS',
          'limit':'25'})
        assert found.status_code==200,found.text
        response=found.json()
        assert response['total']==1
        assert response['items'][0]['name']=='General Warehouse'
        assert response['items'][0]['coordinate_quality']=='unassessed'
        assert response['items'][0]['site_status']=='source_observation'
        data=client.get('/api/universal-facilities/'+response['items'][0]['id'])
        assert data.status_code==200
        assert data.json()['insured_coverage_status']=='unknown'
        assert data.json()['risk_status']=='unassessed'
        zero=client.get('/api/universal-facilities',params={
          'q':'General','country':'CA','source':'EPA_FRS'})
        assert zero.status_code==200 and zero.json()['total']==0
        assert client.get('/api/universal-facilities?industry=Retail').json()['total']==0



def test_national_numeric_identifier_prefix_uses_source_btree_not_site_scan():
    c=db()
    import_records(c,'EPA_FRS',[
      {'id':'110000300001','name':'Industrial Refinery','country':'US','industry':'324110'},
      {'id':'110000300002','name':'Municipal Water Works','country':'CA','industry':'221310'},
      {'id':'110000309999','name':'Warehouse Depot','country':'US','industry':'493110'},
      {'id':'120000300000','name':'Hospital Annex','country':'US','industry':'622110'},
    ],'https://www.epa.gov/frs')
    assert search(c,q='11000030',source='EPA_FRS')['total']==3
    assert search(c,q='110000300001')['total']==1
    assert search(c,q='11000030',country='CA')['total']==1
    assert search(c,q='11000030',industry='493110')['total']==1
    assert search(c,q='120000300000',country='CA')['total']==0
    assert search(c,q='999999000000')['total']==0
    plan=[r[3] for r in c.execute('EXPLAIN QUERY PLAN SELECT ir.site_id '
      'FROM universal_source_records AS ir INDEXED BY '
      'idx_universal_source_identifier_lookup WHERE ir.source_identifier LIKE ?',
      ('11000030%',))]
    assert any('SEARCH ir USING INDEX idx_universal_source_identifier_lookup' in x
               for x in plan),plan
    c.close()
