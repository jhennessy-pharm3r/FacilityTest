import json
import tempfile
import unittest
from pathlib import Path

from scripts.validate_lane_a_massgis import MASSGIS, MASSGIS_SOURCE, collect


def fake_massgis(base, operation, params):
    if not operation:
        doc = {
            "name": "100-Year Flood Zone", "geometryType": "esriGeometryPolygon",
            "objectIdField": "OBJECTID", "fields": [
                {"name": "OBJECTID"}, {"name": "DFIRM_ID"},
                {"name": "FLD_AR_ID"}, {"name": "FLD_ZONE"},
            ],
        }
    else:
        self_key = 1 if params.get("geometryType") else 2
        doc = {"features": [{
            "attributes": {
                "OBJECTID": self_key, "DFIRM_ID": "250001",
                "FLD_AR_ID": "MA_NFHL_" + str(self_key), "FLD_ZONE": "AE",
                "SOURCE_CIT": "official_source",
            },
            "geometry": {"rings": [[[-71.05, 42.35], [-71.04, 42.35],
                                    [-71.04, 42.36], [-71.05, 42.35]]]},
        }]}
    return doc, json.dumps(doc).encode(), base + "/" + operation


class MassGISSourceSampleTests(unittest.TestCase):
    def test_is_independent_and_geography_limited(self):
        with tempfile.TemporaryDirectory() as temp:
            m = collect(Path(temp), fetch=fake_massgis)
            self.assertEqual(m["dataset_id"], MASSGIS_SOURCE)
            self.assertTrue(m["not_a_national_nfhl_replacement"])
            self.assertFalse(m["sfha_only"])
            self.assertTrue(m["unmapped_areas_are_unknown"])
            self.assertTrue(m["source_sample_validated"])
            self.assertEqual(m["sample_raw"], 2)
            self.assertEqual(m["sample_accepted"], 2)
            self.assertEqual(m["indexed_observations"], 2)
            self.assertEqual(m["distinct_fema_native_keys"], 2)
            self.assertEqual(m["verified_physical_facilities"], 0)

    def test_network_failures_do_not_claim_source_data(self):
        def blocked(base, operation, params):
            raise ConnectionError("network unavailable")
        with tempfile.TemporaryDirectory() as temp:
            m = collect(Path(temp), fetch=blocked)
            self.assertFalse(m["source_sample_validated"])
            self.assertEqual(m["sample_accepted"], 0)
            self.assertEqual(m["indexed_observations"], 0)
            self.assertEqual(m["metadata"]["state"], "PROBED")


if __name__ == "__main__":
    unittest.main()
