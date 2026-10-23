"""Coordinator-only private HTTP contract for installed Lane D source indexes.

All local fixtures in this module are SYNTHETIC and NOT source-ingestion evidence;
official-source end-to-end coverage is in GitHub Actions integration workflow.
"""
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from facilityrisk.app import app
from facilityrisk.lane_d.install_source_index import install
from facilityrisk.lane_d.private_api import installed_status, _check_cached
from test_lane_d_install_source_index import make_bundle


@pytest.fixture()
def secured_api(monkeypatch, tmp_path):
    _check_cached.cache_clear()
    monkeypatch.setenv("FACILITY_RISK_DB", str(tmp_path / "insured-workspace.sqlite"))
    monkeypatch.setenv("FACILITY_RISK_AUTH_TOKEN", "L" * 48)
    monkeypatch.setenv("FACILITY_RISK_REQUIRE_AUTH", "1")
    monkeypatch.delenv("FACILITY_RISK_LANE_D_ODIN_USE_APPROVED", raising=False)
    monkeypatch.delenv("FACILITY_RISK_LANE_D_INDEX_ROOT", raising=False)
    root = tmp_path / "source-index"
    root.mkdir()
    client = TestClient(app, headers={"Authorization": "Bearer " + "L" * 48})
    yield client, root, monkeypatch, tmp_path
    _check_cached.cache_clear()
    client.close()


def load_source(root, scratch, kind):
    pkg, src_sha, index_sha = make_bundle(scratch, kind)
    result = install(pkg, root, kind, src_sha, index_sha)
    assert result["verified_readonly_sqlite"] is True
    return result


def test_no_source_mount_returns_unknown_not_safe_or_deployed(secured_api):
    client, _root, _patch, _dir = secured_api
    health = client.get("/api/source-context/lane-d/status")
    assert health.status_code == 200
    status = health.json()
    assert status["datasets"]["pnnl_2014_2023"]["state"] == "not_configured"
    assert status["datasets"]["eia861_2025"]["indexed_private_readonly_rows"] == 0
    assert status["confirmed_insured_site_outages"] == 0
    assert client.get("/api/source-context/historical-outages?county_fips=01001").status_code == 503
    assert client.get("/api/source-indices/status").json()["lane_d"]["source_index_mount_configured"] is False


def test_existing_app_private_auth_protects_new_source_routes(secured_api):
    _client, _root, _patch, _dir = secured_api
    with TestClient(app) as anonymous:
        for endpoint in (
            "/api/source-context/lane-d/status",
            "/api/source-context/utility-candidates?state=WA&county=Pierce",
            "/api/source-context/historical-outages?county_fips=01001",
            "/api/source-context/annual-electric-disturbances?year=2023",
            "/api/source-context/current-outages?county_fips=01001",
        ):
            response = anonymous.get(endpoint)
            assert response.status_code == 401, (endpoint, response.text)


def test_source_index_installed_can_query_only_native_context(secured_api):
    client, root, patch, temp = secured_api
    load_source(root, temp, "eia861_2025")
    load_source(root, temp, "pnnl_2014_2023")
    patch.setenv("FACILITY_RISK_LANE_D_INDEX_ROOT", str(root))
    status = client.get("/api/source-indices/status").json()["lane_d"]
    eia = status["datasets"]["eia861_2025"]
    pnnl = status["datasets"]["pnnl_2014_2023"]
    assert eia["state"] == pnnl["state"] == "verified_private_source_index"
    assert eia["indexed_private_readonly_rows"] == pnnl["indexed_private_readonly_rows"] == 2
    assert eia["public_pages_deployed"] is False
    assert pnnl["source_row_exact_duplicates_flagged"] == 1
    candidates = client.get("/api/source-context/utility-candidates?state=WA&county=Pierce").json()
    assert candidates["read_only_source_context_served_by_private_api"] is True
    assert candidates["data"]["source_territory_observations"] == 1
    assert candidates["insured_site_service_connection_verified"] is False
    county = client.get(
        "/api/source-context/historical-outages?county_fips=01001&year=2014&limit=10").json()
    assert county["data"]["candidate_counts"]["pnnl_historical_county_episodes"] == 1
    assert len(county["data"]["returned_findings"]) == 1
    assert county["insured_site_outage_verified"] is False
    assert county["paid_insurer_business_interruption_claim_verified"] is False
    assert county["data"]["returned_findings"][0]["insured_facility_outage_verified"] is False


def test_invalid_query_or_missing_index_never_claims_zero_risk(secured_api):
    client, root, patch, _temp = secured_api
    patch.setenv("FACILITY_RISK_LANE_D_INDEX_ROOT", str(root))
    assert client.get("/api/source-context/historical-outages?county_fips=1").status_code == 422
    assert client.get("/api/source-context/utility-candidates?state=xx&county=Pierce").status_code == 422
    assert client.get("/api/source-context/utility-candidates?state=WA&county=Pierce").status_code == 503
    assert client.get("/api/source-context/annual-electric-disturbances?year=1800").status_code == 422
    assert client.get("/api/source-context/current-outages?county_fips=01001").status_code == 503
    health = client.get("/api/source-context/lane-d/status").json()["datasets"]
    assert health["pnnl_2014_2023"]["state"] == "not_installed"
    assert health["odin_direct_public"]["state"] == "not_installed"


def test_odin_rights_fail_closed_and_cannot_fake_deployment(secured_api):
    client, root, patch, _temp = secured_api
    patch.setenv("FACILITY_RISK_LANE_D_INDEX_ROOT", str(root))
    res = client.get("/api/source-context/current-outages?county_fips=01001")
    assert res.status_code == 503
    assert "rights review" in res.text.lower()
    patch.setenv("FACILITY_RISK_LANE_D_ODIN_USE_APPROVED", "1")
    assert client.get("/api/source-context/current-outages?county_fips=01001").status_code == 503
    assert client.get("/api/source-context/lane-d/status").json()["confirmed_paid_insurance_claims"] == 0


def test_manifest_or_sqlite_tampering_blocks_readonly_serving(secured_api):
    client, root, patch, temp = secured_api
    load_source(root, temp, "eia861_2025")
    patch.setenv("FACILITY_RISK_LANE_D_INDEX_ROOT", str(root))
    assert client.get("/api/source-context/utility-candidates?state=WA&county=Pierce").status_code == 200
    current = json.loads((root / "eia861_2025" / "current.json").read_text())
    installed = root / "eia861_2025" / current["relative_db"]
    # Attacker-modified payload cannot be served from immutable verified cache
    # when the index inode/size/mtime changes.
    installed.chmod(0o600)
    installed.write_bytes(installed.read_bytes() + b"TAMPERED")
    result = client.get("/api/source-context/utility-candidates?state=WA&county=Pierce")
    assert result.status_code == 503
    assert client.get("/api/source-context/lane-d/status").json()["datasets"]["eia861_2025"]["state"] == "unavailable"


def test_source_index_cannot_live_inside_mutable_insured_workspace(secured_api):
    client, root, patch, temp = secured_api
    private = temp / "insured-data"
    private.mkdir()
    patch.setenv("FACILITY_RISK_DB", str(private / "insured-workspace.sqlite"))
    patch.setenv("FACILITY_RISK_LANE_D_INDEX_ROOT", str(private))
    status = client.get("/api/source-context/lane-d/status").json()
    assert status["datasets"]["eia861_2025"]["state"] == "unavailable"
    assert client.get("/api/source-context/utility-candidates?state=WA&county=Pierce").status_code == 503
