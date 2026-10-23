import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.lane_a_fema_msc_bulk import PRODUCT_ID, download, run


def fake_official_zip(pid):
    f = io.BytesIO()
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("NFHL_51013C.gdb/a00000001.gdbtable", b"source-geodatabase")
        z.writestr("NFHL_51013C.gdb/a00000001.gdbtablx", b"indexes")
    return f.getvalue(), "https://msc.fema.gov/portal/downloadProduct?productID=" + pid


class FEMABulkCountyTests(unittest.TestCase):
    def test_preserves_product_id_and_does_not_invent_polygons(self):
        with tempfile.TemporaryDirectory() as d:
            m = run(Path(d), fetch=fake_official_zip)
            self.assertEqual(m["product_id"], "NFHL_51013C")
            self.assertTrue(m["original_archive_downloaded"])
            self.assertTrue(m["file_format_verified"])
            self.assertEqual(m["archive_members"], 2)
            self.assertIsNone(m["normalized_polygon_count"])
            self.assertEqual(m["indexed_polygon_count"], 0)
            self.assertEqual(m["physically_correlated_insured_sites"], 0)

    def test_html_response_does_not_imply_zip_ingest(self):
        with tempfile.TemporaryDirectory() as d:
            m = run(Path(d), fetch=lambda x: (b"<html>not available</html>", "https://msc.fema.gov"))
            self.assertFalse(m["original_archive_downloaded"])
            self.assertFalse(m["file_format_verified"])
            self.assertIsNone(m["normalized_polygon_count"])
            self.assertIn("not a ZIP", m["error"])


if __name__ == "__main__":
    unittest.main()
