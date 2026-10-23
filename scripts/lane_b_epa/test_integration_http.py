"""Private FastAPI integration contract: source routes inherit app authentication."""
import base64
from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from facilityrisk.security import add_security,make_password_hash
from scripts.lane_b_epa.ingest import ingest
from scripts.lane_b_epa.integration_api import build_router

class PrivateEPAFastAPIRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        raw=root/"echo.csv"
        raw.write_text("REGISTRY_ID,FAC_NAME,FAC_LAT,FAC_LONG\nE123,Industrial Plant,41,-75\n")
        folder=root/"echo"
        ingest("echo",raw,folder)
        self.env={
            "FACILITY_RISK_LANE_B_ECHO_DIRECTORY":str(folder),
            "FACILITY_RISK_LANE_B_ROUTES_ENABLED":"1",
            "FACILITY_RISK_AUTH_TOKEN":"test-only-private-service-secret-32characters",
            "FACILITY_RISK_USERS_JSON":json.dumps({
                "audit_reviewer":{"role":"reviewer",
                    "password_hash":make_password_hash("unique-valid-test-password-for-private-review")}}),
        }
        app=FastAPI()
        app.include_router(build_router())
        add_security(app)
        self.client=TestClient(app)
        self.addCleanup(self.client.close)
    def test_authenticated_source_health_and_raw_access_control(self):
        with patch.dict(os.environ,self.env):
            missing=self.client.get("/api/epa/lane-b/status")
            self.assertEqual(missing.status_code,401)
            auth={"Authorization":"Bearer "+self.env["FACILITY_RISK_AUTH_TOKEN"]}
            ok=self.client.get("/api/epa/lane-b/status",headers=auth)
            self.assertEqual(ok.status_code,200)
            self.assertEqual(ok.json()["sources"]["echo"]["state"],"mounted_source_only")
            self.assertIsNone(ok.json()["sources"]["echo"]["production_deployed_records"])
            q=self.client.get("/api/epa/lane-b/echo/identity",headers=auth,params={"native_id":"E123"})
            self.assertEqual(q.status_code,200)
            self.assertEqual(q.json()["observations_available"],1)
            self.assertNotIn("raw_attributes",q.json()["rows"][0])
            self.assertEqual(q.headers.get("cache-control"),"no-store")
            denied=self.client.get("/api/epa/lane-b/echo/identity",headers=auth,
                params={"native_id":"E123","include_raw":"true"})
            self.assertEqual(denied.status_code,403)
            basic=base64.b64encode(b"audit_reviewer:unique-valid-test-password-for-private-review").decode()
            approved=self.client.get("/api/epa/lane-b/echo/identity",
                headers={"Authorization":"Basic "+basic},
                params={"native_id":"E123","include_raw":"true"})
            self.assertEqual(approved.status_code,200)
            self.assertEqual(approved.json()["rows"][0]["raw_attributes"]["FAC_NAME"],"Industrial Plant")
    def test_invalid_query_and_disabled_route_fail_without_coverage_conclusion(self):
        with patch.dict(os.environ,self.env):
            auth={"Authorization":"Bearer "+self.env["FACILITY_RISK_AUTH_TOKEN"]}
            invalid=self.client.get("/api/epa/lane-b/rcra/identity",headers=auth,
                params={"native_id":"ID123"})
            self.assertEqual(invalid.status_code,503)
            wrong=self.client.get("/api/epa/lane-b/echo/identity",headers=auth,
                params={"native_id":"E123","activity_location":"TX"})
            self.assertEqual(wrong.status_code,422)
            missing=self.client.get("/api/epa/lane-b/echo/identity",headers=auth,
                params={"native_id":"unknown"})
            self.assertEqual(missing.status_code,200)
            self.assertEqual(missing.json()["observations_available"],0)
            self.assertEqual(missing.json()["site_and_insured_loss_status"],"UNASSESSED")
            with patch.dict(os.environ,{"FACILITY_RISK_LANE_B_ROUTES_ENABLED":"0"}):
                off=self.client.get("/api/epa/lane-b/status",headers=auth)
                self.assertEqual(off.status_code,503)
if __name__=="__main__":unittest.main()
