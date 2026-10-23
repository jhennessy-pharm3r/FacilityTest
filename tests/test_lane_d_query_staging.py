"""Coordinator integration-ready source-only query contract regressions."""
from pathlib import Path
import sqlite3
import tempfile
import unittest

from facilityrisk.lane_d.query_staging import get_county_context,validate_fips


class CountyQueryTests(unittest.TestCase):
    def create_pnnl(self,path):
        with sqlite3.connect(path) as db:
            db.execute("""CREATE TABLE source_observations (
                source_kind TEXT,dataset_year INTEGER,county_fips TEXT,state TEXT,county TEXT,
                reported_start TEXT,reported_duration_hours REAL,reported_mean_customers REAL,
                native_event_id TEXT,source_member TEXT,source_line_number INTEGER,source_row_sha256 TEXT)""")
            db.executemany("INSERT INTO source_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",[
                ("county_episode",2014,"01001","Alabama","Autauga","2014-12-24T13:45:00",2.5,631.3,None,"eaglei_outages_2014_merged.csv",3,"fp1"),
                ("county_episode",2015,"01001","Alabama","Autauga","2015-01-02T10:00:00",1.0,100,None,"eaglei_outages_2015_merged.csv",6,"fp2"),
                ("correlation_8h_sensitivity",2015,"01001","Alabama","Autauga","2015-01-02T10:00:00",1.0,100,"E1","lag.csv",2,"fp3"),
                ("county_episode",2014,"01003","Alabama","Baldwin","2014-12-24T15:45:00",2.5,7,None,"data.csv",7,"fp4"),
            ])
    def create_odin(self,path):
        with sqlite3.connect(path) as db:
            db.execute("""CREATE TABLE source_observations (
                original_row_position INTEGER,native_utility_id TEXT,county_fips TEXT,
                reported_state TEXT,reported_county TEXT,reported_start_time TEXT,
                snapshot_utc TEXT,source_sha256 TEXT)""")
            db.executemany("INSERT INTO source_observations VALUES (?,?,?,?,?,?,?,?)",[
                (1,"123","01001","Alabama","Autauga",None,"2026-10-23T15:00:00Z","fp1"),
                (2,"456","19155","Iowa","Pottawattamie","2026-10-23T14:00:00Z","2026-10-23T15:00:00Z","fp2"),
            ])
    def test_candidate_only_and_distinct_time_series(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"pnnl.sqlite";o=Path(t)/"odin.sqlite"
            self.create_pnnl(p);self.create_odin(o)
            out=get_county_context("01001",p,o,year=2015)
            self.assertEqual(out["candidate_counts"],{
                "pnnl_historical_county_episodes":1,
                "odin_public_county_snapshot_rows":1,
            })
            self.assertEqual(len(out["returned_findings"]),2)
            self.assertTrue(all(not x["insured_facility_outage_verified"] for x in out["returned_findings"]))
            self.assertEqual(out["verified_business_interruption_claims"],0)
            self.assertEqual(out["returned_findings"][0]["source_year"],2015)
            self.assertEqual(out["returned_findings"][1]["reported_start_time"],None)
    def test_reject_inferred_or_invalid_fips(self):
        for v in ("1001",1001,"CA","01001' OR 1=1 --",""):
            with self.subTest(v=v):
                with self.assertRaises(ValueError):
                    validate_fips(v)
        with self.assertRaises(ValueError):
            get_county_context("01001",limit=500)
        with self.assertRaises(ValueError):
            get_county_context("01001",year=2026)
    def test_missing_index_fails_closed(self):
        with self.assertRaises(FileNotFoundError):
            get_county_context("01001",pnnl_db="/not-present/lane-d.sqlite")


if __name__=="__main__":
    unittest.main()
