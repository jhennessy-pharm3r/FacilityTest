import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.lane_a_whp_classified import CLASSES, IMAGE_SERVER, parse_class, run


def mock_classified_api(operation, params):
    if not operation:
        response = {"name": "USFS WHP Classified 2023", "pixelType": "U8",
                    "pixelSizeX": 270, "pixelSizeY": 270,
                    "noDataValues": [255], "minValues": [1], "maxValues": [7]}
    else:
        geom = json.loads(params["geometry"])
        # Five geographic probes sample four hazards + one non-burnable.
        value = 6 if geom["x"] > -99.97 and geom["y"] < 40 else (255 if geom["x"] < -100.06 and geom["y"] < 40 else 3)
        response = {"value": str(value)}
    raw = json.dumps(response, sort_keys=True).encode()
    return response, raw, IMAGE_SERVER + "/" + operation


class ClassifiedWHPTests(unittest.TestCase):
    def test_all_source_classes_and_special_masks(self):
        self.assertEqual(len(CLASSES), 7)
        for code in range(1, 6):
            self.assertEqual(parse_class({"value": str(code)}, {255})[0],
                             "BURNABLE_HAZARD_CLASS")
        self.assertEqual(parse_class({"value": "6"}, {255}),
                         ("NON_BURNABLE_MASK", 6, "Non-burnable"))
        self.assertEqual(parse_class({"value": "7"}, {255}),
                         ("WATER_MASK", 7, "Water"))
        self.assertEqual(parse_class({"value": "255"}, {255}),
                         ("NO_DATA", None, None))
        self.assertEqual(parse_class({"value": "0"}, {255}),
                         ("REJECTED_INVALID_CLASS", None, None))
        self.assertEqual(parse_class({"value": "a bad response"}, {255})[0],
                         "REJECTED_INVALID_CLASS")

    def test_source_receipts_and_nonburnable_reconcile(self):
        with tempfile.TemporaryDirectory() as temp:
            m = run(Path(temp), fetch=mock_classified_api,
                    regions={"fixture": (-100.0, 40.0)}, workers=2)
            self.assertTrue(m["sample_complete"])
            self.assertEqual(m["received"], 5)
            self.assertEqual(m["indexed_observations"], 5)
            self.assertEqual(m["burnable_classes"], 3)
            self.assertEqual(m["special_mask_classes"], 1)
            self.assertEqual(m["nodata"], 1)
            self.assertEqual(m["class_distribution"], {
                "Moderate": 3, "Non-burnable": 1, "NO_DATA": 1
            })
            self.assertEqual(m["actual_site_matches"], 0)
            self.assertFalse(m["national_raster_complete"])
            for receipt in [m["metadata"]] + m["records"]:
                p = Path(temp) / "raw" / receipt["raw_file"]
                self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),
                                 receipt["raw_sha256"])

    def test_error_does_not_claim_zero_hazard(self):
        def unreachable(*args):
            raise OSError("GeoPlatform unavailable")
        with tempfile.TemporaryDirectory() as temp:
            m = run(Path(temp), fetch=unreachable,
                    regions={"fixture": (-100, 40)})
            self.assertFalse(m["sample_complete"])
            self.assertIsNone(m["metadata"])
            self.assertEqual(m["received"], 0)
            self.assertEqual(m["actual_site_matches"], 0)

    def test_classified_malformed_numeric_fails(self):
        def bad(operation, params):
            if operation == "":
                return mock_classified_api(operation, params)
            data = {"value": "18"}
            raw = json.dumps(data).encode()
            return data, raw, IMAGE_SERVER + "/" + operation
        with tempfile.TemporaryDirectory() as temp:
            m = run(Path(temp), fetch=bad, regions={"fixture": (-100, 40)})
            self.assertFalse(m["sample_complete"])
            self.assertEqual(m["received"], 5)
            self.assertEqual(m["rejected"], 5)
            self.assertEqual(m["indexed_observations"], 0)


if __name__ == "__main__":
    unittest.main()
