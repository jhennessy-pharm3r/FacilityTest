import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.lane_a_whp_official_summary import run


def fixture():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Summary/regions.csv", "STATE,AREA_HA\nCA,123\nAK,456\n")
        z.writestr("Readme.txt", "Source: USDA Forest Service\n")
    raw = buf.getvalue()
    return raw, "https://research.fs.usda.gov/official.zip"


class WFPSummaryArchiveTests(unittest.TestCase):
    def test_original_archive_sha_and_member_row_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            m = run(Path(temp), fetch=fixture)
            self.assertTrue(m["inventory_verified"])
            self.assertEqual(m["archive_member_count"], 2)
            self.assertEqual(len(m["source_members"]), 2)
            csv_rows = next(x for x in m["source_members"] if x["format"] == "csv")
            self.assertEqual(csv_rows["field_names"], ["STATE", "AREA_HA"])
            self.assertEqual(csv_rows["non_header_rows"], 2)
            self.assertEqual(m["archive_sha256"], hashlib.sha256(
                (Path(temp) / "whp2023_official_summaries.zip").read_bytes()).hexdigest())
            self.assertEqual(m["normalized_aggregate_rows"], 0)
            self.assertEqual(m["indexed_aggregate_rows"], 0)
            self.assertFalse(m["complete_source_raster"])

    def test_invalid_source_zip_has_honest_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            m = run(Path(temp), fetch=lambda: (b"<html>Forbidden</html>", "https://bad.example"))
            self.assertFalse(m["inventory_verified"])
            self.assertFalse(m["source_downloaded"])
            self.assertIsNone(m["archive_sha256"])


if __name__ == "__main__":
    unittest.main()
