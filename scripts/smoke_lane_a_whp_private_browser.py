"""Chromium integration smoke on actual USDA national 270m files and private UI.

Uses public model QA coordinates and a deliberately synthetic review fixture.
Private real insurer site locations are NEVER uploaded to CI or GitHub Pages.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

from facilityrisk.db import connect,initialize
from facilityrisk.site_workspace import intake_site
from facilityrisk.intelligence import review_location


def run():
    if os.environ.get("FACILITY_RISK_REQUIRE_AUTH")!="1" or not os.environ.get("FACILITY_RISK_WHP2023_RASTER_ROOT"):
        raise ValueError("Private full-raster browser QA requires protected server and original full-source ZIP")
    with connect() as db:
        initialize(db)
        fixture=intake_site(db,{"name":"PUBLIC NORCAL SOURCE PIXEL QA ONLY","country":"US"},"qa-test")
        site_id=fixture["facility_id"]
        db.execute("UPDATE facilities SET latitude=?,longitude=? WHERE id=?",(39.5,-122,site_id))
        db.commit()
        review_location(db,site_id,"site_verified",
            "https://research.fs.usda.gov/firelab/products/dataandtools/wildfire-hazard-potential",
            "public-QA-fixture-not-an-insured-property",
            "Synthetic test-only marked-reviewed WGS84 source pixel, NOT a real property review")
    app_url="http://127.0.0.1:8765"
    process=subprocess.Popen([sys.executable,"-m","facilityrisk","serve",
                              "--host","127.0.0.1","--port","8765"],
                             stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
                             text=True,env=os.environ.copy())
    proof=Path("/tmp/facility-lane-a-original-whp-browser.png")
    try:
        for _ in range(80):
            if process.poll() is not None:
                raise RuntimeError("App exited before ready")
            try:
                with urllib.request.urlopen(app_url+"/api/health",timeout=2) as r:
                    if r.status==200:
                        break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(.25)
        else:
            raise RuntimeError("Authenticated private source UI did not start")
        with sync_playwright() as client:
            browser=client.chromium.launch(headless=True,args=["--no-sandbox"])
            context=browser.new_context(viewport={"width":1440,"height":960})
            def attach_token_only_to_loopback(route):
                header=dict(route.request.headers)
                header["Authorization"]="Bearer "+os.environ["FACILITY_RISK_AUTH_TOKEN"]
                return route.continue_(headers=header)
            context.route(app_url+"/**",attach_token_only_to_loopback)
            page=context.new_page()
            try:
                page.goto(app_url+"/",wait_until="domcontentloaded",timeout=30000)
                page.locator(".nav-item[data-page='feeds']").click()
                page.wait_for_function(
                    "() => document.querySelector('#view-root')?.textContent?.includes('USFS WHP2023 full original 270m raster')",
                    timeout=20000)
                text=page.locator("#view-root").inner_text()
                assert "133,505,015 modeled pixels per product" in text
                assert "Source health" in page.inner_text("body")
                page.locator(".nav-item[data-page='map']").click()
                page.wait_for_selector("#lane-a-wildfire-site",timeout=15000)
                picker=page.locator("#lane-a-wildfire-site")
                opts=picker.locator("option").evaluate_all("(els)=>els.map(x=>x.value)")
                assert site_id in opts
                picker.select_option(site_id)
                page.wait_for_function(
                    "() => document.querySelector('#lane-a-wildfire-result')?.textContent?.includes('133,505,015 non-masked')",
                    timeout=20000)
                button=page.locator("#lane-a-check-wildfire")
                assert button.is_enabled()
                button.click()
                page.wait_for_function(
                    "() => document.querySelector('#lane-a-wildfire-result')?.textContent?.includes('continuous source value 152')",
                    timeout=20000)
                result=page.locator("#lane-a-wildfire-result").inner_text()
                assert "Publisher landscape hazard: Low (class 2)" in result
                assert "NOT wildfire probability" in result
                with connect() as db:
                    db.execute("UPDATE facilities SET latitude=latitude+0.1 WHERE id=?",(site_id,))
                    db.commit()
                button.click()
                page.wait_for_function(
                    "() => document.querySelector('#lane-a-wildfire-result')?.textContent?.toLowerCase()?.includes('unknown unverified site coordinate')",
                    timeout=20000)
                proof.parent.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(proof),full_page=True)
            finally:
                context.close()
                browser.close()
        return {"real_full_publisher_six_tiffs_private_source_health_visible":True,
                "model_cell_count_not_facility_count":True,
                "actual_native_continuous_and_classified_2023_sample":True,
                "reviewed_source_qa_fixture_hazard_only":True,
                "changed_private_site_coordinate_revokes_hazard_query":True,
                "real_insured_site_matches":0,
                "permanent_host_deployed":False,
                "browser_qa_screenshot":str(proof)}
    finally:
        process.terminate()
        try:process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)


if __name__=="__main__":
    print("LANE_A_COMPLETE_USDA_RASTER_PRIVATE_BROWSER_PASS="+json.dumps(run(),sort_keys=True))
