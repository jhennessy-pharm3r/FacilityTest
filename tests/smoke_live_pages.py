"""Verify the *deployed* public GitHub Pages UI after GitHub Pages publishes.

This test never reads private snapshots or insurer data. It loads the actual
public URL, checks functional interactions, collects client-side exceptions
and captures desktop/mobile screenshots. The localhost smoke remains separate.
"""
from __future__ import annotations
import json
from datetime import datetime,timezone
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

URL='https://jhennessy-pharm3r.github.io/FacilityTest/'
TARGET=Path('/tmp/facility-live-audit')
TARGET.mkdir(parents=True,exist_ok=True)

def audit():
    report={'site':URL,'checked_at_utc':datetime.now(timezone.utc).isoformat(),
            'checks':{},'js_exceptions':[],'unexpected_private_api_calls':[]}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':900},
                                    device_scale_factor=1,accept_downloads=True)
        page=context.new_page()
        page.on('pageerror',lambda error:report['js_exceptions'].append(str(error)))
        page.on('request',lambda request:report['unexpected_private_api_calls'].append(request.url)
                if '/FacilityTest/api/' in request.url or request.url.startswith('https://jhennessy-pharm3r.github.io/api/')
                else None)
        response=page.goto(URL,wait_until='domcontentloaded',timeout=90000)
        assert response and response.status==200, 'Published home request failed'
        expect(page.locator('#view-root h1')).to_contain_text(
            'Facility exposure & coverage workbench',timeout=90000)
        assert page.evaluate('Boolean(window.WorkbenchUI&&window.PublicRiskAPI)')
        report['checks']['published_workbench']='passed'
        expect(page.locator('.public-preview-banner')).to_contain_text('PUBLIC RESEARCH PREVIEW')
        report['checks']['public_scope_label']='passed'
        page.locator('[data-wb-field="facility"]').fill('Public Demo Office Complex')
        page.locator('[data-wb-field="industry"]').fill('Commercial offices')
        page.locator('[data-wb-kind="perils"][value="flood"]').check(force=True)
        page.locator('[data-wb-kind="deps"][value="power"]').check(force=True)
        expect(page.locator('#wb-coverage-review')).to_contain_text('Parametric flood')
        expect(page.locator('#wb-coverage-review')).to_contain_text('Utility service interruption')
        page.locator('[data-wb-field="days"]').fill('4')
        page.locator('[data-wb-field="daily"]').fill('2500')
        expect(page.locator('#wb-summary')).to_contain_text('$10,000')
        obj=page.evaluate('window.WorkbenchUI.assessment()')
        assert obj['financial_illustration']['gross_downtime_illustration_usd']==10000
        assert all(c['verified_coverage']=='unknown' for c in obj['potential_coverages'])
        report['checks']['cross_industry_insurance_review']='passed'
        page.screenshot(path=str(TARGET/'workbench-desktop.png'),full_page=True)
        page.locator('[data-page="insurance"]').first.click()
        expect(page.locator('#view-root h1')).to_contain_text('Insurance coverage & alternative options')
        expect(page.locator('#view-root')).to_contain_text('Parametric utility outage')
        page.screenshot(path=str(TARGET/'coverage-reference.png'),full_page=True)
        report['checks']['insurance_reference']='passed'
        page.locator('[data-page="registry"]').first.click()
        expect(page.locator('#registry-status')).to_contain_text('source identities',timeout=90000)
        info=page.locator('#registry-status').inner_text()
        report['published_registry_label']=info[:650]
        page.screenshot(path=str(TARGET/'public-registry.png'),full_page=False)
        report['checks']['public_source_registry']='passed'
        # Full deployed navigation check: CI passing on only the landing page is insufficient.
        # Preserve exact page-level results for the published preview, including non-insurance tabs.
        public_pages=('workbench','insurance','underwriting','map','universal',
                      'registry','facilities','cases','evidence','disclosures','sources',
                      'identity','feeds','quality','overview','methodology')
        for name in public_pages:
            nav=page.locator('.nav-item[data-page="'+name+'"]')
            assert nav.count()==1,'Missing public navigation item: '+name
            nav.click()
            expect(nav).to_have_class('nav-item active',timeout=15000)
            expect(page.locator('#view-root .loading-card')).to_have_count(0,timeout=20000)
            expect(page.locator('#view-root')).not_to_be_empty(timeout=15000)
            content=page.locator('#view-root').inner_text()
            assert len(content.strip())>=30,'Blank published page '+name
            assert 'Cannot read properties of undefined' not in content
            report['checks']['page_'+name]='passed'
        page.locator('.nav-item[data-page="workbench"]').click()
        page.screenshot(path=str(TARGET/'navigation-check-desktop.png'),full_page=False)
        context.close()
        mobile=browser.new_context(viewport={'width':390,'height':844},device_scale_factor=1,
                                   is_mobile=True,has_touch=True)
        phone=mobile.new_page()
        phone.on('pageerror',lambda error:report['js_exceptions'].append('mobile: '+str(error)))
        phone.goto(URL,wait_until='domcontentloaded',timeout=90000)
        expect(phone.locator('#view-root h1')).to_contain_text('Facility exposure & coverage workbench',timeout=90000)
        assert phone.evaluate('document.documentElement.scrollWidth <= window.innerWidth+2'), 'Horizontal mobile overflow'
        phone.screenshot(path=str(TARGET/'workbench-mobile.png'),full_page=True)
        report['checks']['mobile_layout']='passed'
        mobile.close()
        browser.close()
    (TARGET/'audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    assert not report['js_exceptions'],report['js_exceptions']
    assert not report['unexpected_private_api_calls'],report['unexpected_private_api_calls']
    print(json.dumps(report,indent=2))

if __name__=='__main__':
    audit()
