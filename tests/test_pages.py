"""Static-public preview safety checks and private research export format."""
from __future__ import annotations
import json
from pathlib import Path
from facilityrisk.browser_export import export_browser_snapshot
from facilityrisk.db import connect, initialize

ROOT = Path(__file__).resolve().parents[1]


def test_public_demo_is_primary_source_only():
    data = json.loads((ROOT/'web'/'public-demo.json').read_text())
    assert data['schema_version'] == '1.0'
    assert data['dataset_mode'] == 'public_demo'
    assert len(data['facilities']) == 3
    assert len(data['evidence']) >= 9
    assert all(x['origin'] == 'public_demo_primary_source' for x in data['evidence'])
    assert all(x['source_url'].startswith('https://') for x in data['evidence'])
    ids = {x['id'] for x in data['facilities']}
    assert all(x['facility_id'] in ids for x in data['evidence'])
    assert all('City reference' in f['coordinate_precision'] for f in data['facilities'])
    assert all(x['fei'] is None for x in data['facilities'])


def test_public_entry_uses_relative_urls_and_banner():
    html=(ROOT/'index.html').read_text()
    assert 'href="./web/styles.css"' in html
    assert 'src="./web/public-api.js"' in html
    assert 'src="./web/app.js"' in html
    assert 'PUBLIC RESEARCH PREVIEW' in html
    assert 'public-data-file' in html
    assert '/assets/' not in html
    assert not (ROOT/'data'/'my-private-facility-snapshot.json').exists()


def test_browser_export_does_not_require_network(tmp_path):
    path=tmp_path/'example.sqlite'
    with connect(path) as conn:
        initialize(conn)
        conn.execute("INSERT INTO facilities(id,name,origin,last_imported) VALUES ('site-1','Test Site','unit','2026-10-21')")
        conn.execute("INSERT INTO evidence(id,facility_id,source,risk_domain,origin,last_imported) VALUES ('ev-1','site-1','SEC EDGAR','Operational','unit','2026-10-21')")
        conn.commit()
        result=export_browser_snapshot(conn,tmp_path/'private.json')
    d=json.loads((tmp_path/'private.json').read_text())
    assert result['evidence']==1
    assert d['dataset_mode']=='private_local_browser_import'
    assert d['facilities'][0]['id']=='site-1'
    assert d['evidence'][0]['facility_id']=='site-1'
    assert 'private' in ' '.join(d['important_caveats']).lower()