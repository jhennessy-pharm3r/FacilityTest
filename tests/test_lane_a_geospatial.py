import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from facilityrisk.lane_a_geospatial import polygon_point_relation, query_fema_point
from scripts.lane_a_nfhl_paged import run
from tests.test_lane_a_nfhl_paged import responder


def square():
    return {"geometry": {"rings": [[
        [0, 0], [10, 0], [10, 10], [0, 10], [0, 0]
    ], [
        [3, 3], [3, 7], [7, 7], [7, 3], [3, 3]
    ]]}}


class SiteHazardEvidenceTests(unittest.TestCase):
    def test_even_odd_holes_and_shared_boundary(self):
        self.assertEqual(polygon_point_relation(square(), 2, 2), "INSIDE")
        self.assertEqual(polygon_point_relation(square(), 5, 5), "OUTSIDE")
        self.assertEqual(polygon_point_relation(square(), 3, 5), "BOUNDARY")
        self.assertEqual(polygon_point_relation(square(), 20, 20), "OUTSIDE")

    def test_requires_independently_corroborated_coordinate(self):
        with self.assertRaisesRegex(ValueError, "corroborated"):
            query_fema_point("missing.sqlite", "missing.json",
                longitude=-90.081, latitude=29.948, site_reference="fixture",
                coordinate_evidence="", coordinates_corroborated=False)

    def test_unknown_outside_coverage_not_no_flood_risk(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            m = run(root, fetch=responder,
                windows={"w": (-90.083, 29.946, -90.080, 29.950)},
                batch_size=2)
            self.assertTrue(m["all_requested_windows_complete"])
            kwargs = {"site_reference": "test_fixture",
                      "coordinate_evidence": "explicit unit-test coordinates",
                      "coordinates_corroborated": True}
            inside = query_fema_point(root / "fema-window-index.sqlite",
                                      root / "manifest.json",
                                      longitude=-90.0805, latitude=29.9485, **kwargs)
            self.assertEqual(inside["coverage_state"],
                             "SOURCE_POLYGON_INTERSECTION_AT_CORROBORATED_POINT")
            self.assertEqual(len(inside["source_features"]), 3)
            self.assertEqual(inside["bbox_candidates"], 3)
            self.assertTrue(inside["site_identity_not_source_verified"])
            self.assertTrue(all(x["original_response_sha256"]
                                for x in inside["source_features"]))

            outside = query_fema_point(root / "fema-window-index.sqlite",
                                       root / "manifest.json",
                                       longitude=-80.0, latitude=25.0, **kwargs)
            self.assertEqual(outside["coverage_state"],
                             "UNKNOWN_INCOMPLETE_SOURCE_COVERAGE")
            self.assertEqual(outside["source_features"], [])

    def test_simplified_geometry_is_review_only(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            m = run(root, fetch=responder,
                windows={"w": (-90.083, 29.946, -90.080, 29.950)},
                batch_size=2)
            db = sqlite3.connect(root / "fema-window-index.sqlite")
            db.execute("UPDATE fema_source_features SET geometry_tolerance_degrees=0.00005 WHERE objectid=11")
            db.commit()
            db.close()
            q = query_fema_point(root / "fema-window-index.sqlite",
                                 root / "manifest.json",
                                 longitude=-90.0805, latitude=29.9485,
                                 site_reference="fixture",
                                 coordinate_evidence="test parcel record",
                                 coordinates_corroborated=True)
            self.assertEqual(q["coverage_state"], "BOUNDARY_OR_SIMPLIFICATION_REVIEW_REQUIRED")
            self.assertIn("GENERALIZED_REVIEW_REQUIRED",
                          [r["geometry_precision"] for r in q["source_features"]])


if __name__ == "__main__":
    unittest.main()
