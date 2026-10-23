"""Browser QA for new *private* EPA page, synthetic fixture only (not real coverage)."""
import json
import os
from pathlib import Path
import shutil
import sys
from playwright.sync_api import sync_playwright, expect

URL="http://127.0.0.1:8767/"
TOKEN=os.environ["FACILITY_RISK_AUTH_TOKEN"]

def audit():
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=["--no-sandbox"],executable_path=shutil.which("chromium"))
        context=browser.new_context(
            viewport={"width":1420,"height":940},
            extra_http_headers={"Authorization":"Bearer "+TOKEN})
        page=context.new_page()
        errors=[]
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.goto(URL,wait_until="domcontentloaded",timeout=45000)
        expect(page.locator("[data-page='epa']")).to_have_count(1)
        page.locator("[data-page='epa']").click()
        expect(page).to_have_url(URL+"?page=epa",timeout=15000)
        expect(page.locator(".epa-evidence-page h1")).to_contain_text("EPA regulatory evidence",timeout=15000)
        # Private EPA tab must preserve the concurrent shareable link and Back/Forward release.
        page.locator("[data-page='sources']").click()
        expect(page).to_have_url(URL+"?page=sources",timeout=15000)
        page.go_back(wait_until="domcontentloaded")
        expect(page).to_have_url(URL+"?page=epa",timeout=15000)
        expect(page.locator(".epa-evidence-page h1")).to_contain_text("EPA regulatory evidence",timeout=15000)
        page.go_forward(wait_until="domcontentloaded")
        expect(page).to_have_url(URL+"?page=sources",timeout=15000)
        page.goto(URL+"?page=epa",wait_until="domcontentloaded",timeout=45000)
        expect(page.locator(".epa-evidence-page h1")).to_contain_text("EPA regulatory evidence",timeout=15000)
        expect(page.locator("#epa-mount-status")).to_contain_text("Public EPA RMP interests",timeout=15000)
        expect(page.locator("#epa-mount-status")).to_contain_text("Verified private mount",timeout=15000)
        expect(page.locator("#epa-mount-status")).to_contain_text("Not installed",timeout=15000)
        page.locator("#epa-source").select_option("rmp_public")
        page.locator("#epa-native-id").fill("RMPFIXTURE100")
        page.locator("#epa-query button[type='submit']").click()
        expect(page.locator("#epa-query-result")).to_contain_text("source observation",timeout=15000)
        expect(page.locator("#epa-query-result")).to_contain_text("RMPFIXTURE100",timeout=15000)
        expect(page.locator("#epa-query-result")).not_to_contain_text("verified insured loss")
        page.locator("#epa-native-id").fill("absent-native-id")
        page.locator("#epa-query button[type='submit']").click()
        expect(page.locator("#epa-query-result")).to_contain_text("does not verify absence",timeout=15000)
        page.locator("#epa-source").select_option("echo")
        expect(page.locator("#epa-search")).to_be_disabled()
        assert not errors,errors
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 3")
        page.screenshot(path="/tmp/epa-private-browser-qa.png",full_page=True)
        print("PRIVATE_EPA_BROWSER_FIXTURE_PASS",json.dumps({
            "new_navigation":True,"private_source_mount_rendered":True,
            "source_exact_id_lookup":True,"unknown_id_unassessed":True,
            "missing_source_query_disabled":True,"browser_errors":errors,
            "source_fixture_only":True,"production_deployed_records":0}))
        browser.close()

if __name__=="__main__":audit()
