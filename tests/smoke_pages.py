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
    page.locator('[data-page="feeds"]').first.click()
    expect(page.locator('#intel-content')).to_contain_text('EPA ECHO',timeout=15000)
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