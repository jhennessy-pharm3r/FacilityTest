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
    assert 'src="./web/intelligence-ui.js"' in html
    assert 'src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"' in html
    assert html.index('src="./web/intelligence-ui.js"') < html.index('src="./web/app.js"')
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


def test_case_timelines_are_primary_sourced_and_no_false_forecasting():
    source=json.loads((ROOT/'web'/'case-studies.json').read_text())
    assert len(source['cases'])==3
    assert sum(len(c['milestones']) for c in source['cases'])==12
    assert all(c['pre_event_evidence_status'] for c in source['cases'])
    assert all(m['timing']!='pre_event' for c in source['cases'] for m in c['milestones'])
    assert all(m['source_url'].startswith('https://') for c in source['cases'] for m in c['milestones'])
    assert 'src="/assets/intelligence-ui.js"' in (ROOT/'web'/'index.html').read_text()
    app=(ROOT/'web'/'app.js').read_text()
    assert 'window.IntelligenceUI.mount' in app
    assert "if(state.tab==='risk')" in app


def test_public_website_never_includes_private_workbook():
    # Track only allowlisted public JSON on GitHub Pages.
    for target in (ROOT/'web'/'public-demo.json',ROOT/'web'/'case-studies.json'):
        text=target.read_text()
        assert 'FACILITY_RISK_AUTH_TOKEN' not in text
        assert 'private_local_browser_import' not in text
    assert (ROOT/'.github/workflows/ci.yml').exists()
    assert (ROOT/'.github/workflows/source-probe.yml').exists()


def test_private_review_queue_is_not_exposed_in_public_navigation():
    private=(ROOT/'web'/'index.html').read_text()
    public=(ROOT/'index.html').read_text()
    appjs=(ROOT/'web'/'app.js').read_text()
    assert 'data-page="reviews"' in private
    assert 'data-page="reviews"' not in public
    assert 'data-review-action' in appjs
    assert '/api/review-approvals/' in appjs
    assert 'Shared service tokens cannot approve' in appjs
