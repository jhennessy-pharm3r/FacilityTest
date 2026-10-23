import hashlib
import tempfile
import unittest
import urllib.error
from pathlib import Path

from scripts.lane_a_fema_distribution import FEMA_LAYER, WFS, run, wfs_feature_types

CAPS = b'''<?xml version="1.0"?>
<wfs:WFS_Capabilities xmlns:wfs="http://www.opengis.net/wfs/2.0"
 xmlns:ns="http://fema.gov/">
<wfs:FeatureTypeList><wfs:FeatureType>
<wfs:Name>public_NFHL:S_Fld_Haz_Ar</wfs:Name>
</wfs:FeatureType></wfs:FeatureTypeList></wfs:WFS_Capabilities>'''


def fake_rest(params):
    assert params["returnCountOnly"] == "true"
    return {"count": 2030405}, b'{"count":2030405}', FEMA_LAYER + "/query", {
        "http_method": "POST", "attempt_count": 2,
    }


def fake_wfs():
    return CAPS, WFS + "?service=WFS&request=GetCapabilities"


class FederalNFHLDistributionTests(unittest.TestCase):
    def test_realistic_count_is_not_downloaded_polygon_census(self):
        with tempfile.TemporaryDirectory() as temp:
            m = run(Path(temp), rest=fake_rest, wfs=fake_wfs)
            self.assertEqual(m["reported_current_service_feature_count"], 2030405)
            self.assertEqual(m["national_downloaded_polygons"], 0)
            self.assertEqual(m["source_only_indexed_polygons"], 0)
            self.assertFalse(m["full_national_download_verified"])
            self.assertEqual(m["wfs_flood_zone_candidates"], ["public_NFHL:S_Fld_Haz_Ar"])
            self.assertTrue(m["at_least_one_official_distribution_reachable"])
            raw = (Path(temp) / "raw" / m["wfs_receipt"]["raw_file"]).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), m["wfs_receipt"]["sha256"])
            self.assertEqual(m["rest_count_receipt"]["transport"]["http_method"], "POST")

    def test_blocked_official_access_keeps_count_unknown(self):
        def unavailable(*args):
            raise urllib.error.URLError("official source unreachable")
        with tempfile.TemporaryDirectory() as temp:
            m = run(Path(temp), rest=unavailable, wfs=unavailable)
            self.assertFalse(m["at_least_one_official_distribution_reachable"])
            self.assertIsNone(m["reported_current_service_feature_count"])
            self.assertEqual(m["wfs_state"], "PROBED")
            self.assertEqual(m["national_downloaded_polygons"], 0)

    def test_fema_wfs_requires_capabilities_not_html(self):
        with self.assertRaises(ValueError):
            wfs_feature_types(b"<html><body>maintenance</body></html>")


if __name__ == "__main__":
    unittest.main()
