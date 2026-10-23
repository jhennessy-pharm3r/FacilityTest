"""ORNL first-party public CIM-like ODIN county feed source-preserving QA fixtures."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from facilityrisk.lane_d.ingest_odin_direct import run,parse,sha,canonical,tagged_names


def sample(**kwargs):
    value={
        "MRID":"182147","mrid":"182147","communityDescriptor":"04013",
        "metersAffected":265,"reportedStartTime":"2026-10-22T05:48:00+00:00",
        "outageArea":{"outageAreaKind":"county","metersServed":20000,"earliestReportedTime":None},
        "names":[
            {"name":"ARIZONA PUBLIC SERVICE CO","nameType":"UtilityName","nameTypeAuthority":"EIA"},
            {"name":"803","nameType":"UtilityId","nameTypeAuthority":"EIA"}],
        "estimatedRestorationTime":{"confidenceKind":None,"ert":None,"ertSource":None},
        "incident":{"cause":None,"location":None},"statusKind":None,
    }
    value.update(kwargs)
    return value


class FirstPartyODINTests(unittest.TestCase):
    def test_public_native_utility_and_county_are_not_site_ids(self):
        a,b,counts=parse(json.dumps({"outage":[sample()]}).encode(),"2026-10-23T16:00:00+00:00")
        self.assertEqual(len(a),1);self.assertFalse(b)
        self.assertEqual(a[0]["source_native_MRID"],"182147")
        self.assertEqual(a[0]["source_utility_id_with_EIA_authority"],"803")
        self.assertEqual(a[0]["source_native_county_fips"],"04013")
        self.assertFalse(a[0]["physical_site_outage_verified"])
        self.assertFalse(a[0]["site_meter_account_verified"])
        self.assertEqual(counts["distinct_nonnull_native_mrids"],1)

    def test_nullable_publisher_native_id_and_unknown_date_preserved(self):
        items=[sample(MRID=None,mrid=None,reportedStartTime=None),
               sample(MRID=None,mrid=None,communityDescriptor="04025",reportedStartTime=None,
                      names=[])]
        a,b,counts=parse(json.dumps({"outage":items}).encode(),"2026-10-23T16:00:00+00:00")
        self.assertEqual((len(a),len(b)),(2,0))
        self.assertEqual(counts["missing_native_mrid"],2)
        self.assertEqual(counts["missing_reported_start"],2)
        self.assertEqual(counts["missing_reported_eia_utility_id"],1)
        self.assertTrue(all(r["reported_start_status"]=="UNKNOWN" for r in a))
        self.assertTrue(all(not r["native_event_id_available"] for r in a))
        self.assertNotEqual(a[0]["source_row_key"],a[1]["source_row_key"])

    def test_exact_duplicates_have_distinct_position_keys_and_lineage(self):
        items=[sample(),sample(),sample(MRID="182147",mrid="182147",metersAffected=100)]
        a,b,counts=parse(json.dumps({"outage":items}).encode(),"2026-10-23T16:00:00+00:00")
        self.assertEqual((len(a),len(b)),(3,0))
        self.assertEqual(counts["exact_duplicate_source_rows_in_snapshot"],1)
        self.assertEqual(counts["repeated_nonnull_native_mrid_occurrences"],2)
        self.assertTrue(a[1]["is_exact_duplicate_row_in_snapshot"])
        self.assertEqual(a[1]["duplicate_of_source_row"],1)
        self.assertFalse(a[2]["is_exact_duplicate_row_in_snapshot"])
        self.assertEqual(len({x["source_row_key"] for x in a}),3)

    def test_deny_invalid_source_ids_geometry_and_money_like_metrics(self):
        bad=[
            sample(communityDescriptor="4013"),
            sample(outageArea={"outageAreaKind":"ZIP"}),
            sample(metersAffected=-2),
            sample(MRID="177",mrid="178"),
            sample(reportedStartTime="not-time"),
            sample(reportedStartTime="2040-01-01T00:00:00+00:00"),
            sample(metersAffected="nan"),
            sample(names=3),
        ]
        a,b,counts=parse(json.dumps({"outage":[sample()]+bad}).encode(),"2026-10-23T16:00:00+00:00")
        self.assertEqual((len(a),len(b)),(2,7))
        self.assertEqual(sum(counts["reject_reasons"].values()),7)
        self.assertFalse(a[1]["site_meter_account_verified"])

    def test_real_staging_count_digest_indexes_rejections(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);original=base/"raw.json"
            data=json.dumps({"outage":[sample(),sample(),sample(MRID=None,mrid=None,
                  communityDescriptor="04025",reportedStartTime=None),
                  sample(metersAffected=-9)]}).encode()
            original.write_bytes(data)
            m=run(original,base/"stage")
            self.assertEqual(m["downloaded"],4)
            self.assertEqual(m["normalized_accepted"],3)
            self.assertEqual(m["rejected"],1)
            self.assertEqual(m["indexed_ephemeral_local_sqlite"],3)
            self.assertEqual(m["observations"]["exact_duplicate_source_rows_in_snapshot"],1)
            self.assertEqual(m["original_raw_json_sha256"],sha(data))
            self.assertEqual(m["deployed"],0)
            self.assertEqual(m["insured_facility_outages_verified"],0)
            with sqlite3.connect(base/"stage"/"odin_direct_county_staging.sqlite") as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0],"ok")
                self.assertEqual(db.execute("SELECT COUNT(*) FROM source_observations").fetchone()[0],3)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM source_observations WHERE is_exact_duplicate=1").fetchone()[0],1)

    def test_wrong_top_level_rejected(self):
        for obj in ({"results":[]},{"outage":[]},[],{"outage":{}}):
            with self.assertRaises(ValueError):
                parse(json.dumps(obj).encode(),"2026-10-23T16:00:00+00:00")


if __name__=="__main__":
    unittest.main()
