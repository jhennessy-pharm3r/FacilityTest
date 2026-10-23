"""Browser-smoke the real authenticated private Lane A API and hazard UI.

Runs the app on 127.0.0.1 against *previously verified* original publisher
source artifacts. The only research site is an explicitly unreviewed CI fixture.
A passing ephemeral browser check never asserts external deployment.
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

from facilityrisk.db import connect, initialize
from facilityrisk.site_workspace import intake_site


def run():
    if not os.environ.get("FACILITY_RISK_LANE_A_INDEX_ROOT", "").startswith("/"):
        raise ValueError("Must mount actual installed Lane A publisher-source release")
    if (os.environ.get("FACILITY_RISK_REQUIRE_AUTH") != "1" or
            len(os.environ.get("FACILITY_RISK_AUTH_TOKEN", "")) < 24):
        raise ValueError("Must test an authenticated private server")
    with connect() as conn:
        initialize(conn)
        site = intake_site(conn, {
            "name": "CI-only unreviewed all-industry research request",
            "country": "US",
        }, "test-runner")
    url = "http://127.0.0.1:8765"
    process = subprocess.Popen(
        [sys.executable, "-m", "facilityrisk", "serve",
         "--host", "127.0.0.1", "--port", "8765"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        env=os.environ.copy(), text=True,
    )
    snapshot = Path("/tmp/lane-a-private-source-browser.png")
    try:
        healthy = False
        for _ in range(80):
            if process.poll() is not None:
                raise RuntimeError("Private API server exited before accepting connections")
            try:
                with urllib.request.urlopen(url + "/api/health", timeout=2) as response:
                    healthy = response.status == 200
                    if healthy:
                        break
            except (urllib.error.URLError, TimeoutError):
                time.sleep(0.25)
        if not healthy:
            raise RuntimeError("Private API did not become ready on loopback")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(viewport={"width": 1440, "height": 920})
            token = os.environ["FACILITY_RISK_AUTH_TOKEN"]
            # Scope private credentials to loopback ONLY; never forward to
            # Leaflet/CDN third-party tiles or unrelated origin requests.
            def authorize_local(route):
                headers = dict(route.request.headers)
                headers["Authorization"] = "Bearer " + token
                return route.continue_(headers=headers)
            context.route(url + "/**", authorize_local)
            page = context.new_page()
            try:
                page.goto(url + "/", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_selector(".nav-item[data-page='feeds']", timeout=15000)
                page.locator(".nav-item[data-page='feeds']").click()
                page.wait_for_function(
                    "() => document.querySelector('#view-root')?.textContent?.includes('FEMA NFHL — bounded flood polygons')",
                    timeout=20000,
                )
                root_text = page.locator("#view-root").inner_text()
                assert "USFS WHP 2023 — administrative aggregates" in root_text
                assert "35,304" in root_text
                assert "34" in root_text
                assert "0 approved insured-site matches" in root_text

                page.locator(".nav-item[data-page='map']").click()
                page.wait_for_selector("#lane-a-site", timeout=15000)
                page.wait_for_function(
                    "() => document.querySelector('#lane-a-fema-result')?.textContent?.includes('Bounded FEMA source index ready')",
                    timeout=20000,
                )
                selector = page.locator("#lane-a-site")
                assert site["facility_id"] in selector.locator("option").evaluate_all(
                    "(options) => options.map(option => option.value)"
                )
                selector.select_option(site["facility_id"])
                button = page.locator("#lane-a-check-fema")
                assert button.is_enabled()
                button.click()
                page.wait_for_function(
                    "() => document.querySelector('#lane-a-fema-result')?.textContent?.includes('unknown unverified site coordinate')",
                    timeout=20000,
                )
                output = page.locator("#lane-a-fema-result").inner_text().lower()
                assert "no legal nfip/firm" in output
                page.screenshot(path=str(snapshot), full_page=True)
            finally:
                context.close()
                browser.close()
        return {
            "actual_private_source_health_visible": True,
            "source_rows_are_not_facilities": True,
            "original_official_index_release": "0fe99942dd2d58919130de5b",
            "unreviewed_site_hazard_unknown": True,
            "no_client_deployment_claimed": True,
            "private_site_fixture_only": site["facility_id"].startswith("intake-"),
            "screenshot": str(snapshot),
        }
    finally:
        process.terminate()
        try:
            process.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=4)


if __name__ == "__main__":
    print("LANE_A_PRIVATE_BROWSER_REAL_SOURCE_QA=" + json.dumps(run(), sort_keys=True))
