"""Lane D EIA county territory candidates: no automatic physical facility matching."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from facilityrisk.lane_d.query_eia_service_territory import service_territory_candidates


class EIACountyCandidateTests(unittest.TestCase):
    def make_db(self, path):
        with sqlite3.connect(path) as db:
            db.execute("""CREATE TABLE source_observations (
                ingestion_row_key TEXT PRIMARY KEY,
                source_kind TEXT NOT NULL,
                reporting_year INTEGER NOT NULL,
                utility_id TEXT,state TEXT,county TEXT,
                source_member TEXT,source_sheet TEXT,source_row INTEGER,
                row_sha256 TEXT,original_row_json TEXT)""")
            rows=[
                ("t1","service_territory",2025,"101","WA","Pierce","Service_Territory_2025.xlsx","Counties_States",10,"sh1",json.dumps(["2025","101","Public Electric One","Y","WA","Pierce"])),
                ("t2","service_territory",2025,"202","WA","Pierce","Service_Territory_2025.xlsx","Counties_States",11,"sh2",json.dumps(["2025","202","Public Electric Two","Y","WA","Pierce"])),
                ("t3","service_territory",2025,"303","OR","Pierce","Service_Territory_2025.xlsx","Counties_States",12,"sh3",json.dumps(["2025","303","Different State","Y","OR","Pierce"])),
                ("t4","service_territory",2025,"404","WA","Piercefield","Service_Territory_2025.xlsx","Counties_States",13,"sh4",json.dumps(["2025","404","Different County","Y","WA","Piercefield"])),
                ("r1","reliability",2025,"101","WA",None,"Reliability_2025.xlsx","Reliability_States",100,"rh1",json.dumps(["2025","101","Public Electric One","WA","Investor Owned","600.5","0.6"])),
                ("r2","reliability",2025,"101","OR",None,"Reliability_2025.xlsx","Reliability_States",101,"rh2",json.dumps(["2025","101","Public Electric One","OR","Investor Owned","900.5","0.9"])),
            ]
            db.executemany("INSERT INTO source_observations VALUES (?,?,?,?,?,?,?,?,?,?,?)",rows)

    def test_two_provider_candidates_not_auto_matched_and_link_reliability_by_state(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"eia.db";self.make_db(p)
            r=service_territory_candidates(p,"WA","Pierce")
            self.assertEqual(r["source_territory_observations"],2)
            self.assertEqual(r["candidate_records_returned"],2)
            self.assertEqual([v["original_source_utility_id"] for v in r["returned_candidates"]],["101","202"])
            self.assertEqual(len(r["returned_candidates"][0]["same_state_utility_reliability_sources"]),1)
            self.assertEqual(r["returned_candidates"][0]["same_state_utility_reliability_sources"][0]["original_positional_values"][5],"600.5")
            self.assertEqual(len(r["returned_candidates"][1]["same_state_utility_reliability_sources"]),0)
            self.assertTrue(all(not x["site_serving_utility_verified"] for x in r["returned_candidates"]))
            self.assertEqual(r["verified_insured_business_interruption_claims"],0)
            self.assertEqual(r["verified_facility_outages"],0)
            self.assertEqual(r["source_area_match_method"],"CASE_INSENSITIVE_EXACT_SOURCE_COUNTY_TEXT")

    def test_case_insensitive_name_and_multiple_candidate_truncation_explicit(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"eia.db";self.make_db(p)
            r=service_territory_candidates(p,"WA","pIeRcE",limit=1)
            self.assertEqual(r["source_territory_observations"],2)
            self.assertEqual(r["candidate_records_returned"],1)
            self.assertTrue(r["truncated"])

    def test_disallow_fuzzy_and_wrong_state_matches(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"eia.db";self.make_db(p)
            self.assertEqual(service_territory_candidates(p,"WA","Pier")["source_territory_observations"],0)
            self.assertEqual(service_territory_candidates(p,"VA","Pierce")["source_territory_observations"],0)

    def test_invalid_sources_and_input_injection_fail_closed(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"eia.db";self.make_db(p)
            for state,county,limit in [("Washington","Pierce",50),("wa","Pierce",50),("WA","x",50),("WA","Pierce\nKing",50),("WA","Pierce",0),("WA","Pierce",101)]:
                with self.subTest(state=state,county=county,limit=limit):
                    with self.assertRaises(ValueError):
                        service_territory_candidates(p,state,county,limit)
            self.assertEqual(service_territory_candidates(p,"WA","Pierce' OR 1=1 --")["source_territory_observations"],0)
            with self.assertRaises(FileNotFoundError):
                service_territory_candidates(Path(t)/"missing.sqlite","WA","Pierce")


if __name__=="__main__":
    unittest.main()
