"""DOE OE417 annual read-only source adapter original rows and unknown start dates."""
from pathlib import Path
import sqlite3
import tempfile
import unittest

from facilityrisk.lane_d.query_oe417_annual import annual_context


def seed(path):
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE source_observations (
            source_row_key TEXT,original_position INTEGER,event_date TEXT,
            restoration_date TEXT,source_area_text TEXT,source_event_type TEXT,
            source_nerc_region TEXT,source_alert_criteria TEXT,
            reported_customers INTEGER,reported_demand_mw_decimal TEXT,
            exact_duplicate_source INTEGER,duplicate_of_source_position INTEGER,
            original_row_sha256 TEXT,raw_json TEXT)""")
        rows=[
            ("oe-1",1,"2023-01-12",None,"Washington: King County;","Vandalism","WECC",
             "Physical attack",None,None,0,None,"sha1","{}"),
            ("oe-2",2,"2023-01-12",None,"Washington: King County;","Vandalism","WECC",
             "Physical attack",None,None,1,1,"sha1","{}"),
            ("oe-3",3,None,None,"California: Napa County;","Severe Weather","WECC",
             "Weather event",123,"3.5",0,None,"sha3","{}"),
            ("oe-4",4,"2023-09-01","2023-09-02","New York: Queens","Severe Weather","NPCC",
             "Transmission interruption",200,"100",0,None,"sha4","{}"),
        ]
        db.executemany("INSERT INTO source_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",rows)


class OfficialOE417QueryTests(unittest.TestCase):
    def test_source_only_without_making_site_outage_claims(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"oe417.sqlite";seed(p)
            out=annual_context(p)
            self.assertEqual(out["original_source_rows_total"],4)
            self.assertEqual(out["exact_duplicate_original_rows_withheld"],1)
            self.assertEqual(out["matching_content_distinct_source_rows"],3)
            self.assertEqual(len(out["source_records"]),3)
            self.assertEqual(out["independently_confirmed_insured_facility_outages"],0)
            self.assertTrue(all(not r["insured_site_electric_outage_verified"] for r in out["source_records"]))
            self.assertTrue(all(r["publisher_native_event_id"] is None for r in out["source_records"]))
            self.assertEqual(out["deployed"],0)

    def test_undated_annual_source_is_not_imputed_to_2023(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"oe417.sqlite";seed(p)
            unknown=annual_context(p,date_state="undated")
            self.assertEqual(unknown["matching_content_distinct_source_rows"],1)
            self.assertEqual(unknown["source_records"][0]["date_status"],"NOT_REPORTED")
            self.assertIsNone(unknown["source_records"][0]["reported_incident_start_date"])
            by_year=annual_context(p,event_year=2023)
            self.assertEqual(by_year["matching_content_distinct_source_rows"],2)
            self.assertEqual({r["date_status"] for r in by_year["source_records"]},{"REPORTED"})

    def test_type_filter_is_exact_and_limit_explicit(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"oe417.sqlite";seed(p)
            r=annual_context(p,event_type="Severe Weather",limit=1)
            self.assertEqual(r["matching_content_distinct_source_rows"],2)
            self.assertEqual(r["returned"],1)
            self.assertTrue(r["truncated"])
            self.assertEqual(annual_context(p,event_type="Weather")["returned"],0)

    def test_fail_closed_on_unreviewed_year_input_injection_or_missing_file(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"oe417.sqlite";seed(p)
            for kwargs in (
                {"event_year":1890},{"event_year":True},
                {"date_state":"unknown"},{"event_year":2023,"date_state":"undated"},
                {"limit":101},{"limit":0},{"limit":True},
                {"event_type":"Weather' OR 1=1 --\n"},
            ):
                with self.subTest(**kwargs):
                    with self.assertRaises(ValueError):
                        annual_context(p,**kwargs)
            with self.assertRaises(FileNotFoundError):
                annual_context(Path(t)/"missing.db")


if __name__=="__main__":
    unittest.main()
