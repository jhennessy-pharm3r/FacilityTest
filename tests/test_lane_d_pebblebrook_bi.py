"""Hotel-sector issuer BI recognized income, annual/quarter non-additive fixtures."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from facilityrisk.lane_d.ingest_pebblebrook_bi import CASES,inspect,run


def raw(case,phrase):
    return ("<!doctype html><html><body><h1>"+case["expected_title"]+"</h1><p>"+
            case["release_date"]+"</p><p>LaPlaya Beach Resort & Club in Naples "
            "has suffered interruption and flooding. Business interruption insurance " +
            phrase + "</p>" + "<footer>Issuer governance information. "*15+
            "</footer></body></html>").encode()


def report2024():
    return (
        "Hurricane Ian. In Q4 2024, the Company finalized its claim. "
        "As a result, the Company realized an additional $5.4 million in unexpected "
        "income. This increased total BI income in 2024 to $23.8 million. "
        "Including the $33.0 million of BI income recognized in 2023, the "
        "company realized over $56 million."
    )


def report2025():
    return (
        "Update on LaPlaya Recovery from Named Storms. "
        "LaPlaya required full restoration following Hurricanes Helene and Milton. "
        "The Company recognized $3.1 million of business interruption (BI) insurance "
        "income in the fourth quarter, bringing the full-year BI insurance recovery "
        "to $12.7 million. The 2024 property and BI insurance hurricane claims now fully settled."
    )


class HotelIncomeTests(unittest.TestCase):
    def test_recognized_2024_and_2023_with_q4_subset(self):
        c=CASES[0]
        items,report=inspect(c,raw(c,report2024()),c["source_url"],200)
        self.assertEqual(len(items),3)
        self.assertEqual(report["reporting_year"],2024)
        self.assertEqual({i["accounting_period"]:i["amount_usd"] for i in items},{
            "2024_FY":23800000,"2024_Q4":5400000,"2023_FY":33000000})
        self.assertEqual(next(i for i in items if i["accounting_period"]=="2024_Q4")["inclusion_scope"],"SUBSET_OF_2024_FY")
        self.assertTrue(all(not i["carrier_claim_payment_independently_verified"] for i in items))

    def test_2025_helene_milton_group_distinct_from_ian_and_recognition_not_cash(self):
        c=CASES[1]
        items,report=inspect(c,raw(c,report2025()),c["source_url"],200)
        self.assertEqual(len(items),2)
        self.assertEqual({i["accounting_period"]:i["amount_usd"] for i in items},{
            "2025_FY":12700000,"2025_Q4":3100000})
        self.assertEqual(len({i["underlying_event_key"] for i in items}),1)
        self.assertEqual({i["inclusion_scope"] for i in items},{"ANNUAL_RECOGNIZED_AMOUNT","SUBSET_OF_2025_FY"})
        self.assertTrue(all(not i["cash_received_by_issuer_independently_verified"] for i in items))

    def test_source_wrong_domain_or_missing_period_fails_closed(self):
        c=CASES[0]
        for data in (
            raw(c,report2024()).replace(b"$23.8 million",b"$44.8 million"),
            raw(c,report2024()).replace(b"February 26, 2025",b"February 26, 2024"),
            raw(c,report2024()).replace(b"Hurricane Ian",b"Hurricane Helene"),
        ):
            with self.assertRaises(ValueError):
                inspect(c,data,c["source_url"],200)
        with self.assertRaises(ValueError):
            inspect(c,raw(c,report2024()),"https://other.example/",200)

    def test_both_publisher_documents_one_accounting_item_per_period(self):
        a=CASES[0];b=CASES[1]
        with tempfile.TemporaryDirectory() as t, patch(
            "facilityrisk.lane_d.ingest_pebblebrook_bi.retrieve",
            side_effect=[
              inspect(a,raw(a,report2024()),a["source_url"],200),
              inspect(b,raw(b,report2025()),b["source_url"],200),
            ]):
            m=run(Path(t),min_sources=2)
            self.assertEqual((m["downloaded_publisher_documents"],
                              m["financial_statement_records_normalized"],
                              m["financial_statement_records_staged_sqlite"]),(2,5,5))
            self.assertEqual(m["distinct_named_storm_event_groups"],2)
            self.assertEqual(m["verified_annual_income_2024_ian_usd"],23800000)
            self.assertEqual(m["verified_annual_income_2025_helene_milton_usd"],12700000)
            self.assertEqual(m["independently_insurer_verified_paid_bi_claims"],0)
            self.assertEqual(m["deployed"],0)

    def test_blocked_external_source_is_not_success(self):
        with tempfile.TemporaryDirectory() as t, patch(
            "facilityrisk.lane_d.ingest_pebblebrook_bi.retrieve",side_effect=ValueError("403")
        ):
            with self.assertRaises(RuntimeError):
                run(Path(t))
            m=json.loads((Path(t)/"manifest.json").read_text())
            self.assertEqual(m["downloaded_publisher_documents"],0)
            self.assertEqual(m["financial_statement_records_staged_sqlite"],0)
            self.assertEqual(m["deployed"],0)


if __name__=="__main__":
    unittest.main()
