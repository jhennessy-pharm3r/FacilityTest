"""Regression gates for new research sources and geo-candidate quarantine."""
import csv
import pytest
from facilityrisk.db import connect, initialize
from facilityrisk.intelligence import review_location
from facilityrisk.source_extensions import (SOURCES, catalog, probe_extensions,
                                            import_geo_csv, review_event_candidate)


@pytest.fixture
def db(tmp_path):
    conn = connect(tmp_path / 'sources.sqlite')
    initialize(conn)
    conn.execute("""INSERT INTO facilities
        (id,name,country,latitude,longitude,origin,last_imported)
        VALUES ('site-reviewed','Reviewed site','United States',35.834,-82.002,'fixture','2026-10-21')""")
    conn.execute("""INSERT INTO facilities
        (id,name,country,latitude,longitude,origin,last_imported)
        VALUES ('site-unreviewed','Unreviewed site','United States',35.835,-82.002,'fixture','2026-10-21')""")
    conn.commit()
    yield conn
    conn.close()


def _csv(path, rows):
    with path.open('w', encoding='utf-8', newline='') as file:
        w = csv.DictWriter(file, fieldnames=['event_id','latitude','longitude','date','summary','url','precision'])
        w.writeheader()
        w.writerows(rows)


def test_catalog_has_complete_source_scope_and_never_claims_ingestion(db):
    rows = catalog(db)
    assert len(rows) == len(SOURCES) == 15
    assert all(r['probe_state'] == 'not_tested' and r['staged_candidates'] == 0 for r in rows)
    assert all(r['documentation'].startswith('https://') for r in rows)


def test_source_probe_html_is_only_documentation_reachable(db):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'paths': {'/api/LicenceProfile': {}}}
    class Session:
        def get(self, url, **kwargs): return Response()
    rows = probe_extensions(db, Session())
    assert len(rows) == 15
    assert {r['state'] for r in rows} == {'docs_reachable','schema_reachable'}
    assert all(r['state'] not in ('validated','ingested') for r in rows)


def test_incident_import_needs_reviewed_site_point_and_is_not_evidence(db, tmp_path):
    path = tmp_path / 'incidents.csv'
    _csv(path, [{'event_id':'event-1','latitude':35.835,'longitude':-82.002,
                 'date':'2024-01-01','summary':'Nearby transport incident',
                 'url':'https://example.org/event-1','precision':'city'},
                {'event_id':'event-2','latitude':0,'longitude':0,
                 'date':'2024-01-02','summary':'Distant event','url':'','precision':'city'}])
    opts = dict(id_column='event_id', date_column='date', title_column='summary',
                url_column='url', precision_column='precision', radius_km=10)
    with pytest.raises(ValueError, match='independently reviewed'):
        import_geo_csv(db, path, 'phmsa', **opts)
    review_location(db,'site-reviewed','site_verified','https://example.org/reviewed-site-point',
                    'QA reviewer','Verified physical site point with source record')
    out = import_geo_csv(db, path, 'phmsa', **opts)
    assert out['rows_seen'] == 2 and out['new_candidates'] == 1
    assert db.execute('SELECT COUNT(*) FROM evidence').fetchone()[0] == 0
    assert db.execute('SELECT COUNT(*) FROM external_event_candidates').fetchone()[0] == 1
    assert import_geo_csv(db, path, 'phmsa', **opts)['new_candidates'] == 0
    assert db.execute("SELECT status FROM external_event_candidates").fetchone()[0] == 'pending'


def test_candidate_review_requires_evidence_and_does_not_create_evidence(db, tmp_path):
    path = tmp_path / 'events.csv'
    _csv(path, [{'event_id':'event-1','latitude':35.835,'longitude':-82.002,
                 'date':'2024-01-01','summary':'Nearby incident',
                 'url':'https://example.org/event-1','precision':'exact'}])
    review_location(db,'site-reviewed','site_verified','https://example.org/reviewed-site-point',
                    'QA reviewer','Verified physical site point with source record')
    import_geo_csv(db,path,'nrc',id_column='event_id',date_column='date',
                   title_column='summary',url_column='url',precision_column='precision')
    cid=db.execute('SELECT id FROM external_event_candidates').fetchone()[0]
    with pytest.raises(ValueError, match='HTTPS'):
        review_event_candidate(db,cid,'reviewed_relevant','Reviewer','http://bad.test','Detailed note to approve')
    r=review_event_candidate(db,cid,'reviewed_relevant','Reviewer',
                             'https://example.org/corroboration','Corroborated regional context only')
    assert r['status']=='reviewed_relevant'
    assert db.execute('SELECT COUNT(*) FROM evidence').fetchone()[0] == 0


def test_csv_rejects_unknown_schema_and_nonincident_sources(db,tmp_path):
    path=tmp_path/'empty.csv'
    path.write_text('record,position\n1,2\n',encoding='utf-8')
    with pytest.raises(ValueError,match='no incident-level CSV'):
        import_geo_csv(db,path,'eia861')
    review_location(db,'site-reviewed','site_verified','https://example.org/reviewed-site-point',
                    'QA reviewer','Verified physical site point with source record')
    with pytest.raises(ValueError,match='missing required columns'):
        import_geo_csv(db,path,'nrc')


def test_spatial_grid_handles_antimeridian_and_near_poles(db,tmp_path):
    """Conservative prefilter cannot silently lose valid 25-50 km candidates."""
    for fid,lat,lon in [('site-dateline',0.0,179.95),
                        ('site-polar',89.9,20.0),
                        ('site-remote',-49.0,65.0)]:
        db.execute("""INSERT INTO facilities
          (id,name,country,latitude,longitude,origin,last_imported)
          VALUES (?,?,?,?,?,?,?)""",(fid,fid,'Global synthetic fixture',lat,lon,
                                    'fixture','2026-10-21'))
    db.commit()
    for fid in ('site-dateline','site-polar','site-remote'):
        review_location(db,fid,'site_verified','https://example.org/physical-site-point',
                        'Point reviewer','Verified precise synthetic property point')
    path=tmp_path/'cross_global_incidents.csv'
    _csv(path,[
      {'event_id':'E-DATELINE','latitude':0.0,'longitude':-179.95,
       'date':'2024-01-01','summary':'Release across the international date line',
       'url':'https://example.org/event-date-line','precision':'precise'},
      {'event_id':'E-POLE','latitude':89.9,'longitude':-160.0,
       'date':'2024-01-02','summary':'Near-polar high longitude separation',
       'url':'https://example.org/event-pole','precision':'precise'},
      {'event_id':'E-OUTSIDE','latitude':10,'longitude':10,
       'date':'2024-01-03','summary':'Distant incident',
       'url':'https://example.org/event-elsewhere','precision':'precise'}])
    output=import_geo_csv(db,path,'phmsa',id_column='event_id',
               date_column='date',title_column='summary',url_column='url',
               precision_column='precision',radius_km=50)
    assert output['new_candidates']==2
    assert output['outside_radius']==1
    assert output['geographic_distance_checks']<=3
    assert output['spatial_prefilter']=='one_degree_grid_then_haversine'
    rows=db.execute('SELECT facility_id,source_record_id,status FROM external_event_candidates').fetchall()
    matched={(x['facility_id'],x['source_record_id']) for x in rows}
    assert matched=={('site-dateline','E-DATELINE'),('site-polar','E-POLE')}
    assert all(x['status']=='pending' for x in rows)
    assert db.execute('SELECT COUNT(*) FROM evidence').fetchone()[0]==0


def test_spatial_prefilter_avoids_all_sites_times_events_scan(db,tmp_path):
    for i in range(240):
        lat=-80.0+(i%160)
        lon=-170.0+((i*17)%340)
        db.execute("""INSERT INTO facilities
          (id,name,country,latitude,longitude,origin,last_imported)
          VALUES(?,?,?,?,?,?,?)""",(f'grid-{i}',f'Site {i}','Synthetic',lat,lon,
                                   'fixture','2026-10-21'))
    db.commit()
    for i in range(240):
        review_location(db,f'grid-{i}','site_verified',
                        'https://example.org/site-geocodes','QA reviewer',
                        'Independently checked synthetic site point')
    db.execute("""INSERT INTO facilities
      (id,name,country,latitude,longitude,origin,last_imported)
      VALUES('grid-target','Target','Synthetic',40,-70,'fixture','2026-10-21')""")
    db.commit()
    review_location(db,'grid-target','site_verified','https://example.org/target-location',
                    'QA reviewer','Verified exact target point')
    file=tmp_path/'grid-sample.csv'
    _csv(file,[{'event_id':'ONLY-NEARBY','latitude':40.01,'longitude':-70.01,
        'date':'2025-06-01','summary':'Source report near target',
        'url':'https://example.org/event','precision':'site'}])
    result=import_geo_csv(db,file,'nrc',id_column='event_id',
                          date_column='date',title_column='summary',url_column='url',
                          radius_km=10)
    assert result['verified_sites_tested']==241
    assert result['candidates_nearby']>=1
    assert result['geographic_distance_checks']<30
    assert result['geographic_distance_checks']<result['verified_sites_tested']
    assert db.execute('SELECT COUNT(*) FROM evidence').fetchone()[0]==0
