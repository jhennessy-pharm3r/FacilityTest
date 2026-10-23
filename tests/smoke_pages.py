"""Public GitHub Pages browser smoke check; runs on GitHub CI only.

Uses only public demo fixtures, never the analyst workbook or insured data.
"""
from playwright.sync_api import sync_playwright,expect
import json
import sys
import shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from facilityrisk.registry_catalog import FIELDS,make_catalog,normalize_device

BASE='http://127.0.0.1:8099/'

with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,args=['--no-sandbox'],executable_path=shutil.which('chromium'))
    page=browser.new_page(viewport={'width':1480,'height':950},device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    # Synthetic FDA registry response validates unrestricted catalog search,
    # separate from the three public research case studies.
    sample=make_catalog([
        normalize_device({'registration':{'name':'Acme Devices Galway','fei_number':'3000000011',
            'city':'Galway','iso_country_code':'IE','address_line_1':'14 Research St',
            'owner_operator':{'firm_name':'Acme Global'}},'establishment_type':['Manufacture Medical Device']}),
        normalize_device({'registration':{'name':'Acme Devices Boston','fei_number':'3000000012',
            'city':'Boston','iso_country_code':'US','address_line_1':'15 Research St',
            'owner_operator':{'firm_name':'Acme Global'}},'establishment_type':['Manufacture Medical Device']})
    ],{'fda_device':{'status':'imported'},'fda_drug':{'status':'not_requested'}})
    page.route('**/registry/catalog.json',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps(sample)))
    page.on('dialog',lambda dialog:dialog.accept())
    page.goto(BASE,wait_until='domcontentloaded',timeout=45000)
    # Insurance-first entry point works for ANY manually named facility without
    # claiming registered-site, geohazard or confirmed policy coverage.
    expect(page.locator('#view-root h1')).to_contain_text('Facility exposure & coverage workbench',timeout=15000)
    page.locator('[data-wb-field="facility"]').fill('Example Public Logistics Hub')
    page.locator('[data-wb-field="industry"]').fill('Transport and warehousing')
    page.locator('[data-wb-field="location"]').fill('New Brunswick, Canada')
    page.locator('[data-wb-kind="perils"][value="flood"]').check()
    page.locator('[data-wb-kind="deps"][value="power"]').check()
    page.locator('[data-wb-kind="deps"][value="supplier"]').check()
    expect(page.locator('#wb-coverage-review')).to_contain_text('Parametric flood')
    expect(page.locator('#wb-coverage-review')).to_contain_text('Contingent BI')
    expect(page.locator('#wb-coverage-review')).to_contain_text('Utility service interruption')
    page.locator('#wb-coverage-flood').select_option('excluded')
    expect(page.locator('#wb-summary')).to_contain_text('1',timeout=15000)
    page.locator('[data-wb-field="days"]').fill('5')
    page.locator('[data-wb-field="daily"]').fill('15000')
    expect(page.locator('#wb-summary')).to_contain_text('$75,000',timeout=15000)
    assessment=page.evaluate('window.WorkbenchUI.assessment()')
    assert assessment['facility']['name']=='Example Public Logistics Hub'
    assert assessment['financial_illustration']['gross_downtime_illustration_usd']==75000
    assert len(assessment['potential_coverages'])>=5
    assert all(x['verified_coverage']=='unknown' for x in assessment['potential_coverages'])
    with page.expect_download() as transfer:
        page.locator('#wb-export').click()
    download=transfer.value
    path=download.path()
    report=json.loads(Path(path).read_text(encoding='utf-8'))
    assert report['facility']['industry']=='Transport and warehousing'
    assert report['financial_illustration']['gross_downtime_illustration_usd']==75000
    assert any(x['id']=='flood' and x['user_reported_status']=='excluded' and x['verified_coverage']=='unknown'
               for x in report['potential_coverages'])
    page.locator('[data-page="insurance"]').first.click()
    expect(page.locator('#view-root')).to_contain_text('Parametric flood',timeout=15000)
    page.locator('[data-page="workbench"]').first.click()
    expect(page.locator('[data-wb-field="facility"]')).to_have_value('Example Public Logistics Hub')
    page.locator('#wb-reset').click()
    expect(page.locator('[data-wb-field="facility"]')).to_have_value('')
    page.locator('[data-page="universal"]').first.click()
    expect(page.locator('#view-root')).to_contain_text('Universal facility discovery')
    expect(page.locator('#view-root')).to_contain_text('private backend')
    page.locator('[data-page="registry"]').first.click()
    expect(page.locator('#view-root h1')).to_contain_text('All registered facilities',timeout=15000)
    # The real Ireland/Canada catalogs are also loaded. Initial results are
    # paginated; synthetic records need not be in the first 35 entries.
    expect(page.locator('#registry-status')).to_contain_text('source identities',timeout=35000)
    expect(page.locator('[data-reg-id]').first).to_contain_text('Acme Devices Boston',timeout=15000)
    page.locator('#registry-query').fill('Acme Devices Galway')
    page.locator('#registry-search-button').click()
    expect(page.locator('#registry-results')).to_contain_text('Acme Devices Galway',timeout=15000)
    expect(page.locator('#registry-results')).not_to_contain_text('Acme Devices Boston')
    page.locator('#registry-source').select_option('Canada NPRI')
    page.locator('#registry-search-button').click()
    expect(page.locator('#registry-results')).not_to_contain_text('Acme Devices Galway',timeout=15000)
    page.locator('#registry-source').select_option('FDA device registration / listing')
    page.locator('#registry-search-button').click()
    expect(page.locator('#registry-results')).to_contain_text('Acme Devices Galway',timeout=15000)
    page.locator('[data-reg-id]').first.click()
    expect(page.locator('#registry-detail-container')).to_contain_text('Not assessed')
    page.locator('#registry-assess').click()
    expect(page.locator('#view-root h1')).to_contain_text('Facility exposure & coverage workbench')
    expect(page.locator('[data-wb-field="facility"]')).to_have_value('Acme Devices Galway')
    source_observation=page.evaluate('window.WorkbenchUI.assessment().source_observation')
    assert source_observation['physical_property_verified'] is False
    assert source_observation['source']
    assert page.evaluate('window.WorkbenchUI.assessment().scenarios.length')==0
    page.locator('[data-page="registry"]').first.click()
    page.locator('[data-reg-id]').first.click()
    page.locator('#registry-track').click()
    page.locator('[data-page="facilities"]').first.click()
    expect(page.locator('#facility-cards')).to_contain_text('Acme Devices Galway',timeout=15000)
    page.locator('[data-page="cases"]').first.click()
    expect(page.locator('#intel-content')).to_contain_text('Pfizer Rocky Mount',timeout=15000)
    expect(page.locator('#intel-content')).to_contain_text('Amgen Juncos',timeout=15000)
    page.locator('[data-page="identity"]').first.click()
    expect(page.locator('#intel-content')).to_contain_text('Verified FRS crosswalks',timeout=15000)
    page.locator('[data-page="map"]').first.click()
    expect(page.locator('#intel-map-canvas')).to_be_visible(timeout=15000)
    page.locator('[data-page="underwriting"]').first.click()
    expect(page.locator('#intel-content')).to_contain_text('Business interruption',timeout=15000)
    page.locator('[data-page="insurance"]').first.click()
    expect(page.locator('#view-root')).to_contain_text('Insurance coverage & alternative options',timeout=15000)
    expect(page.locator('#view-root')).to_contain_text('Parametric flood',timeout=15000)
    expect(page.locator('#view-root')).to_contain_text('Coverage unknown',timeout=15000)
    page.locator('[data-page="feeds"]').first.click()
    expect(page.locator('#intel-content')).to_contain_text('EPA ECHO',timeout=15000)
    expect(page.locator('#intel-content')).to_contain_text('Actual published data ingestion',timeout=15000)
    expect(page.locator('#intel-content')).to_contain_text('USCG National Response Center',timeout=15000)
    # Parallel worker lanes expose official source staging, never production facility matches.
    expect(page.locator('#intel-content')).to_contain_text('Parallel-source ingestion progress',timeout=15000)
    expect(page.locator('#intel-content')).to_contain_text('App deployed',timeout=15000)
    ledger_path=Path(__file__).resolve().parents[1]/'web/coordination/parallel-ingestion.json'
    progress=json.loads(ledger_path.read_text(encoding='utf-8'))
    assert progress['review_status']=='verified_source_qa_not_deployed'
    records=[source for lane in progress['lanes'] for source in lane['sources']]
    assert all(row['deployed']==0 for row in records)
    for source_id in ('epa_echo','epa_rcra','uscg_nrc','eia861','fema_nfhl'):
        item=next(row for row in records if row['id']==source_id)
        expect(page.locator('#intel-content')).to_contain_text(item['name'],timeout=15000)
        expect(page.locator('#intel-content')).to_contain_text(f"{item['accepted']:,}",timeout=15000)
    expect(page.locator('#intel-content')).to_contain_text('Official access blocked',timeout=15000)
    expect(page.locator('#intel-content')).to_contain_text('not a deployed facility-risk dataset',timeout=15000)
    # Filters must operate on the real reviewed 20-source progress ledger.
    expect(page.locator('.parallel-source-row:visible')).to_have_count(len(records),timeout=15000)
    page.locator('#parallel-lane-filter').select_option('C')
    expect(page.locator('.parallel-source-row:visible')).to_have_count(len(progress['lanes'][2]['sources']))
    expect(page.locator('#parallel-visible-count')).to_contain_text('4 of 20 source streams')
    page.locator('#parallel-stage-filter').select_option('access_blocked')
    expect(page.locator('.parallel-source-row:visible')).to_have_count(1)
    expect(page.locator('#parallel-visible-count')).to_contain_text('1 of 20 source streams')
    page.locator('#parallel-lane-filter').select_option('')
    expect(page.locator('.parallel-source-row:visible')).to_have_count(2)
    page.locator('#parallel-stage-filter').select_option('')
    expect(page.locator('.parallel-source-row:visible')).to_have_count(len(records))


    # Use the actual committed NOAA summary, never a fixed or guessed row count.
    noaa_status=Path(__file__).resolve().parents[1]/'web/ingestion/noaa-storm-events.json'
    if noaa_status.exists():
        noaa=json.loads(noaa_status.read_text(encoding='utf-8'))
        assert noaa['state']=='staged_source_artifact' and noaa['records']>0
        expect(page.locator('#intel-content')).to_contain_text(
            f"{noaa['records']:,}",timeout=15000)
        expect(page.locator('#intel-content')).to_contain_text(
            'NOAA Storm Events Details',timeout=15000)
        expect(page.locator('#intel-content')).to_contain_text(
            'staged source artifact',timeout=15000)
    # Dynamic current official NOAA selected spill-response source count.
    selected_path=Path(__file__).resolve().parents[1]/'web/ingestion/noaa-incidentnews.json'
    if selected_path.exists():
        selected=json.loads(selected_path.read_text(encoding='utf-8'))
        assert selected['source']=='NOAA IncidentNews Selected Spills'
        assert selected['state']=='staged_source_artifact'
        assert selected['records']>0 and selected['coordinate_records']<=selected['records']
        assert sum(selected['threat_counts'].values())==selected['records']
        expect(page.locator('#intel-content')).to_contain_text(
            'NOAA IncidentNews Selected Spills',timeout=15000)
        expect(page.locator('#intel-content')).to_contain_text(
            f"{selected['records']:,}",timeout=15000)
        expect(page.locator('#intel-content')).to_contain_text(
            'not all reported spills',timeout=15000)
    page.locator('[data-page="facilities"]').first.click()
    page.locator('.facility-card').first.click()
    expect(page.locator('#detail-drawer')).to_have_class('detail-drawer open',timeout=15000)
    page.locator('[data-tab="risk"]').first.click()
    expect(page.locator('.drawer-body')).to_contain_text('Site and identity checks',timeout=15000)
    page.locator('#drawer-close').click()
    page.locator('[data-page="overview"]').first.click()
    # Test the real committed public catalog in addition to the synthetic fixture.
    public_catalog=json.loads((Path(__file__).resolve().parents[1]/'web/registry/catalog.json').read_text(encoding='utf-8'))
    if len(public_catalog.get('rows',[]))>1000:
        page.unroute('**/registry/catalog.json')
        page.goto(BASE,wait_until='domcontentloaded',timeout=45000)
        page.locator('[data-page="registry"]').first.click()
        expected_count=len(public_catalog['rows'])
        for source_file in ('ireland-leap.json','canada-npri.json'):
            extra=Path(__file__).resolve().parents[1]/'web/registry'/source_file
            if extra.is_file():
                companion=json.loads(extra.read_text(encoding='utf-8'))
                assert companion['schema_version']=='1.0' and companion['fields']==public_catalog['fields']
                expected_count+=len(companion['rows'])
        expect(page.locator('#registry-status')).to_contain_text(
            f'{expected_count:,} separate regulatory source identities',timeout=45000)
        assert page.locator('[data-reg-id]').count()==35, 'Expected paginated all-facilities browsing'
        example=next(dict(zip(public_catalog['fields'],r)) for r in public_catalog['rows'] if r[6] and len(r[6])>=7)
        page.locator('#registry-query').fill(example['fei'])
        page.locator('#registry-search-button').click()
        expect(page.locator('#registry-results')).to_contain_text(example['name'],timeout=35000)
        print('Real cross-source catalog browser checked:',expected_count,'distinct regulatory identities')
    page.screenshot(path='/tmp/facility-public-browser-smoke.png',full_page=True)
    assert not errors, 'JavaScript runtime exceptions: '+'; '.join(errors)
    print('Public preview browser routes and facility underwriting drawer passed.')
    browser.close()