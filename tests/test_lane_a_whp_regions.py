import json
import tempfile
import unittest
from pathlib import Path

from scripts.lane_a_whp_regions import USFS, grid_points, interpret_pixel, run


def live_reply_shape(path, params):
    if path == "":
        doc = {"name": "WHP continuous",
               "pixelType": "S32", "pixelSizeX": 270, "pixelSizeY": 270,
               "noDataValues": [-2147483648],
               "minValues": [0], "maxValues": [144153],
               "extent": {"spatialReference": {"wkid": 3857}}}
    else:
        geom = json.loads(params["geometry"])
        value = "-2147483648" if geom["x"] < -120.03 else "0"
        doc = {"value": value, "location": geom}
    raw = json.dumps(doc, sort_keys=True).encode()
    return doc, raw, USFS + "/" + path


class USFSRegionalGridTests(unittest.TestCase):
    def test_explicit_nodata_is_not_low_risk(self):
        self.assertEqual(interpret_pixel({"value": "-2147483648"}, {-2147483648},
                                         lo=0, hi=144153), ("NO_DATA", None))
        self.assertEqual(interpret_pixel({"value": "0"}, {-2147483648},
                                         lo=0, hi=144153), ("VALUE", 0.0))
        self.assertEqual(interpret_pixel({"value": "BOGUS"}, set(),
                                         lo=0, hi=144153), ("INVALID_PIXEL", None))
        self.assertEqual(interpret_pixel({"value": "200000"}, set(),
                                         lo=0, hi=144153), ("INVALID_PIXEL", None))

    def test_official_response_inventory_counts_and_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            m = run(Path(folder), fetch=live_reply_shape,
                    regions={"west": (-120.0, 39.0), "midwest": (-105.0, 40.0)},
                    workers=2)
            self.assertTrue(m["complete_geographic_probe_set"])
            self.assertEqual(m["requested_points"], 10)
            self.assertEqual(m["downloaded_replies"], 10)
            self.assertEqual(m["accepted_numeric_pixels"], 8)
            self.assertEqual(m["no_data_pixels"], 2)
            self.assertEqual(m["rejected_pixels"], 0)
            self.assertEqual(m["indexed_point_observations"], 10)
            self.assertEqual(m["distinct_region_count"], 2)
            self.assertEqual(m["site_matches"], 0)
            self.assertFalse(m["national_raster_complete"])
            self.assertTrue((Path(folder) / "whp-regional-source-only.sqlite").exists())
            import hashlib
            for receipt in m["observations"]:
                raw = (Path(folder) / "raw" / receipt["raw_file"]).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), receipt["raw_sha256"])

    def test_missing_source_replies_are_not_zero_hazard(self):
        def partial(path, params):
            if path == "" or json.loads(params["geometry"])["x"] < -119.99:
                return live_reply_shape(path, params)
            raise OSError("GeoPlatform failure")
        with tempfile.TemporaryDirectory() as folder:
            m = run(Path(folder), fetch=partial,
                    regions={"west": (-120.0, 39.0)}, workers=1)
            self.assertFalse(m["complete_geographic_probe_set"])
            self.assertTrue(m["sample_reconciled"])
            self.assertEqual(m["source_failures"], 2)
            self.assertTrue(all(x["state"] == "SOURCE_UNAVAILABLE" or
                                x["state"] == "DOWNLOADED"
                                for x in m["observations"]))

    def test_grid_bounds(self):
        pts = list(grid_points({"test": (-100, 40)}))
        self.assertEqual(len(pts), 5)
        self.assertEqual(pts[0], ("test", 0, -100.0, 40.0))


if __name__ == "__main__":
    unittest.main()
