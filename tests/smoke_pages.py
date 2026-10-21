"""Public GitHub Pages browser smoke check; runs on GitHub CI only.

Uses only public demo fixtures, never the analyst workbook or insured data.
"""
from playwright.sync_api import sync_playwright,expect

BASE='http://127.0.0.1:8099/'

with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1480,'height':950},device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(BASE,wait_until='domcontentloaded',timeout=45000)
    expect(page.locator('#view-root h1')).to_contain_text('Facility Risk Intelligence',timeout=30000)
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
    page.screenshot(path='/tmp/facility-public-browser-smoke.png',full_page=True)
    assert not errors, 'JavaScript runtime exceptions: '+'; '.join(errors)
    print('Public preview browser routes and facility underwriting drawer passed.')
    browser.close()