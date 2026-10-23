"""Issuer BI read-only query tests: original financial grain and no paid claims."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from facilityrisk.lane_d.query_issuer_bi_context import get_issuer_bi_context


def add_crane(path):
    with sqlite3.connect(path) as c:
        c.execute("""CREATE TABLE source_financial_observations (
            evidence_key TEXT PRIMARY KEY,source_id TEXT,issuer_cik TEXT,
            underlying_event_key TEXT,financial_metric_kind TEXT,
            reported_amount_usd INTEGER,accounting_period TEXT,
            document_sha256 TEXT,source_pdf_page INTEGER,record_json TEXT)""")
        rows=[]
        for i,(kind,amt,period,basis,paid) in enumerate([
            ("RECEIVED_BI_PROCEEDS_FOR_LOST_PROFITS",4000000,"2025_Q2","ISSUER_REPORTS_RECEIVED_BI_PROCEEDS",True),
            ("REMAINING_INSURANCE_RECEIVABLE",3600000,"2025_06_30_BALANCE","RECEIVABLE_NOT_RECEIVED",False),
        ]):
            key=f"crane-{i}"
            source={
                "evidence_key":key,"source_document_sha256":"original-sha-2025",
                "reported_amount_usd":amt,"accounting_period_or_window":period,
                "underlying_incident_key":"crane-marion-helene-2024",
                "original_document_url":"https://investors.craneco.com/2025-q2.pdf",
                "basis":basis,"issuer_reports_received_lost_profit_bi_proceeds":paid,
            }
            rows.append((key,"crane2025q2","1944013","crane-marion-helene-2024",
                         kind,amt,period,"original-sha-2025",24,json.dumps(source)))
        c.executemany("INSERT INTO source_financial_observations VALUES (?,?,?,?,?,?,?,?,?,?)",rows)


def add_pebblebrook(path):
    with sqlite3.connect(path) as c:
        c.execute("""CREATE TABLE source_financial_observations (
            evidence_key TEXT PRIMARY KEY,source_id TEXT,event_key TEXT,
            accounting_period TEXT,kind TEXT,amount_usd INTEGER,
            original_sha256 TEXT,raw_json TEXT)""")
        rows=[]
        for i,(kind,amt,period,basis) in enumerate([
            ("RECOGNIZED_BI_INSURANCE_INCOME",12700000,"2025_FY","ANNUAL_RECOGNIZED_AMOUNT"),
            ("RECOGNIZED_BI_INSURANCE_INCOME_Q4_COMPONENT",3100000,"2025_Q4","SUBSET_OF_2025_FY"),
        ]):
            key=f"peb-{i}"
            source={
                "evidence_key":key,"document_sha256":"original-sha-peb",
                "amount_usd":amt,"accounting_period":period,
                "underlying_event_key":"laplaya-helene-milton-2024",
                "first_party_source_url":"https://investor.pebblebrookhotels.com/publisher",
                "issuer_cik":"1474098","inclusion_scope":basis,
            }
            rows.append((key,"pebblebrook2025fy","laplaya-helene-milton-2024",
                         period,kind,amt,"original-sha-peb",json.dumps(source)))
        c.executemany("INSERT INTO source_financial_observations VALUES (?,?,?,?,?,?,?,?)",rows)


class BIContextTests(unittest.TestCase):
    def make(self,t):
        p=Path(t)
        crane=p/"crane.sqlite";peb=p/"peb.sqlite"
        add_crane(crane);add_pebblebrook(peb)
        return crane,peb

    def test_two_issuers_keep_nonadditive_financial_classes_distinct(self):
        with tempfile.TemporaryDirectory() as t:
            crane,peb=self.make(t)
            output=get_issuer_bi_context(crane_db=crane,pebblebrook_db=peb)
            self.assertEqual(len(output["returned_financial_source_observations"]),4)
            self.assertEqual(sum(x["source_financial_observations_in_stage"] for x in output["source_kind_counts"].values()),4)
            self.assertEqual(output["independently_verified_insurer_payment_records"],0)
            self.assertEqual(output["deployed"],0)
            sources=output["returned_financial_source_observations"]
            self.assertEqual(len({r["issuer"] for r in sources}),2)
            self.assertTrue(all(r["carrier_payment_independently_verified"] is False for r in sources))
            self.assertTrue(all(r["facility_power_outage_independently_verified"] is False for r in sources))
            self.assertEqual(len([r for r in sources if r["cash_received_for_lost_profits_reported_by_issuer"]]),1)
            self.assertEqual({r["reporting_basis"] for r in sources},
                {"ISSUER_REPORTS_RECEIVED_BI_PROCEEDS","RECEIVABLE_NOT_RECEIVED",
                 "ANNUAL_RECOGNIZED_AMOUNT","SUBSET_OF_2025_FY"})

    def test_explicit_event_and_issuer_scoping(self):
        with tempfile.TemporaryDirectory() as t:
            crane,peb=self.make(t)
            output=get_issuer_bi_context(
                crane_db=crane,pebblebrook_db=peb,
                event_key="laplaya-helene-milton-2024")
            self.assertEqual(len(output["returned_financial_source_observations"]),2)
            self.assertEqual(output["source_kind_counts"]["Crane Company"]["source_financial_observations_in_stage"],0)
            self.assertTrue(all(x["issuer"]=="Pebblebrook Hotel Trust" for x in output["returned_financial_source_observations"]))
            byissuer=get_issuer_bi_context(
                crane_db=crane,pebblebrook_db=peb,issuer="Crane Company")
            self.assertEqual(set(byissuer["source_kind_counts"]),{"Crane Company"})

    def test_bound_on_each_source_and_missing_data_not_site_zero(self):
        with tempfile.TemporaryDirectory() as t:
            crane,peb=self.make(t)
            output=get_issuer_bi_context(crane_db=crane,pebblebrook_db=peb,limit=1)
            self.assertEqual(len(output["returned_financial_source_observations"]),2)
            self.assertTrue(all(x["truncated"] for x in output["source_kind_counts"].values()))
            self.assertTrue(output["records_are_not_independently_verified_paid_insurance_claims"])
            self.assertEqual(output["independently_verified_facility_power_outages"],0)

    def test_tampered_financial_amount_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            crane,peb=self.make(t)
            with sqlite3.connect(crane) as c:
                c.execute("UPDATE source_financial_observations SET reported_amount_usd=999 WHERE evidence_key='crane-0'")
            with self.assertRaisesRegex(ValueError,"inconsistent"):
                get_issuer_bi_context(crane_db=crane)

    def test_fail_closed_input_injection_and_missing_paths(self):
        with tempfile.TemporaryDirectory() as t:
            crane,peb=self.make(t)
            for bad in ("Unknown Corporation","Crane Company' OR 1=1 --"):
                with self.assertRaises(ValueError):
                    get_issuer_bi_context(crane_db=crane,issuer=bad)
            for bad in ("bad' OR 1=1 --","",123,"HELENE_2024"):
                with self.assertRaises(ValueError):
                    get_issuer_bi_context(crane_db=crane,event_key=bad)
            for bad in (0,101,-1,1.2,True):
                with self.assertRaises(ValueError):
                    get_issuer_bi_context(crane_db=crane,limit=bad)
            with self.assertRaises(ValueError):
                get_issuer_bi_context()
            with self.assertRaises(FileNotFoundError):
                get_issuer_bi_context(crane_db=Path(t)/"absent.sqlite")


if __name__=="__main__":
    unittest.main()
