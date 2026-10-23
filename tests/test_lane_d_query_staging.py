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
    def create_direct_odin(self,path):
        with sqlite3.connect(path) as db:
            db.execute("""CREATE TABLE source_observations (
                original_position INTEGER,native_mrid TEXT,native_county_fips TEXT,
                native_eia_utility_id TEXT,reported_start TEXT,meters_affected INTEGER,
                snapshot_utc TEXT,original_row_sha256 TEXT,is_exact_duplicate INTEGER)""")
            db.executemany("INSERT INTO source_observations VALUES (?,?,?,?,?,?,?,?,?)",[
                (1,"mrid-1","01001","123",None,211,"2026-10-23T16:00:00Z","fp1",0),
                (2,"mrid-1","01001","123",None,211,"2026-10-23T16:00:00Z","fp1",1),
                (3,None,"01001","456","2026-10-23T15:00:00Z",26,
                    "2026-10-23T16:00:00Z","fp2",0),
                (4,"mrid-3","01003","789","2026-10-23T15:03:00Z",10,
                    "2026-10-23T16:00:00Z","fp3",0),
            ])

    def test_direct_firstparty_odin_rows_exclude_exact_duplicates_and_leave_site_unknown(self):
        with tempfile.TemporaryDirectory() as t:
            o=Path(t)/"direct.sqlite"
            self.create_direct_odin(o)
            out=get_county_context("01001",odin_direct_db=o,limit=30)
            self.assertEqual(out["candidate_counts"]["odin_firstparty_public_county_snapshot_raw_rows"],3)
            self.assertEqual(out["candidate_counts"]["odin_firstparty_exact_duplicate_rows_excluded"],1)
            self.assertEqual(len(out["returned_findings"]),2)
            self.assertTrue(all(x["category"]=="PUBLIC_COUNTY_OUTAGE_SNAPSHOT"
                                for x in out["returned_findings"]))
            self.assertTrue(all(x["publisher"]=="DOE/ORNL ODIN FIRST_PARTY"
                                for x in out["returned_findings"]))
            self.assertTrue(all(x["insured_facility_outage_verified"] is False
                                for x in out["returned_findings"]))
            self.assertTrue(all(x["site_utility_assignment_verified"] is False
                                for x in out["returned_findings"]))
            self.assertEqual(out["verified_business_interruption_claims"],0)

    def test_refuse_mixing_firstparty_odin_with_mirror(self):
        with tempfile.TemporaryDirectory() as t:
            o=Path(t)/"odin_direct.sqlite";m=Path(t)/"odin_mirror.sqlite"
            self.create_direct_odin(o);self.create_odin(m)
            with self.assertRaisesRegex(ValueError,"overlapping feeds"):
                get_county_context("01001",odin_db=m,odin_direct_db=o)

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
