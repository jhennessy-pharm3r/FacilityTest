"""ORNL ODIN source participant feed health is NOT verified facility electrical service."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from facilityrisk.lane_d.ingest_odin_participants import parse,run


def feed(**updates):
    data={
        "dataId":"feed-A","eiaId":"803",
        "name":"ARIZONA PUBLIC SERVICE CO",
        "dataResolution":"county","receivedDate":"2026-10-23T14:00:00Z",
        "hasError":False,"totalOutages":5,"vendor":"Test vendor",
        "outageFeed":"https://utility.example/outage/endpoint",
    }
    data.update(updates)
    return data


class UtilityFeedTests(unittest.TestCase):
    def test_native_ids_and_feed_health_not_site_assignment(self):
        a,b,stat=parse(json.dumps([feed(),feed(dataId="feed-B",eiaId=None,receivedDate=None,totalOutages=None)]).encode(),
                       "2026-10-23T16:00:00Z")
        self.assertEqual((len(a),len(b)),(2,0))
        self.assertEqual(stat["distinct_native_eia_utility_ids"],1)
        self.assertEqual(stat["missing_eia_utility_ids"],1)
        self.assertEqual(stat["null_reported_receive_timestamps"],1)
        self.assertFalse(a[0]["insured_site_utility_assignment_verified"])
        self.assertEqual(a[0]["native_data_id"],"feed-A")
        self.assertEqual(a[0]["reported_total_outages"],5)

    def test_exact_repeated_feed_source_recognized_but_original_position_retained(self):
        a,b,stat=parse(json.dumps([feed(),feed()]).encode(),"2026-10-23T16:00:00Z")
        self.assertEqual(stat["exact_source_row_duplicates"],1)
        self.assertEqual(a[1]["duplicate_of_source_row"],1)
        self.assertNotEqual(a[0]["source_row_key"],a[1]["source_row_key"])

    def test_reject_malformed_native_data_id_and_negative_count(self):
        a,b,stat=parse(json.dumps([feed(),feed(dataId=""),feed(dataId="other",totalOutages=-3)]).encode(),"2026-10-23T16:00:00Z")
        self.assertEqual((len(a),len(b)),(1,2))
        self.assertEqual(stat["distinct_native_data_ids"],1)
        self.assertEqual(stat["rejection_reasons"],{
            "missing_native_data_id":1,
            "invalid_outage_count":1,
        })

    def test_actual_index_is_local_review_only_and_correctly_reconciles(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);raw=p/"original.json"
            raw.write_text(json.dumps([feed(),feed(dataId="feed-C",eiaId=None,totalOutages=None)]))
            out=p/"out"
            m=run(raw,out)
            self.assertEqual((m["records_downloaded"],m["normalized_accepted"],m["indexed_local_sqlite"]),(2,2,2))
            self.assertEqual(m["verified_insured_site_utility_assignments"],0)
            self.assertEqual(m["durable_backend_indexed"],0)
            self.assertEqual(m["deployed"],0)
            with sqlite3.connect(out/"odin_utility_status_staging.sqlite") as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0],"ok")
                self.assertEqual(db.execute("SELECT count(*) FROM utility_feeds").fetchone()[0],2)

    def test_fail_closed_on_empty_or_wrong_json_shape(self):
        for raw in ('[]','{"items":[]}','{}',''):
            with self.assertRaises(ValueError):
                parse(raw.encode(),"2026-10-23T16:00:00Z")


if __name__=="__main__":
    unittest.main()
