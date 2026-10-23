"""Browser acceptance of private Facility Risk Source Health with synthetic-only rows.

This verifies the real UI event handlers, read-only FastAPI integration,
pagination and status language. It does NOT test 25 actual insured facilities,
production hosting, primary PHMSA incident downloads or site-level matching.
"""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sqlite3
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
source=ROOT/"tests/test_industrial_private_api.py"
spec=importlib.util.spec_from_file_location("test_industrial_private_api",source)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def reachable(host="127.0.0.1",port=8766):
    try:
        with socket.create_connection((host,port),timeout=1):
            return True
    except OSError:
        return False

def smoke():
    with tempfile.TemporaryDirectory(prefix="lane-e-synthetic-browser-") as d:
        location=Path(d)
        incident_root=mod._incidents(location)
        wms_root=mod._enforcement(location)
        token=secrets.token_urlsafe(36)
        reviewer_pass=secrets.token_urlsafe(30)
        from facilityrisk.security import make_password_hash
        from facilityrisk.universal_registry import import_records
        from facilityrisk.db import initialize
        workspace=location/"workspace.sqlite"
        with sqlite3.connect(workspace) as c:
            c.row_factory=sqlite3.Row
            initialize(c)
            import_records(c,"EPA_FRS",[{
              "source_identifier":"110000000001","name":"Example Industries Test Plant",
              "company":"Example Industries","city":"Test City 1",
              "state":"TX","country":"US","industry":"Manufacturing",
              "address":"123 Synthetic Test Road","latitude":29.01,"longitude":-95.01
            }],"https://www.epa.gov/frs",vintage="synthetic-browser-test-2026")
            site_id=c.execute("""SELECT site_id FROM universal_source_records
              WHERE source_key='EPA_FRS' AND source_identifier='110000000001'""").fetchone()[0]
            c.execute("""INSERT INTO facilities(id,name,company,address,country,origin,last_imported)
                         VALUES(?,?,?,?,?,?,?)""",(
                "synthetic-insured-research-case",
                "Example Industries Research Case",
                "Example Industries","123 Synthetic Test Road, Test City 1, TX",
                "US","analyst_research_unverified","2026-10-23"))
            c.execute("""INSERT INTO universal_research_links(site_id,research_facility_id)
                         VALUES(?,?)""",(site_id,"synthetic-insured-research-case"))
            c.commit()
        env=os.environ.copy()
        env.update({
            "FACILITY_RISK_DB":str(workspace),
            "FACILITY_RISK_LANE_C_ROOT":str(incident_root),
            "FACILITY_RISK_PHMSA_WMS_ROOT":str(wms_root),
            "FACILITY_RISK_AUTH_TOKEN":token,
            "FACILITY_RISK_USERS_JSON":json.dumps({
                "reviewerone":{"role":"reviewer",
                               "password_hash":make_password_hash(reviewer_pass)}
            }),
            "FACILITY_RISK_REQUIRE_AUTH":"1",
            "FACILITY_RISK_ENABLE_WRITES":"0"
        })
        proc=subprocess.Popen([
            sys.executable,"-m","uvicorn","facilityrisk.app:app",
            "--host","127.0.0.1","--port","8766","--no-access-log"
        ],env=env,cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
        try:
            for _ in range(65):
                if reachable():break
                if proc.poll() is not None:
                    raise AssertionError("Private backend failed before UI test: "+proc.stderr.read()[-1200:])
                time.sleep(.2)
            else:raise AssertionError("Private backend not listening on loopback")

            with sync_playwright() as playwright:
                browser=playwright.chromium.launch(headless=True,args=["--no-sandbox"])
                context=browser.new_context(
                    viewport={"width":1450,"height":950},
                    http_credentials={"username":"reviewerone","password":reviewer_pass})
                page=context.new_page()
                errors=[]
                page.on("pageerror",lambda e:errors.append(str(e)))
                # No external CSS/tile vendor is needed to demonstrate the private
                # source-only page; prevent outbound access in synthetic test.
                page.route("https://unpkg.com/**",lambda route:route.abort())
                page.goto("http://127.0.0.1:8766/",wait_until="domcontentloaded",timeout=45000)
                # The async app bootstrap fetches five datasets then rerenders
                # the initial page. Clicking the sidebar before it completes
                # is a navigation race: bootstrap resets to the workbench.
                expect(page.locator('#view-root h1')).to_contain_text(
                    "Facility exposure & coverage workbench",timeout=20000)
                expect(page.locator('[data-page="workbench"]')).to_have_class(
                    "nav-item active",timeout=20000)
                page.locator('[data-page="feeds"]').click()
                expect(page.locator('#breadcrumb-page')).to_have_text(
                    "SOURCE STATUS",timeout=15000)
                expect(page.locator(".industrial-private-explorer")).to_be_visible(timeout=30000)
                expect(page.locator(".industrial-metrics")).to_contain_text("26")
                expect(page.locator(".industrial-metrics")).to_contain_text("2")
                page.locator("#industrial-source-select").select_option("nrc_2025")
                page.locator("#industrial-events-form button[type=submit]").click()
                expect(page.locator("#industrial-events-message")).to_contain_text("25 source rows",timeout=15000)
                expect(page.locator("#industrial-events-rows tr")).to_have_count(25)
                expect(page.locator("#industrial-prev")).to_be_disabled()
                expect(page.locator("#industrial-next")).to_be_disabled()
                page.locator("#industrial-state").fill("TX")
                page.locator("#industrial-events-form button[type=submit]").click()
                expect(page.locator("#industrial-events-message")).to_contain_text("13 source rows",timeout=15000)
                expect(page.locator("#industrial-events-rows tr")).to_have_count(13)
                page.locator("#industrial-operator").fill("00123")
                page.locator("#industrial-wms-form button[type=submit]").click()
                expect(page.locator("#industrial-wms-message")).to_contain_text("1 enforcement case",timeout=15000)
                expect(page.locator("#industrial-wms-rows tr")).to_have_count(1)
                expect(page.locator(".industrial-private-explorer")).to_contain_text("not confirmed accidents")
                # Select a real *workflow* source-site identity from the
                # synthetic FRS fixture, then screen agency-native reports.
                # Candidate rows NEVER become verified incident/site links.
                page.locator('[data-page="universal"]').click()
                expect(page.locator('#uf-q')).to_be_visible(timeout=20000)
                expect(page.locator('#uf-results .registry-record')).to_have_count(1,timeout=20000)
                page.locator('#uf-results button[data-uf-id]').first.click()
                expect(page.locator('#uf-industrial')).to_be_visible(timeout=12000)
                page.locator('#uf-industrial').click()
                expect(page.locator('#uf-industrial-results')).to_contain_text(
                    "candidate source observations",timeout=18000)
                expect(page.locator('#uf-industrial-results')).to_contain_text(
                    "reviewer investigation required",timeout=18000)
                expect(page.locator('#uf-industrial-results')).to_contain_text(
                    "NO confirmed site attribution",timeout=18000)
                # Existing research-case drawer must also read the exact
                # linked publisher site identity (never infer from the
                # company's headquarters address).
                page.locator('[data-page="facilities"]').click()
                expect(page.locator('#facility-cards [data-site]')).to_have_count(1,timeout=20000)
                page.locator('#facility-cards [data-site]').first.click()
                expect(page.locator('#detail-drawer')).to_be_visible(timeout=12000)
                page.locator('#detail-drawer [data-tab="risk"]').click()
                expect(page.locator('#industrial-research-case-check')).to_be_visible(timeout=15000)
                page.locator('#industrial-research-case-check').click()
                expect(page.locator('#industrial-research-case-results')).to_contain_text(
                    "source-report candidates",timeout=18000)
                expect(page.locator('#industrial-research-case-results')).to_contain_text(
                    "none independently attributed to the insured site",timeout=18000)
                assert not errors,errors
                shot=Path("/tmp/lane-e-private-industrial-synthetic-smoke.png")
                page.screenshot(path=str(shot),full_page=True)
                print("PRIVATE_UI_BROSWER_SYNTHETIC_ONLY_PASS: 25 industry labels, NRC/CSB source queries, WMS filter, 401 Basic challenge, no automatic facility matches")
                context.close();browser.close()
        finally:
            proc.terminate()
            try:proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill();proc.wait(timeout=5)

if __name__=="__main__":
    smoke()
