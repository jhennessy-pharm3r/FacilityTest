"""Source-identity and no-automatic-loss tests; entirely synthetic SEC filing excerpt."""
import json
from pathlib import Path
import tempfile
import unittest

from facilityrisk.lane_d.ingest_sec_bi import inspect_filing, run, validate_entry

ENTRY = {
    "issuer_cik": "10456", "accession": "0001628280-24-047221",
    "filename": "bax-20240930.htm",
    "source_scope": "2024Q3 10-Q", "issuer_name": "Example issuer",
    "event_terms": ["Hurricane Helene"], "site_terms": ["North Cove", "Marion"],
    "event_type": "natural disaster", "official_url":
        "https://www.sec.gov/Archives/edgar/data/10456/000162828024047221/bax-20240930.htm",
}

def html(body):
    return ("<html><head><title>SEC Sample</title><style>.x { color:red; }</style></head>"
            "<body><h1>UNITED STATES SECURITIES AND EXCHANGE COMMISSION</h1>"
            "<h2>FORM 10-Q</h2><p>"+body+"</p></body></html>").encode()


class PrimaryFilingTests(unittest.TestCase):
    def test_accession_identity_and_scoped_evidence(self):
        doc = html("Hurricane Helene flooded our North Cove facility in Marion. "
                   "Operations were disrupted. Business interruption policies may "
                   "cover some expenses and sales impacts subject to insurer review. "
                   "Management estimates a future sales impact of $200 million.")
        r = inspect_filing(ENTRY, doc)
        self.assertEqual(r["source_accession"], ENTRY["accession"])
        self.assertEqual(r["source_cik"], "10456")
        self.assertEqual(r["reported_site_terms"], ["North Cove", "Marion"])
        self.assertTrue(r["issuer_disclosure_verified"])
        self.assertFalse(r["physical_site_independently_verified"])
        self.assertFalse(r["power_outage_verified"])
        self.assertFalse(r["financial_amount_verified"])
        self.assertFalse(r["business_interruption_insurance_paid_verified"])
        self.assertIsNone(r["loss_amount_usd"])
        self.assertIsNone(r["claims_amount_usd"])
        self.assertIn("$200 million", r["evidence_excerpt"])

    def test_reject_wrong_accession_or_filename(self):
        for overrides in [
            {"accession": "0001628280-24-not-real"},
            {"official_url": "https://example.com/forged"},
            {"filename": "../../bad.htm"},
            {"issuer_cik": "ABCDEFG"},
        ]:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    validate_entry({**ENTRY, **overrides})

    def test_fail_when_source_site_missing(self):
        with self.assertRaisesRegex(ValueError, "Named site"):
            inspect_filing(ENTRY, html("Hurricane Helene disrupted operations at another place. "
                                       "Business interruption coverage is under review."))

    def test_fail_when_event_missing(self):
        with self.assertRaisesRegex(ValueError, "Event phrase absent"):
            inspect_filing(ENTRY, html("A reported North Cove site outage led to business interruption."))

    def test_no_source_html_if_download_not_authorized(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "truthful contact User-Agent"):
                run(ENTRY, Path(temp))

    def test_local_primary_html_manifest_separates_amounts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "archived.html"
            raw.write_bytes(html("Hurricane Helene hit the North Cove facility. "
                                 "Business interruption resulting from storm damage "
                                 "was under review by management and insurers."))
            manifest = run(ENTRY, root / "out", html_path=raw)
            self.assertEqual(manifest["issuer_disclosures_accepted"], 1)
            self.assertEqual(manifest["financial_amounts_verified"], 0)
            self.assertEqual(manifest["insured_claims_verified"], 0)
            self.assertEqual(manifest["verified_outage_events"], 0)
            self.assertEqual(manifest["durable_backend_indexed"], 0)
            rec = json.loads((root / "out" / "evidence.jsonl").read_text())
            self.assertEqual(rec["source_accession"], ENTRY["accession"])
            self.assertEqual(rec["source_filename"], ENTRY["filename"])


if __name__ == "__main__":
    unittest.main()
