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
    assert 'src="./web/workbench-ui.js"' in html
    assert html.index('src="./web/workbench-ui.js"') < html.index('src="./web/app.js"')
    assert 'data-page="workbench"' in html
    assert 'data-page="workbench"' in (ROOT/'web'/'index.html').read_text()
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


def test_pages_and_records_have_shareable_history_routes_without_exposing_forms():
    public=(ROOT/'index.html').read_text()
    private=(ROOT/'web'/'index.html').read_text()
    app=(ROOT/'web'/'app.js').read_text()
    registry=(ROOT/'web'/'registry-ui.js').read_text()
    universal=(ROOT/'web'/'universal-ui.js').read_text()
    for html in (public,private):
        assert 'id="copy-view-link"' in html
        assert '<a class="nav-item' in html
        assert 'href="?page=feeds"' in html
        assert 'href="?page=registry"' in html
        assert 'href="?page=facilities"' in html
    assert "window.addEventListener('popstate',restoreLocation)" in app
    assert "window.history.pushState" in app
    assert "window.history[method==='replace'?'replaceState':'pushState']" in app
    assert 'window.FacilityRiskRouter=Object.freeze' in app
    assert 'navigator.clipboard.writeText(window.location.href)' in app
    assert 'routeableFacility(id)' in app
    assert 'routeableFacility(state.facility)' in app
    assert 'openSite(route.facility,{fromRoute:true,tab:route.tab})' in app
    assert 'window.RegistryUI={render:' in registry and 'mount,restoreRoute,routeParams,pages' in registry
    assert 'window.UniversalUI={render,mount,restoreRoute,routeParams}' in universal
    # Private assessment/policy values are never placed in browser URL parameters.
    route_keys=app.split('const ROUTE_KEYS=new Set(',1)[1].split(');',1)[0]
    assert 'coverage' not in route_keys and 'daily' not in route_keys
    assert 'sourceIdentity' not in route_keys and 'policy' not in route_keys


def test_cross_industry_evidence_context_is_source_specific_and_not_claims():
    page = (ROOT/'index.html').read_text()
    private = (ROOT/'web'/'index.html').read_text()
    script = (ROOT/'web'/'source-insights.js').read_text()
    css = (ROOT/'web'/'source-insights.css').read_text()
    wb = (ROOT/'web'/'workbench-ui.js').read_text()
    insurance = (ROOT/'web'/'insurance-ui.js').read_text()
    app = (ROOT/'web'/'app.js').read_text()
    manifest = json.loads((ROOT/'web'/'coordination'/'parallel-ingestion.json').read_text())
    rows = [s for lane in manifest['lanes'] for s in lane['sources']]
    assert len(manifest['lanes']) == 4 and len(rows) >= 20
    assert all(s['deployed'] == 0 and s['verified_insured_sites'] == 0 for s in rows)
    assert all(s['run_url'].startswith('https://github.com/') for s in rows)
    for html in (page, private):
        assert 'source-insights.js' in html and 'source-insights.css' in html
        assert html.index('source-insights.js') < html.index('app.js')
    for page_name in ('workbench','insurance','universal','registry','facilities',
                      'cases','map','identity','underwriting','evidence',
                      'disclosures','methodology'):
        assert page_name + ':' in script or "'" + page_name + "':" in script
    for key in ('fema_nfhl','usfs_whp_aggregates','epa_echo','epa_rcra',
                'epa_tri','uscg_nrc','csb','eia861','pnnl_outages','odin_county'):
        assert key + ':' in script or "'" + key + "':" in script
    assert 'No new-source site match approved' in script
    assert 'site-specific pixel' in script.lower() or 'site-specific' in script.lower()
    assert "if(page==='feeds'||!element)return" in script
    assert "window.SourceInsights?.mount(state.page,ROOT)" in app
    assert 'si-inventory-search' in script and 'si-inventory-family' in script
    assert '.si-inventory-row[hidden]{display:none}' in css
    assert 'source_research_tasks:researchTasks()' in wb
    assert "site_evidence_status:'not_verified'" in wb
    assert 'linkedEvidence(x.id)' in insurance
    # Source links are research references; assessment/policy/site values are NOT serialized.
    assert 'policy' not in script.split("function sourceLink(id,label)",1)[1].split('function statline',1)[0].lower()


def test_full_national_wildfire_raster_has_distinct_source_grain_and_coverage_context():
    app=(ROOT/'web'/'source-insights.js').read_text()
    workbench=(ROOT/'web'/'workbench-ui.js').read_text()
    insurance=(ROOT/'web'/'insurance-ui.js').read_text()
    assert 'usfs_whp2023_six_national_tiffs:' in app
    assert '133,505,015 valid landscape cells in each product' in app
    assert 'CI staged only, not insured sites' in app
    assert "'usfs_whp2023_six_national_tiffs'" in workbench
    assert "'usfs_whp2023_six_national_tiffs'" in insurance
    manifest=json.loads((ROOT/'web'/'coordination'/'parallel-ingestion.json').read_text())
    for source in (s for l in manifest['lanes'] for s in l['sources']):
        if source['id']=='usfs_whp2023_six_national_tiffs':
            assert source['accepted']==source['indexed_ci']==6
            assert source['deployed']==source['verified_insured_sites']==0
            assert source['source_sha256']=='7f10f1f8dd97551b8be1458fe0ec924df60b2cea7ece2d1af4c3c1166d1895ab'
