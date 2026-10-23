"""Official 2023 DOE OE417 annual summary source-preserving ingestion QA."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from facilityrisk.lane_d.ingest_oe417_annual import parse,run,DATASET_ID,EXPECTED_FIELDS,digest


def row(**updates):
    raw={
        "event_month":"January",
        "date_event_began":"2023-01-12",
        "time_event_began":None,
        "date_of_restoration":None,
        "time_of_restoration":None,
        "area_affected":"Washington: King County;",
        "nerc_region":"WECC",
        "alert_criteria":"Damage or destruction of its Facility that results from actual or suspected intentional human action.",
        "event_type":"Vandalism",
        "demand_loss_mw":None,
        "number_of_customers_affected":None,
    }
    raw.update(updates)
    return raw


META={"dataset_id":DATASET_ID,"metas":{"default":{"license":"Public Domain"}}}


class OE417AnnualTests(unittest.TestCase):
    def test_metadata_data_use_and_schema_exact(self):
        a,r,m=parse(json.dumps([row()]).encode(),META)
        self.assertEqual(len(a),1)
        self.assertFalse(r)
        self.assertEqual(m["source_calendar_year_counts"],{"2023":1})
        self.assertEqual(m["missing_demand_mw"],1)
        self.assertEqual(m["missing_reported_customer_count"],1)
        self.assertEqual(m["records_with_site_coordinates"],0)
        self.assertIsNone(a[0]["publisher_native_event_id"])
        self.assertFalse(a[0]["insured_business_interruption_claim_confirmed"])
        self.assertEqual(a[0]["original_source_row"]["area_affected"],"Washington: King County;")
        for metadata in (
            {"dataset_id":DATASET_ID,"metas":{"default":{"license":"Proprietary"}}},
            {"dataset_id":"another-dataset","metas":{"default":{"license":"Public Domain"}}},
            {"dataset_id":DATASET_ID},
        ):
            with self.assertRaises(ValueError):
                parse(json.dumps([row()]).encode(),metadata)

    def test_undated_official_row_remains_accepted_unassessed_event_time(self):
        items=[row(date_event_began=None,event_type="Severe Weather"),
               row(date_event_began="",event_type="Transmission Interruption")]
        a,r,stats=parse(json.dumps(items).encode(),META)
        self.assertEqual((len(a),len(r)),(2,0))
        self.assertEqual(stats["missing_event_start_date_preserved_as_unknown"],2)
        self.assertEqual(stats["source_calendar_year_counts"],{})
        self.assertTrue(all(x["event_date_source_status"]=="NOT_REPORTED" for x in a))
        self.assertTrue(all(x["source_event_year"] is None for x in a))
        self.assertTrue(all(not x["site_electric_outage_verified"] for x in a))

    def test_preserve_native_missing_time_and_nonnegative_customers(self):
        a,r,m=parse(json.dumps([row(number_of_customers_affected=1242,demand_loss_mw=4.25,date_of_restoration="2023-01-14")]).encode(),META)
        self.assertEqual((len(a),len(r)),(1,0))
        self.assertEqual(a[0]["reported_customers_affected"],1242)
        self.assertEqual(a[0]["reported_demand_loss_mw_decimal"],"4.25")
        self.assertIsNone(a[0]["source_time_event_began"])
        self.assertEqual(a[0]["restoration_date_source"],"2023-01-14")
        self.assertEqual(m["missing_restoration_date"],0)
        self.assertEqual(m["numeric_reported_customer_count"],1)

    def test_exact_identical_source_rows_kept_with_lineage_and_stable_ids(self):
        items=[row(),row(),row(event_type="Severe Weather")]
        raw=json.dumps(items).encode()
        accepted,rejected,stats=parse(raw,META)
        self.assertEqual((len(accepted),len(rejected)),(3,0))
        self.assertEqual(stats["exact_duplicate_source_rows"],1)
        self.assertEqual(stats["content_distinct_accepted_publisher_rows"],2)
        self.assertTrue(accepted[1]["is_exact_duplicate_publisher_record"])
        self.assertEqual(accepted[1]["duplicate_of_source_position"],1)
        self.assertEqual(len({x["source_row_key"] for x in accepted}),3)
        rerun,_,_=parse(raw,META)
        self.assertEqual([x["source_row_key"] for x in accepted],[x["source_row_key"] for x in rerun])

    def test_reject_invalid_dates_bad_numeric_and_schema_drift_without_fake_outages(self):
        cases=[
            row(date_event_began=None),
            row(date_event_began="2023-02-30"),
            row(number_of_customers_affected=-1),
            row(demand_loss_mw="nan"),
            row(date_of_restoration="not-reported"),
            dict(list(row().items())[:-1]),
        ]
        a,r,m=parse(json.dumps([row()]+cases).encode(),META)
        self.assertEqual((len(a),len(r)),(2,5))
        self.assertEqual(sum(m["rejection_reasons"].values()),5)
        self.assertEqual(m["missing_event_start_date_preserved_as_unknown"],1)
        self.assertIsNone(a[1]["event_date_source"])
        self.assertIsNone(a[1]["source_event_year"])
        self.assertEqual(a[1]["event_date_source_status"],"NOT_REPORTED")
        self.assertFalse(a[0]["site_electric_outage_verified"])

    def test_source_reconciliation_staged_sqlite_and_licenses(self):
        with tempfile.TemporaryDirectory() as t:
            folder=Path(t)
            original=folder/"raw.json";meta=folder/"meta.json";out=folder/"out"
            raw=json.dumps([row(),row(),row(date_event_began="2023-10-06",event_type="Weather"),row(demand_loss_mw=-5)]).encode()
            original.write_bytes(raw);meta.write_text(json.dumps(META))
            m=run(original,meta,out)
            self.assertEqual((m["original_source_rows"],m["normalized_accepted"],m["rejected"]),(4,3,1))
            self.assertEqual(m["indexed_temporary_sqlite_rows"],3)
            self.assertEqual(m["statistics"]["exact_duplicate_source_rows"],1)
            self.assertEqual(m["downloaded_original_export_sha256"],digest(raw))
            self.assertEqual(m["metadata_declared_license"],"Public Domain")
            self.assertEqual(m["durable_backend_indexed"],m["deployed"])
            self.assertEqual(m["deployed"],0)
            self.assertEqual(len((out/"rejected.jsonl").read_text().splitlines()),1)
            with sqlite3.connect(out/"oe417_annual_staging.sqlite") as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0],"ok")
                self.assertEqual(db.execute("SELECT count(*) FROM source_observations").fetchone()[0],3)
                self.assertEqual(db.execute("SELECT count(*) FROM source_observations WHERE exact_duplicate_source=1").fetchone()[0],1)

    def test_refuse_wrong_export_shape(self):
        for raw in ('{}','{"results":[]}','[]','', '["x"]'):
            with self.assertRaises(ValueError):
                parse(raw.encode(),META)


if __name__=="__main__":
    unittest.main()
