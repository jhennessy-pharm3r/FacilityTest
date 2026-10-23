"""Test real official Lane A source artifacts through the authenticated FastAPI.

Requires FACILITY_RISK_LANE_A_INDEX_ROOT to reference an installed immutable
release on this runner. Fixture private research intake ≠ verified insured site.
"""
import json
import os
import sys

from fastapi.testclient import TestClient

from facilityrisk.app import app
from facilityrisk.db import connect, initialize
from facilityrisk.site_workspace import intake_site


def validate():
    if (os.environ.get("FACILITY_RISK_REQUIRE_AUTH") != "1" or
            len(os.environ.get("FACILITY_RISK_AUTH_TOKEN", "")) < 24 or
            not os.environ.get("FACILITY_RISK_LANE_A_INDEX_ROOT", "").startswith("/")):
        raise ValueError("Test requires source mount and authentication")
    authorization = {"Authorization": "Bearer " + os.environ["FACILITY_RISK_AUTH_TOKEN"]}
    with TestClient(app) as client:
        assert client.get("/api/lane-a/status").status_code == 401
        def get(path):
            response = client.get(path, headers=authorization)
            if response.status_code != 200:
                raise RuntimeError("Unexpected HTTP " + str(response.status_code) + " " + path)
            return response.json()

        status = get("/api/lane-a/status")
        assert status["state"] == "ready_partial"
        assert status["fema_national_geometry_complete"] is False
        assert status["usfs_270m_national_raster_complete"] is False
        assert status["authenticated_private_index_mounted"] is True
        assert status["source_only_records"] == {
            "fema_nfhl": 34, "usda_summary": 35304,
            "usda_continuous": 70, "usda_classified": 70,
        }
        combined = get("/api/source-indices/status")
        assert combined["lane_a"]["release_id"] == status["release_id"]

        original = get("/api/lane-a/usda-whp2023/geography/zip/00029")
        unknown = get("/api/lane-a/usda-whp2023/geography/zip/10168")
        county = get("/api/lane-a/usda-whp2023/geography/county/06017")
        management = get("/api/lane-a/usda-whp2023/geography/management_jurisdiction/Grand%20Total")
        assert original["native_geographic_id"] == "00029"
        assert original["original_archive_sha256"] == status["original_usda_zip_sha256"]
        assert unknown["source_coverage"] == "UNKNOWN_NO_AREA_VALUES"
        assert unknown["total_acres"] is None
        assert county["native_geographic_id"] == "06017"
        assert management["is_publisher_grand_total"] is True

        flood = get("/api/lane-a/fema-nfhl/06067C/06067C_1223")
        assert flood["source_key"] == "dfirm:06067C:fld_ar:06067C_1223"
        assert flood["original_reply_sha256"]
        assert flood["effective_date_verified"] is False
        assert flood["is_physical_insured_facility"] is False
        assert flood["coverage_is_national"] is False

        continuous = get("/api/lane-a/usda-whp2023/qa-pixel/usda_continuous/alaska/0")
        classified = get("/api/lane-a/usda-whp2023/qa-pixel/usda_classified/alaska/0")
        assert continuous["raw_sha256"] and classified["raw_sha256"]
        assert continuous["longitude"] == classified["longitude"]
        assert continuous["latitude"] == classified["latitude"]
        assert classified["class_label"] == "Non-burnable"
        assert classified["hazard_score_calibrated_to_property_losses"] is False

        absent = get("/api/lane-a/usda-whp2023/geography/zip/99999")
        assert absent["risk_assessment"] == "UNKNOWN"
        assert client.get("/api/lane-a/usda-whp2023/geography/zip/00029").status_code == 401

        with connect() as conn:
            initialize(conn)
            fixture = intake_site(conn, {"name": "CI ONLY — UNREVIEWED RESEARCH REQUEST",
                                         "country": "US"}, "integration-test")
        site = get("/api/facilities/" + fixture["facility_id"] + "/fema-nfhl")
        assert site["coverage_state"] == "UNKNOWN_UNVERIFIED_SITE_COORDINATE"
        assert site["source_features"] == []
        assert site["verified_property_hazard"] is False
        assert get("/api/lane-a/status")["verified_insured_sites"] == 0

    return {
        "real_source_queries_through_authenticated_api": True,
        "publisher_native_identifiers_preserved": True,
        "source_counts": status["source_only_records"],
        "source_release": status["release_id"],
        "missing_coverage_unknown": True,
        "unreviewed_site_blocked": True,
        "external_client_api_deployment_claimed": False,
        "insured_site_links": 0,
    }


def main():
    result = validate()
    print("LANE_A_REAL_FASTAPI_SOURCE_QUERIES_PASS=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
