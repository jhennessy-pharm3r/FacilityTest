"""Regression gates for new research sources and geo-candidate quarantine."""
import csv
import pytest
from facilityrisk.db import connect, initialize
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
    assert len(rows) == len(SOURCES) == 14
    assert all(r['probe_state'] == 'not_tested' and r['staged_candidates'] == 0 for r in rows)
    assert all(r['documentation'].startswith('https://') for r in rows)


def test_source_probe_html_is_only_documentation_reachable(db):
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'paths': {'/api/LicenceProfile': {}}}
    class Session:
        def get(self, url, **kwargs): return Response()
    rows = probe_extensions(db, Session())
    assert len(rows) == 14
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
    db.execute("""INSERT INTO location_reviews(facility_id,precision,reviewer,verified_at)
                  VALUES ('site-reviewed','site_verified','QA','2026-10-21')""")
    db.commit()
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
    db.execute("""INSERT INTO location_reviews(facility_id,precision,reviewer,verified_at)
                  VALUES ('site-reviewed','site_verified','QA','2026-10-21')""")
    db.commit()
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
    db.execute("""INSERT INTO location_reviews(facility_id,precision,reviewer,verified_at)
                  VALUES ('site-reviewed','site_verified','QA','2026-10-21')""")
    db.commit()
    with pytest.raises(ValueError,match='missing required columns'):
        import_geo_csv(db,path,'nrc')
