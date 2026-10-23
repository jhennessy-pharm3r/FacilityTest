"""Coordinator Lane A API gates. Fixture locations never count as insured sites."""
import sqlite3

from fastapi.testclient import TestClient

from facilityrisk.app import app
from facilityrisk import lane_a_service


def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("FACILITY_RISK_REQUIRE_AUTH", "1")
    monkeypatch.setenv("FACILITY_RISK_AUTH_TOKEN", "q" * 40)
    monkeypatch.setenv("FACILITY_RISK_DB", str(tmp_path / "workspace.sqlite"))
    return TestClient(app)


def _auth(client, url):
    return client.get(url, headers={"Authorization": "Bearer " + "q" * 40})


def test_source_indices_never_treat_unmounted_lane_a_as_zero_hazard(monkeypatch, tmp_path):
    monkeypatch.delenv(lane_a_service.ROOT_ENV, raising=False)
    with _client(monkeypatch, tmp_path) as client:
        assert client.get("/api/lane-a/status").status_code == 401
        status = _auth(client, "/api/lane-a/status")
        assert status.status_code == 200
        assert status.json()["state"] == "not_configured"
        assert status.json()["source_only_records"] is None
        combined = _auth(client, "/api/source-indices/status").json()
        assert combined["lane_a"]["state"] == "not_configured"
        assert _auth(client, "/api/lane-a/usda-whp2023/geography/zip/00029").status_code == 503
        assert _auth(client, "/api/lane-a/fema-nfhl/06067C/06067C_1223").status_code == 503
        assert _auth(client, "/api/lane-a/usda-whp2023/qa-pixel/usda_continuous/alaska/0").status_code == 503
        assert _auth(client, "/api/facilities/not-a-site/fema-nfhl").status_code == 503


def test_invalid_mounted_release_is_unavailable_not_zero(monkeypatch, tmp_path):
    monkeypatch.setenv(lane_a_service.ROOT_ENV, str(tmp_path / "not-an-installation"))
    with _client(monkeypatch, tmp_path) as client:
        bad = _auth(client, "/api/lane-a/status")
        assert bad.status_code == 200
        assert bad.json()["state"] == "unavailable"
        assert bad.json()["source_only_records"] is None
        assert _auth(client, "/api/lane-a/usda-whp2023/geography/zip/00029").status_code == 503
        assert _auth(client, "/api/source-indices/status").json()["lane_a"]["state"] == "unavailable"


def test_api_rejects_invalid_publisher_source_identity(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as client:
        assert _auth(client, "/api/lane-a/usda-whp2023/geography/company/acme").status_code == 422
        assert _auth(client, "/api/lane-a/fema-nfhl/DFIRM-1/not%20valid").status_code == 422
        assert _auth(client, "/api/lane-a/usda-whp2023/qa-pixel/invalid/alaska/0").status_code == 422


def test_only_private_workspace_review_of_current_coordinate_enables_fema_screen(monkeypatch):
    """An external caller cannot supply a self-asserted reviewed=true flag."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE facilities(id TEXT PRIMARY KEY,latitude REAL,longitude REAL);
        CREATE TABLE location_reviews(
            facility_id TEXT PRIMARY KEY,precision TEXT,evidence_url TEXT,
            reviewed_latitude REAL,reviewed_longitude REAL);
    """)
    db.execute("INSERT INTO facilities VALUES ('qa-only-site',29.9511,-90.0715)")
    calls = []
    def fake_point(root, **kwargs):
        calls.append(kwargs)
        return {"coverage_state": "SOURCE_POLYGON_INTERSECTION_AT_CORROBORATED_POINT",
                "source_features": [], "review_required": True}
    monkeypatch.setattr(lane_a_service, "_ready",
                        lambda: ("/no-live-records", {"release_id": "abc123"}))
    monkeypatch.setattr(lane_a_service, "query_reviewed_coordinate", fake_point)
    try:
        not_reviewed = lane_a_service.reviewed_facility_flood(db, "qa-only-site")
        assert not_reviewed["coverage_state"] == "UNKNOWN_UNVERIFIED_SITE_COORDINATE"
        assert calls == []
        db.execute("""INSERT INTO location_reviews VALUES
            ('qa-only-site','site_verified','https://example.gov/original-property-record',
             29.9511,-90.0715)""")
        allowed = lane_a_service.reviewed_facility_flood(db, "qa-only-site")
        assert allowed["source_release_id"] == "abc123"
        assert allowed["property_hazard_legally_confirmed"] is False
        assert calls[0]["coordinates_corroborated"] is True
        assert calls[0]["coordinate_evidence"].startswith("https://")
        assert calls[0]["site_reference"] == "qa-only-site"
        db.execute("UPDATE facilities SET longitude=-90.0799 WHERE id='qa-only-site'")
        changed = lane_a_service.reviewed_facility_flood(db, "qa-only-site")
        assert changed["coverage_state"] == "UNKNOWN_UNVERIFIED_SITE_COORDINATE"
        assert len(calls) == 1
    finally:
        db.close()
