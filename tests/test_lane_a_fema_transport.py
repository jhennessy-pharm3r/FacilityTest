import json
import tempfile
import unittest
from pathlib import Path

from scripts.diagnose_lane_a_fema_access import FEMA, native_source_key, run


def fake_response(base, params, method):
    doc = {"features": [
        {"attributes": {"OBJECTID": 44, "DFIRM_ID": "100001",
                        "FLD_AR_ID": "A123", "FLD_ZONE": "AE"}},
        {"attributes": {"OBJECTID": 44, "DFIRM_ID": "100001",
                        "FLD_AR_ID": "A123", "FLD_ZONE": "AE"}},
        {"attributes": {"FLD_ZONE": "X"}},
    ]}
    raw = json.dumps(doc, sort_keys=True).encode()
    return doc, raw, base + "/query"


class FEMATransportTests(unittest.TestCase):
    def test_native_identifiers(self):
        self.assertEqual(native_source_key({"DFIRM_ID": "1", "FLD_AR_ID": "2"}),
                         "dfirm:1:fld_ar:2")
        self.assertEqual(native_source_key({"OBJECTID": 9}), "service_objectid:9")
        self.assertIsNone(native_source_key({"FLD_ZONE": "AE"}))

    def test_real_reply_fixture_accept_reject_and_checksum(self):
        with tempfile.TemporaryDirectory() as temp:
            m = run(Path(temp), requester=fake_response,
                    strategies=(("unit", FEMA, {"f": "json"}, "GET"),))
            self.assertTrue(m["official_attribute_ingestion_succeeded"])
            self.assertTrue(m["source_sample_reconciled"])
            self.assertEqual(m["total_raw_observations"], 3)
            self.assertEqual(m["total_accepted_observations"], 1)
            self.assertEqual(m["total_rejected_observations"], 2)
            self.assertEqual(m["indexed_observations"], 1)
            self.assertEqual(m["site_matches"], 0)
            self.assertFalse(m["source_complete"])

    def test_network_block_is_not_zero_risk(self):
        def blocked(*args):
            raise OSError("Connection reset")
        with tempfile.TemporaryDirectory() as temp:
            m = run(Path(temp), requester=blocked,
                    strategies=(("unit", FEMA, {}, "GET"),))
            self.assertFalse(m["official_attribute_ingestion_succeeded"])
            self.assertIsNone(m["strategies"][0]["raw_count"])
            self.assertEqual(m["strategies"][0]["state"], "PROBED")
            self.assertEqual(m["indexed_observations"], 0)


if __name__ == "__main__":
    unittest.main()
