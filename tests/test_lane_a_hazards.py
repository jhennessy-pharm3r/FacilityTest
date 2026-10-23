import unittest

from facilityrisk.lane_a_hazards import collect, nfhl_point, valid_point, whp_point


def fake_fema(base, path, params):
    assert path == "query" and params["inSR"] == 4326
    assert "FLD_AR_ID" in params["outFields"]
    return ({
        "features": [{
            "attributes": {
                "OBJECTID": 42, "DFIRM_ID": "123456",
                "FLD_AR_ID": "NATIVE_FLOOD_ID", "FLD_ZONE": "AE",
            }
        }]
    }, "https://example.org/fema", "a" * 64, 50)


def fake_usfs(base, path, params):
    assert path == "identify" and params["geometryType"] == "esriGeometryPoint"
    assert base.endswith("/ImageServer")
    return ({"value": "571", "properties": {"Values": ["571"]}},
            "https://example.org/usfs", "b" * 64, 50)


def site():
    return {
        "site_reference": "case", "longitude": -119, "latitude": 38,
        "coordinates_corroborated": True,
        "coordinate_evidence": "verified survey record",
    }


class LaneAHazardTests(unittest.TestCase):
    def test_coordinates(self):
        self.assertTrue(valid_point(-119.2, 38.1))
        for point in [(181, 0), (0, -91), (float("nan"), 1),
                      (True, 40), ("1", 2)]:
            self.assertFalse(valid_point(*point))

    def test_fema_source_identity(self):
        sample = nfhl_point(-119.2, 38.1, fake_fema)
        self.assertEqual(sample["records"][0]["source_key"],
                         "dfirm:123456:fld_ar:NATIVE_FLOOD_ID")
        self.assertEqual(sample["records"][0]["source_objectid"], 42)
        self.assertEqual(sample["accepted_count"], 1)

    def test_duplicate_fema_ids_rejected(self):
        def duplicate(base, path, params):
            return ({
                "features": [
                    {"attributes": {"OBJECTID": 4}},
                    {"attributes": {"OBJECTID": 4}},
                ]
            }, "url", "c", 3)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            nfhl_point(-119, 38, duplicate)

    def test_no_fema_polygon_not_low_risk(self):
        def empty(base, path, params):
            return ({"features": []}, "url", "c", 3)
        self.assertEqual(nfhl_point(-119, 38, empty)["coverage_state"],
                         "unknown_no_intersection")

    def test_truncated_fema_rejected(self):
        def truncated(base, path, params):
            return ({"features": [], "exceededTransferLimit": True}, "url", "c", 3)
        with self.assertRaisesRegex(ValueError, "truncated"):
            nfhl_point(-119, 38, truncated)

    def test_whp_raster_identify_has_no_native_event_id(self):
        sample = whp_point(-119, 38, fake_usfs)
        self.assertEqual(sample["records"][0]["pixel_value"], 571.0)
        self.assertIsNone(sample["records"][0]["source_native_feature_id"])
        self.assertEqual(sample["source"], "usfs_whp_continuous_2023")

    def test_whp_no_data_unknown(self):
        def empty(base, path, params):
            return ({"value": "NoData"}, "url", "c", 3)
        sample = whp_point(-119, 38, empty)
        self.assertEqual(sample["coverage_state"], "unknown_no_raster_value")
        self.assertEqual(sample["rejected_count"], 1)

    def test_whp_value_zero_not_missing(self):
        def zero(base, path, params):
            return ({"value": "0"}, "url", "c", 3)
        self.assertEqual(whp_point(-119, 38, zero)["records"][0]["pixel_value"], 0)

    def test_corroboration_and_evidence_gate(self):
        s = site()
        s["coordinates_corroborated"] = False
        with self.assertRaisesRegex(ValueError, "Corroborated"):
            collect([s])
        s = site()
        del s["coordinate_evidence"]
        with self.assertRaisesRegex(ValueError, "coordinate_evidence"):
            collect([s])

    def test_failures_are_probed_with_unknown_counts(self):
        def failure(base, path, params):
            raise ValueError("Service unavailable")
        result = collect([site()], failure)
        self.assertEqual(len(result["observations"]), 2)
        self.assertTrue(all(x["coverage_state"] == "unknown_source_unavailable"
                            for x in result["observations"]))
        self.assertTrue(all(x["ingestion_state"] == "PROBED"
                            for x in result["observations"]))
        self.assertTrue(all(x["raw_count"] is None
                            for x in result["observations"]))


if __name__ == "__main__":
    unittest.main()
