"""Deterministic Lane A content/schema, source identity, and staging QA."""
import json
import tempfile
import unittest
from pathlib import Path

from scripts.validate_lane_a_sources import (
    FEMA, WHP, fetch_capture, parse_fema, parse_whp, run,
)


def fake_fetch(base, operation, params):
    if not operation:
        doc = (
            {"geometryType": "esriGeometryPolygon", "objectIdField": "OBJECTID",
             "fields": [{"name": "OBJECTID"}, {"name": "FLD_AR_ID"}, {"name": "DFIRM_ID"}]}
            if base == FEMA else
            {"name": "USFS WHP Continuous 2023", "pixelSizeX": 270, "pixelType": "S32"}
        )
    elif base == FEMA:
        doc = {"features": [
            {"attributes": {"OBJECTID": 17, "DFIRM_ID": "111111",
                            "VERSION_ID": "1.1.1.0", "FLD_AR_ID": "FLD123",
                            "FLD_ZONE": "AE", "SOURCE_CIT": "sample"},
             "geometry": {"rings": [[[-90.1, 30.0], [-90.0, 30.0],
                                     [-90.0, 30.1], [-90.1, 30.0]]]}}
        ], "exceededTransferLimit": True}
    else:
        doc = {"value": "571", "properties": {"Values": ["571"]}}
    raw = json.dumps(doc, sort_keys=True).encode()
    return doc, raw, base + "/" + operation


class LaneALiveValidationTest(unittest.TestCase):
    def test_fema_native_identity_and_geometry(self):
        doc, raw, url = fake_fetch(FEMA, "query", {})
        rows, rejects = parse_fema(doc["features"], url)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rejects), 0)
        self.assertEqual(rows[0]["source_key"], "dfirm:111111:fld_ar:FLD123")
        self.assertEqual(rows[0]["raw_feature"]["attributes"]["FLD_ZONE"], "AE")

    def test_reject_missing_native_id_and_bad_geometry(self):
        features = [
            {"attributes": {"FLD_ZONE": "AE"}, "geometry": {"rings": [[[0, 0]]] }},
            {"attributes": {"OBJECTID": 5}, "geometry": {"rings": [[[200, 2]]] }},
            {"attributes": {"OBJECTID": 6}, "geometry": {"rings": [[[0, 0]]] }},
        ]
        good, bad = parse_fema(features, FEMA)
        self.assertEqual(len(good), 1)
        self.assertEqual(len(bad), 2)
        self.assertEqual({x["reason"] for x in bad}, {"missing_native_identifier", "invalid_wgs84_polygon"})

    def test_duplicate_response_native_ids(self):
        doc, raw, url = fake_fetch(FEMA, "query", {})
        good, bad = parse_fema(doc["features"] * 2, url)
        self.assertEqual(len(good), 1)
        self.assertEqual(bad[0]["reason"], "duplicate_in_response")

    def test_whp_no_data_not_zero_hazard(self):
        for item in [{"value": None}, {"value": "NoData"}, {"value": "-9999"}, {"value": float("nan")}]:
            self.assertIsNone(parse_whp(item)[0])
        self.assertEqual(parse_whp({"value": "0"})[0], 0.0)

    def test_staging_checksum_and_sqlite_reconcile(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = run(Path(temp), fetch=fake_fetch,
                windows=(("test", (-90.1, 30.0, -90.0, 30.1)),),
                points=(("test", (-120.0, 39.0)),))
            self.assertTrue(manifest["source_access_complete"])
            self.assertTrue(manifest["all_qa_reconciled"])
            self.assertEqual(manifest["sqlite_quick_check"], "ok")
            self.assertEqual(manifest["verified_physical_facility_count"], 0)
            a = manifest["sources"]["fema_nfhl"]
            b = manifest["sources"]["usfs_whp_continuous_2023"]
            self.assertEqual((a["sample_raw"], a["sample_accepted"], a["indexed_observations"]), (1, 1, 1))
            self.assertEqual((b["sample_raw"], b["sample_accepted"], b["indexed_observations"]), (1, 1, 1))
            self.assertTrue(a["samples"][0]["source_exceeded_transfer_limit"])
            self.assertTrue((Path(temp) / "source-only.sqlite").exists())
            for source in (a, b):
                for receipt in [source["metadata"]] + source["samples"]:
                    raw = (Path(temp) / "raw" / receipt["raw_file"]).read_bytes()
                    import hashlib
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), receipt["raw_sha256"])

    def test_blocked_source_not_verified(self):
        def blocked(base, operation, params):
            raise OSError("network-blocked")
        with tempfile.TemporaryDirectory() as temp:
            m = run(Path(temp), fetch=blocked, windows=(("t", (-90.1, 30, -90, 30.1)),),
                    points=(("t", (-120, 39)),))
            self.assertFalse(m["source_access_complete"])
            self.assertTrue(m["all_qa_reconciled"])
            for source in m["sources"].values():
                self.assertEqual(source["metadata"]["state"], "PROBED")
                self.assertEqual(source["samples"][0]["state"], "PROBED")
                self.assertEqual(source["sample_accepted"], 0)
                self.assertEqual(source["indexed_observations"], 0)


if __name__ == "__main__":
    unittest.main()
