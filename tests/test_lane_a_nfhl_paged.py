import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.lane_a_fema_query_smoke import validate as validate_native_query
from scripts.lane_a_nfhl_paged import (
    FEMA_LAYER, envelope, geometry_bbox, run, source_key,
)

FIELDS = [{"name": x} for x in (
    "OBJECTID", "DFIRM_ID", "FLD_AR_ID", "FLD_ZONE", "SOURCE_CIT",
)]


def fema_record(oid):
    return {
        "attributes": {
            "OBJECTID": oid, "DFIRM_ID": "22071C",
            "FLD_AR_ID": "22071C_" + str(oid),
            "FLD_ZONE": "AE" if oid % 2 else "X",
            "SOURCE_CIT": "FEMA_STUDY",
            "VERSION_ID": "1.1.1.0",
        },
        "geometry": {"rings": [
            [[-90.081, 29.948], [-90.080, 29.948],
             [-90.080, 29.949], [-90.081, 29.948]]
        ]},
    }


def responder(params, *, missing=False, count_offset=0, truncate=False):
    if params.get("where") == "1=0":
        d = {"fields": FIELDS, "features": []}
    elif params.get("returnIdsOnly") == "true":
        d = {"objectIdFieldName": "OBJECTID", "objectIds": [11, 12, 13]}
    elif params.get("returnCountOnly") == "true":
        d = {"count": 3 + count_offset}
    else:
        ids = [int(v) for v in params["objectIds"].split(",")]
        if missing and ids[-1] == 13:
            ids = ids[:-1]
        d = {"geometryType": "esriGeometryPolygon",
             "spatialReference": {"wkid": 4326},
             "features": [fema_record(v) for v in ids],
             "exceededTransferLimit": truncate}
    return d, json.dumps(d, sort_keys=True).encode(), FEMA_LAYER + "/query"


class FEMAPagedWindowsTests(unittest.TestCase):
    def test_complete_enumeration_of_more_than_one_query_page(self):
        with tempfile.TemporaryDirectory() as folder:
            windows = {
                "window_1": (-90.083, 29.946, -90.080, 29.950),
                "window_2": (-90.083, 29.946, -90.080, 29.950),
            }
            m = run(Path(folder), fetch=responder, windows=windows,
                    max_ids_per_window=10, batch_size=2)
            self.assertTrue(m["all_requested_windows_complete"])
            lookup = validate_native_query(Path(folder))
            self.assertTrue(lookup["read_only_source_query_verified"])
            self.assertEqual(lookup["distinct_source_native_keys"], 3)
            self.assertEqual(m["source_feature_count"], 3)
            self.assertEqual(m["window_membership_count"], 6)
            self.assertEqual(m["rtree_index_count"], 3)
            self.assertEqual(m["successful_windows"], 2)
            self.assertEqual(m["distinct_dfirm_ids"], 1)
            self.assertEqual(m["windows"]["window_1"]["id_count"], 3)
            self.assertEqual(len(m["windows"]["window_1"]["chunks"]), 2)
            self.assertEqual(m["actual_physical_site_matches"], 0)
            self.assertFalse(m["national_source_complete"])
            db = sqlite3.connect(Path(folder) / "fema-window-index.sqlite")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM fema_source_bounds").fetchone()[0], 3)
            self.assertEqual(db.execute("PRAGMA quick_check").fetchone()[0], "ok")
            db.close()
            self.assertTrue((Path(folder) / "raw" / "window_1.ids.json").is_file())

    def test_source_native_key_and_geometry_bounds(self):
        self.assertEqual(source_key(fema_record(12)["attributes"]),
                         "dfirm:22071C:fld_ar:22071C_12")
        self.assertEqual(geometry_bbox(fema_record(12)),
                         (-90.081, 29.948, -90.08, 29.949))
        with self.assertRaises(ValueError):
            envelope((-90, 30, -91, 31))
        broken = fema_record(12)
        broken["geometry"]["rings"][0][-1] = [-91, 30]
        with self.assertRaisesRegex(ValueError, "unclosed"):
            geometry_bbox(broken)

    def test_inconsistent_source_count_fails_closed(self):
        def mismatch(params):
            return responder(params, count_offset=1)
        with tempfile.TemporaryDirectory() as folder:
            m = run(Path(folder), fetch=mismatch, windows={
                "w": (-90.083, 29.946, -90.080, 29.950)
            })
            self.assertFalse(m["all_requested_windows_complete"])
            self.assertEqual(m["windows"]["w"]["status"], "INCOMPLETE")
            self.assertIn("count/IDs", m["windows"]["w"]["error"])

    def test_missing_id_after_paged_query_fails_closed(self):
        def missing(params):
            return responder(params, missing=True)
        with tempfile.TemporaryDirectory() as folder:
            m = run(Path(folder), fetch=missing, windows={
                "w": (-90.083, 29.946, -90.080, 29.950)
            }, batch_size=2)
            self.assertFalse(m["all_requested_windows_complete"])
            self.assertIn("Missing/extra OBJECTIDs", m["windows"]["w"]["error"])

    def test_transfer_limit_is_not_ignored(self):
        def transfer(params):
            return responder(params, truncate=True)
        with tempfile.TemporaryDirectory() as folder:
            m = run(Path(folder), fetch=transfer, windows={
                "w": (-90.083, 29.946, -90.080, 29.950)
            })
            self.assertEqual(m["successful_windows"], 0)
            self.assertIn("exceededTransferLimit", m["windows"]["w"]["error"])


    def test_split_and_disclosed_generalization_for_oversize_polygon(self):
        def big(params):
            if "objectIds" in params:
                ids = params["objectIds"].split(",")
                if len(ids) > 1:
                    raise RuntimeError("ArcGIS 500 oversized polygon batch")
                if ids == ["13"] and "maxAllowableOffset" not in params:
                    raise RuntimeError("Single polygon exceeds 15MB JSON limit")
            return responder(params)
        with tempfile.TemporaryDirectory() as folder:
            m = run(Path(folder), fetch=big, windows={
                "w": (-90.083, 29.946, -90.080, 29.950)
            }, batch_size=3)
            self.assertTrue(m["all_requested_windows_complete"])
            self.assertFalse(m["all_native_resolution"])
            self.assertEqual(m["geometry_generalized_observations"], 1)
            self.assertEqual(m["source_feature_count"], 3)
            self.assertEqual(m["windows"]["w"]["accepted_count"], 3)
            self.assertGreater(len(m["windows"]["w"]["attempt_errors"]), 0)
            db = sqlite3.connect(Path(folder) / "fema-window-index.sqlite")
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM fema_source_features WHERE geometry_tolerance_degrees > 0"
            ).fetchone()[0], 1)
            db.close()

    def test_interruption_preserves_true_partial_index_counts(self):
        def fail_last(params):
            if params.get("objectIds") == "13":
                raise RuntimeError("official source disconnected during last polygon")
            return responder(params)
        with tempfile.TemporaryDirectory() as folder:
            m = run(Path(folder), fetch=fail_last, windows={
                "w": (-90.083, 29.946, -90.080, 29.950)
            }, batch_size=2)
            self.assertFalse(m["all_requested_windows_complete"])
            self.assertEqual(m["source_feature_count"], 2)
            self.assertEqual(m["windows"]["w"]["accepted_count"], 2)
            self.assertEqual(m["windows"]["w"]["retrieved_ids"], 2)
            self.assertEqual(m["windows"]["w"]["status"], "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
