import unittest
from facilityrisk.lane_a_hazards import collect, nfhl_point, valid_point, whp_point


def fake_fema(base, path, params):
    assert path == "query" and params["inSR"] == 4326
    return ({"features": [{"attributes": {"OBJECTID": 42, "DFIRM_ID": "123456", "FLD_ZONE": "AE"}}]},
            "https://example.org/fema", "a" * 64, 50)


def fake_usfs(base, path, params):
    assert path == "identify" and params["geometryType"] == "esriGeometryPoint"
    return ({"results": [{"layerId": 1, "layerName": "WHP classified", "value": "Moderate", "attributes": {"Value": 3}}]},
            "https://example.org/usfs", "b" * 64, 50)


class LaneAHazardTests(unittest.TestCase):
    def test_coordinates(self):
        self.assertTrue(valid_point(-119.2, 38.1))
        for point in [(181, 0), (0, -91), (float("nan"), 1), (True, 40), ("1", 2)]:
            self.assertFalse(valid_point(*point))

    def test_fema_source_id(self):
        x = nfhl_point(-119.2, 38.1, fake_fema)
        self.assertEqual(x["records"][0]["source_id"], "42")
        self.assertEqual(x["accepted_count"], 1)

    def test_duplicate_fema_ids_rejected(self):
        def duplicate(base, path, params):
            return ({"features": [{"attributes": {"OBJECTID": 4}}, {"attributes": {"OBJECTID": 4}}]}, "url", "c", 3)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            nfhl_point(-119, 38, duplicate)

    def test_no_fema_polygon_not_low_risk(self):
        def empty(base, path, params):
            return ({"features": []}, "url", "c", 3)
        self.assertEqual(nfhl_point(-119, 38, empty)["coverage_state"], "unknown_no_intersection")

    def test_truncated_fema_rejected(self):
        def truncated(base, path, params):
            return ({"features": [], "exceededTransferLimit": True}, "url", "c", 3)
        with self.assertRaisesRegex(ValueError, "truncated"):
            nfhl_point(-119, 38, truncated)

    def test_whp_raster_identify(self):
        self.assertEqual(whp_point(-119, 38, fake_usfs)["records"][0]["value"], "Moderate")

    def test_whp_no_data_unknown(self):
        def empty(base, path, params):
            return ({"results": []}, "url", "c", 3)
        self.assertEqual(whp_point(-119, 38, empty)["coverage_state"], "unknown_no_raster_value")

    def test_corroboration_gate(self):
        with self.assertRaisesRegex(ValueError, "Corroborated"):
            collect([{"site_reference": "a", "longitude": -119, "latitude": 38, "coordinates_corroborated": False}])

    def test_failures_not_reported_as_zero_hazard(self):
        def failure(base, path, params):
            raise ValueError("Service unavailable")
        result = collect([{"site_reference": "case", "longitude": -119, "latitude": 38, "coordinates_corroborated": True}], failure)
        self.assertEqual(len(result["observations"]), 2)
        self.assertTrue(all(x["coverage_state"] == "unknown_source_unavailable" for x in result["observations"]))
        self.assertTrue(all(x["ingestion_state"] != "STAGED" for x in result["observations"]))


if __name__ == "__main__":
    unittest.main()
