"""Lane D issuer release tests: synthetic only; never counted as real ingestion."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from facilityrisk.lane_d.ingest_issuer_release import (
    SOURCE_RECORDS, inspect_issuer_html, run, validate_case, digest,
)


def html(case=None, body=None):
    case = case or SOURCE_RECORDS[0]
    body = body or (
        "Hurricane Helene caused an event at the North Cove facility. "
        "Operations at North Cove faced " + case["effect_terms"][0] + " while remediation progresses. "
        "Supply continuity and production capacity are being restored in phases. "
        "The company is reporting only anticipated financial implications; "
        "these are not completed loss adjustment claims or paid insurance policies. "
    )
    # Adequate length and realistic site/date anchor placement with HTML navigation.
    return (
        "<!doctype html><html><head><title>" + case["expected_title"] +
        "</title><script>var ignored='Hurricane Helene North Cove';</script></head>" +
        "<body><h1>" + case["expected_title"] + "</h1><p>" + case["release_date"] +
        "</p><article>" + body + "</article><footer>" + "Issuer release legal disclaimer. " * 14 +
        "</footer></body></html>"
    ).encode()


class FakeResponse:
    def __init__(self, data, url):
        self.data = data
        self.url = url
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return self.url

    def read(self, size):
        return self.data[:size]


class IssuerReleaseTests(unittest.TestCase):
    def test_release_identity_dates_events_and_no_loss_inference(self):
        case=SOURCE_RECORDS[0]
        raw=html(case)
        record=inspect_issuer_html(case, raw, case["source_url"], 200)
        self.assertEqual(record["source_id"],case["id"])
        self.assertEqual(record["publication_sha256"], digest(raw))
        self.assertIn("North Cove",record["reported_site_anchors"])
        self.assertEqual(record["source_authentication"], "HTTPS_FIRST_PARTY_200_EXACT_URL")
        self.assertTrue(record["issuer_reports_operational_interruption"])
        self.assertFalse(record["independently_verified_site_identity"])
        self.assertFalse(record["electrical_power_outage_verified"])
        self.assertFalse(record["actual_downtime_hours_verified"])
        self.assertFalse(record["insured_business_interruption_loss_verified"])
        self.assertIsNone(record["reported_financial_impact_amount"])

    def test_reject_nonissuer_domain_and_redirect(self):
        case=SOURCE_RECORDS[0]
        with self.assertRaisesRegex(ValueError,"approved first-party"):
            validate_case({**case,"source_url":"https://thirdparty.example/claim"})
        with self.assertRaisesRegex(ValueError,"Unexpected publisher"):
            inspect_issuer_html(case,html(case),"https://investor.baxter.com/another-page",200)

    def test_reject_false_or_missing_date_event_and_effect(self):
        case=SOURCE_RECORDS[0]
        for data in [
            html(case).replace(case["release_date"].encode(),b"August 8, 2019"),
            html(case).replace(b"Hurricane Helene",b"Hurricane Katrina"),
            html(case).replace(b"closed for production",b"paused"),
        ]:
            with self.assertRaises(ValueError):
                inspect_issuer_html(case, data, case["source_url"], 200)

    def test_company_q4_sales_forecast_distinct_from_actual_claim(self):
        c=SOURCE_RECORDS[1]
        issuer_guidance=(
            "Hurricane Helene caused extensive damage at the North Cove site. "
            "Baxter reports a production shutdown and an expected shortage of product. "
            "Financial Outlook: As a result of the hurricane, Baxter expects total company "
            "fourth-quarter sales to be negatively impacted by approximately $200 million, "
            "including other business segments. This is an estimate, not a paid claim."
        )
        doc=html(c,body=issuer_guidance)
        r=inspect_issuer_html(c,doc,c["source_url"],200)
        forecast=r["issuer_prospective_sales_guidance"]
        self.assertEqual(forecast["as_reported_approximate_amount"],200000000)
        self.assertEqual(forecast["scope"],"TOTAL_COMPANY_Q4_2024")
        self.assertTrue(forecast["estimated_not_realized"])
        self.assertTrue(forecast["not_covered_loss"])
        self.assertTrue(forecast["not_paid_insurance"])
        self.assertIsNone(r["reported_financial_impact_amount"])
        self.assertFalse(r["claims_paid_verified"])

    def test_multiple_documents_one_underlying_event(self):
        cases=[SOURCE_RECORDS[0], SOURCE_RECORDS[1]]
        def fake_urlopen(req,timeout=0):
            case=next(c for c in cases if c["source_url"]==req.full_url)
            return FakeResponse(html(case),case["source_url"])
        with tempfile.TemporaryDirectory() as t, patch(
            "facilityrisk.lane_d.ingest_issuer_release.urlopen",side_effect=fake_urlopen
        ):
            result=run(Path(t),cases=cases,min_success=2)
            self.assertEqual(result["downloaded"],2)
            self.assertEqual(result["distinct_named_underlying_events"],1)
            self.assertEqual(result["indexed_local_staging"],2)
            self.assertEqual(result["deployed"],0)
            self.assertEqual(result["durable_backend_indexed"],0)
            self.assertEqual(result["verified_financial_claims"],0)
            self.assertEqual(len((Path(t)/"issuer_disclosures.jsonl").read_text().splitlines()),2)

    def test_http_403_logged_not_verified(self):
        case=SOURCE_RECORDS[0]
        def error(req,timeout=0):
            raise HTTPError(req.full_url,403,"Forbidden",{},None)
        with tempfile.TemporaryDirectory() as t, patch(
            "facilityrisk.lane_d.ingest_issuer_release.urlopen",side_effect=error
        ):
            with self.assertRaisesRegex(RuntimeError,"acceptance gate failed"):
                run(Path(t),cases=[case],min_success=1)
            manifest=json.loads((Path(t)/"manifest.json").read_text())
            self.assertEqual((manifest["downloaded"],manifest["normalized"],manifest["indexed_local_staging"]),(0,0,0))
            self.assertIn("403",manifest["failed_sources"][0]["reason"])
            self.assertEqual(manifest["deployed"],0)


if __name__=="__main__":
    unittest.main()
