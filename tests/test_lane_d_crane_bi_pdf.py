"""Issuer-hosted source PDF finance: standalone SYNTHETIC fixture evidence tests."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from facilityrisk.lane_d.ingest_crane_bi_pdf import (
    SOURCE_DOCS, financial_facts, parse_pages, run, fetch_pdf
)


def make_pages(case,section_text):
    return [
        "CRANE COMPANY FORM "+case["filing_form"]+" for the Period Ended "+case["period_anchor"]
            +" Commission file number 1-41570",
        "Table of Contents Crane Company reporting issuer",
        "Other Notes company business strategy details",
        "Marion, NC Site Hurricane Damage and Recovery: In September 2024, "
            "Crane's Marion, North Carolina site was affected by flooding from Hurricane Helene. "
            "Insurance policy provides business interruption coverage including lost profits. "
            +section_text,
        "Further reporting, other narrative.",
        *["Ordinary unrelated form data"]*7,
    ]


def year2024():
    return (
        "For the year ended December 31, 2024, we incurred losses and expenses "
        "of $23.3 million related to damages caused by the hurricane, including "
        "repairs and inventory. We have received insurance recoveries of $20.0 million "
        "and have an insurance receivable of $2.8 million, net of deductible."
    )


def q22025():
    return (
        "For the six months ended June 30, 2025, we incurred expenses, "
        "and have an insurance receivable of $3.6 million. "
        "On a cumulative basis, we incurred expenses of $29.1 million related to damage "
        "and received corresponding insurance recoveries of $25.0 million. "
        "During the second quarter we also received insurance proceeds for lost profits "
        "of $4.0 million, included in Miscellaneous income, net."
    )


class CranePDFTest(unittest.TestCase):
    def test_2024_repair_expenses_and_property_recoveries_not_bi(self):
        c=SOURCE_DOCS[0]
        facts,rec=parse_pages(c,make_pages(c,year2024()),"sha2024")
        self.assertEqual(len(facts),3)
        self.assertEqual(rec["pdf_page_count"],12)
        self.assertEqual(rec["issuer_reported_insurance_cash_received_for_lost_profits_usd"],0)
        self.assertEqual({f["financial_metric_kind"]:f["reported_amount_usd"] for f in facts},{
            "INCURRED_PROPERTY_REPAIR_REMEDIATION_EXPENSE":23_300_000,
            "RECEIVED_HURRICANE_INSURANCE_RECOVERY_UNALLOCATED":20_000_000,
            "REMAINING_INSURANCE_RECEIVABLE":2_800_000,
        })
        self.assertTrue(all(not f["independent_insurer_claim_payment_confirmed"] for f in facts))
        self.assertTrue(all(not f["actual_site_power_outage_confirmed"] for f in facts))

    def test_2025_actual_bi_received_is_distinct_from_cumulative_site_recovery(self):
        c=SOURCE_DOCS[1]
        facts,rec=parse_pages(c,make_pages(c,q22025()),"sha2025")
        self.assertEqual(len(facts),4)
        self.assertEqual(rec["issuer_reported_insurance_cash_received_for_lost_profits_usd"],4_000_000)
        actual=[x for x in facts if x["issuer_reports_received_lost_profit_bi_proceeds"]]
        self.assertEqual(len(actual),1)
        self.assertEqual(actual[0]["accounting_period_or_window"],"2025_Q2")
        self.assertEqual(actual[0]["basis"],"ISSUER_REPORTS_RECEIVED_BI_PROCEEDS")
        self.assertFalse(actual[0]["independent_insurer_claim_payment_confirmed"])
        self.assertIn("2024_EVENT_THROUGH_2025_06_30",
                      {x["accounting_period_or_window"] for x in facts})
        self.assertNotEqual(actual[0]["financial_metric_kind"],"CUMULATIVE_HURRICANE_INSURANCE_RECOVERY_UNALLOCATED")

    def test_reject_false_issuer_period_or_weak_context(self):
        c=SOURCE_DOCS[1]
        good=make_pages(c,q22025())
        for pages in (
            [x.replace("CRANE COMPANY","OTHER COMPANY") for x in good],
            [x.replace("June 30, 2025","June 30, 2024") for x in good],
            [x.replace("Marion, NC","Different, TX") for x in good],
            [x.replace("received insurance proceeds for lost profits of $4.0 million",
                       "expects insurance proceeds for lost profits of $4.0 million") for x in good],
        ):
            with self.assertRaises(ValueError):
                parse_pages(c,pages,"sha")

    def test_source_metrics_evidence_rows_have_independent_id_and_event_stable(self):
        a,b=SOURCE_DOCS
        fa,_=parse_pages(a,make_pages(a,year2024()),"sha2024")
        fb,_=parse_pages(b,make_pages(b,q22025()),"sha2025")
        self.assertEqual(len({x["evidence_key"] for x in fa+fb}),7)
        self.assertEqual(len({x["underlying_incident_key"] for x in fa+fb}),1)
        self.assertEqual(sum(x["reported_amount_usd"] for x in fa+fb
                             if x["issuer_reports_received_lost_profit_bi_proceeds"]),4_000_000)
        self.assertEqual(sum(x["reported_amount_usd"] for x in fa+fb
                             if x["financial_metric_kind"]=="REMAINING_INSURANCE_RECEIVABLE"),6_400_000)
        # The sum of balances is NOT the valid total receivable; periods are separate.
        self.assertEqual([x["accounting_period_or_window"] for x in fa+fb
                          if x["financial_metric_kind"]=="REMAINING_INSURANCE_RECEIVABLE"],
                         ["2024_12_31_BALANCE","2025_06_30_BALANCE"])

    def test_blocked_source_does_not_claim_success_or_durable_index(self):
        with tempfile.TemporaryDirectory() as t, patch(
            "facilityrisk.lane_d.ingest_crane_bi_pdf.fetch_pdf",
            side_effect=ValueError("Publisher HTTP 403 Forbidden")
        ):
            with self.assertRaisesRegex(RuntimeError,"source gate not met"):
                run(Path(t),cases=SOURCE_DOCS,min_sources=2)
            import json
            manifest=json.loads((Path(t)/"manifest.json").read_text())
            self.assertEqual(manifest["pdf_documents_downloaded_and_verified"],0)
            self.assertEqual(manifest["financial_records_extracted"],0)
            self.assertEqual(manifest["deployed"],0)
            self.assertEqual(manifest["durable_backend_indexed"],0)
            self.assertEqual(len(manifest["rejected_or_blocked"]),2)


if __name__=="__main__":
    unittest.main()
