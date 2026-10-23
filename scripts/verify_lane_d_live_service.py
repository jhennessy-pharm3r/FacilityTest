"""Operator validation of a REAL running private Lane D source API.

This script cannot provision a VM, sign a backup, approve source rights, verify
physical sites, or change Source Health. Run on a private host after the source
SHA-pinned Lane D index installation. Credential is read from an environment
variable, never supplied on a command line or written to the QA receipt.

Remote HTTP is disallowed; remote checks require HTTPS + authenticated access.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

EXPECTED = {
    "eia861_2025": (12923, "f59f6c732bf685fe0a1591b32227f5ce572dc0dfd26bb5caaeed128ac4e3a396"),
    "pnnl_2014_2023": (2124183, "44557bae7a5c8e02c611a14f75fe9e123d81d286f700b9fd88ac538edd910fe7"),
    "oe417_annual_public": (341, "5329d272544e9164692f08b34a5079d3f89a2095f1a77a8fa8dfca8923b06d18"),
}


def validate_url(url):
    parsed = urlparse(url)
    if (parsed.username or parsed.password or parsed.query or parsed.fragment
        or parsed.path not in ("", "/")):
        raise ValueError("Base URL must contain only host and optional port")
    if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Remote plaintext HTTP is not allowed")
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Private source API must use local HTTP or verified HTTPS")
    if not parsed.hostname:
        raise ValueError("Private source API requires an actual hostname")
    return url.rstrip("/")


def run(url, token, *, county_fips="48201"):
    url = validate_url(url)
    if not isinstance(token, str) or len(token) < 32:
        raise ValueError("Provide an authorized 32+ character token in a secret environment variable")
    if not isinstance(county_fips, str) or len(county_fips) != 5 or not county_fips.isdigit():
        raise ValueError("County FIPS must be exactly five source-geography digits")

    def request(path, authenticated=True):
        headers = {"Accept": "application/json"}
        if authenticated:
            headers["Authorization"] = "Bearer " + token
        try:
            with urlopen(Request(url + path, headers=headers), timeout=180) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    anonymous, _ = request("/api/source-context/lane-d/status", authenticated=False)
    if anonymous != 401:
        raise RuntimeError("Private Lane D source status is not protected by 401 authentication")
    code, result = request("/api/source-context/lane-d/status")
    if code != 200 or not result.get("source_index_mount_configured"):
        raise RuntimeError("Authenticated backend is missing source index mount")
    actual = result["datasets"]
    for key, (expected_count, official_sha) in EXPECTED.items():
        row = actual[key]
        if (row["state"] != "verified_private_source_index"
            or row["indexed_private_readonly_rows"] != expected_count
            or row.get("publisher_original_sha256") != official_sha):
            raise RuntimeError("Private serving count/provenance gate failed for "+key)
        if (row["verified_insured_site_utility_connections"] != 0
            or row["verified_insured_facility_outages"] != 0
            or row["public_pages_deployed"] is not False):
            raise RuntimeError("Source serving incorrectly reports site verification or public deployment")

    code, utilities = request("/api/source-context/utility-candidates?" +
                              urlencode({"state": "WA", "county": "Pierce", "limit": 20}))
    if (code != 200 or utilities["data"]["source_territory_observations"] != 15
        or utilities["insured_site_service_connection_verified"] is not False):
        raise RuntimeError("Actual EIA Pierce utility candidate query failed")

    code, historical = request("/api/source-context/historical-outages?" +
                               urlencode({"county_fips": county_fips, "limit": 10}))
    county_count = historical.get("data", {}).get("candidate_counts", {}).get(
        "pnnl_historical_county_episodes", 0)
    if (code != 200 or not isinstance(county_count, int) or county_count <= 0
        or historical["insured_site_outage_verified"] is not False
        or not historical["data"]["returned_findings"]
        or any(x["insured_facility_outage_verified"] for x in historical["data"]["returned_findings"])):
        raise RuntimeError("Historical county source query failed or imputed insured-site outage")

    code, annual = request("/api/source-context/annual-electric-disturbances?year=2023&limit=10")
    if (code != 200 or annual["data"]["matching_content_distinct_source_rows"] != 309
        or annual["paid_insurer_business_interruption_claim_verified"] is not False):
        raise RuntimeError("Actual DOE annual disturbance read-only query failed")

    code, _ = request("/api/source-context/current-outages?county_fips=01001")
    if code != 503:
        raise RuntimeError("Unapproved/not-installed ORNL source did not fail closed")

    return {
        "check_utc": datetime.now(timezone.utc).isoformat(),
        "private_authenticated_live_http_source_query_verified": True,
        "source_count_and_original_sha_verified": {
            key: {"accepted": count, "official_source_sha256": sha}
            for key, (count, sha) in EXPECTED.items()
        },
        "unauthenticated_request_http_code": anonymous,
        "eia_pierce_reported_provider_candidates": 15,
        "pnnl_county_fips": county_fips,
        "pnnl_reported_county_episode_rows": county_count,
        "doe_annual_2023_source_dated_rows": 309,
        "odin_publisher_rights_not_approved_in_this_test": True,
        "installed_http_source_index_as_insured_property": False,
        "confirmed_insured_site_outages": 0,
        "carrier_confirmed_insurance_claims": 0,
        "backup_restore_attestation_completed_by_this_test": False,
        "public_pages_data_deployment_completed_by_this_test": False,
        "operator_must_separately_verify_persistent_storage_backups_and_oidc": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--token-env", default="FACILITY_RISK_AUTH_TOKEN")
    parser.add_argument("--county-fips", default="48201")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    token = os.environ.get(args.token_env)
    if not token:
        raise SystemExit("Missing configured private token environment variable")
    report = run(args.base_url, token, county_fips=args.county_fips)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
