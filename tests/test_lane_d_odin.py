"""ORNL ODIN atomic official public county outage snapshot regression fixtures."""
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
import tempfile
import sqlite3
import unittest
from facilityrisk.lane_d.ingest_odin import parse,run,sha256,canonical


def rec(**overrides):
    o={
        "utility_id":"0012","communitydescriptor":"01001","metersaffected":10,
        "reportedstarttime":"2026-10-22T11:00:00+00:00",
        "county":"Autauga","state":"Alabama","statuskind":"Active",
        "name":"Utility A","incident": "EVT-02","geom":None,
        "geo_point_2d":None,"estimatedrestorationtime":None,
    }
    o.update(overrides)
    return o


class ODINTests(unittest.TestCase):
    def test_county_snapshot_parses_without_facility_inference(self):
        good=[rec(),rec(utility_id="123",communitydescriptor="19155",
                        county="Pottawattamie",state="Iowa",metersaffected=None,
                        reportedstarttime="2026-10-20T10:00:00Z")]
        a,b,q=parse(json.dumps(good).encode(),"2026-10-23T15:00:00+00:00")
        self.assertEqual((len(a),len(b)),(2,0))
        self.assertEqual(q["distinct_county_fips"],2)
        self.assertEqual(q["missing_affected_meters"],1)
        self.assertEqual(a[0]["native_county_fips"],"01001")
        self.assertFalse(a[0]["facility_outage_verified"])
        self.assertFalse(a[0]["business_interruption_verified"])
        self.assertIsNone(a[1]["reported_meters_affected"])
        self.assertEqual(a[0]["native_incident_id"],"EVT-02")

    def test_invalid_rows_rejected_keeping_raw(self):
        data=[rec(),rec(communitydescriptor="123"),rec(metersaffected=-2),
              rec(utility_id=""),rec(reportedstarttime="bad"),{"other":"data"},3]
        a,b,q=parse(json.dumps(data).encode(),"2026-10-23T15:00:00Z")
        self.assertEqual((len(a),len(b)),(1,6))
        self.assertEqual(sum(q["rejection_reasons"].values()),6)
        self.assertTrue(all("raw" in x for x in b))

    def test_raw_to_stage_count_and_no_deployment(self):
        rows=[rec(),rec(utility_id="3",communitydescriptor="12086",county="Miami-Dade",state="Florida")]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            input_file=root/"input.json"
            input_file.write_text(json.dumps(rows))
            result=run(input_file,root/"stage",expected_total=2)
            self.assertEqual(result["downloaded_records"],2)
            self.assertEqual(result["normalized_records"],2)
            self.assertEqual(result["locally_indexed_records"],2)
            self.assertEqual(result["durable_backend_indexed"],0)
            self.assertEqual(result["site_outages_verified"],0)
            self.assertEqual(result["deployed"],0)
            self.assertEqual(result["raw_response_sha256"],sha256(input_file.read_bytes()))
            with sqlite3.connect(root/"stage"/"odin_county_outage_staging.sqlite") as db:
                self.assertEqual(db.execute("select count(*) from source_observations").fetchone()[0],2)
                self.assertEqual(db.execute("select county_fips from source_observations where native_utility_id='0012'").fetchone()[0],"01001")
            with self.assertRaisesRegex(ValueError,"mismatches"):
                run(input_file,root/"bad",expected_total=3)

    def test_duplicate_raw_records_flagged_not_assumed_distinct_events(self):
        items=[rec(),rec()]
        a,b,q=parse(json.dumps(items).encode(),"2026-10-23T15:00:00Z")
        self.assertEqual(q["exact_row_duplicate_fingerprints"],1)
        self.assertNotEqual(a[0]["source_row_key"],a[1]["source_row_key"])
        self.assertEqual(a[0]["native_incident_id"],a[1]["native_incident_id"])

    def test_invalid_future_and_geometry_independent(self):
        data=[rec(reportedstarttime="2045-01-01T00:00:00Z"),
              rec(communitydescriptor="19155",geom={"type":"Feature"},metersaffected="NaN")]
        with self.assertRaisesRegex(ValueError,"No valid county"):
            parse(json.dumps(data).encode(),"2026-10-23T15:00:00Z")


if __name__=="__main__":
    unittest.main()
