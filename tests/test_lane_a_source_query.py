import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from facilityrisk.lane_a_source_query import source_fema_polygon, source_whp_record


class LaneASourceReadOnlyTests(unittest.TestCase):
    def fake_whp(self, file):
        conn = sqlite3.connect(file)
        conn.executescript("""
            CREATE TABLE whp2023_geography(
                geography_type TEXT, native_geographic_id TEXT,
                raw_row_json TEXT,source_workbook_sha256 TEXT,
                source_zip_sha256 TEXT
            );
            CREATE TABLE whp2023_management(
                source_label TEXT,raw_row_json TEXT,
                source_workbook_sha256 TEXT,source_zip_sha256 TEXT
            );
        """)
        def record(kind, key, area):
            return json.dumps({
                "source_geography_type": kind,
                "native_geographic_id": key, "total_acres": area,
                "source_coverage": ("UNKNOWN_NO_AREA_VALUES"
                                    if area is None else "AGGREGATE_AREA_VALUES"),
                "original_xlsx_sha256": "b" * 64,
                "original_archive_sha256": "c" * 64,
            })
        conn.execute("INSERT INTO whp2023_geography VALUES(?,?,?,?,?)",
                     ("zip", "00029", record("zip", "00029", 1387.0), "b" * 64, "c" * 64))
        conn.execute("INSERT INTO whp2023_geography VALUES(?,?,?,?,?)",
                     ("zip", "10168", record("zip", "10168", None), "b" * 64, "c" * 64))
        conn.execute("INSERT INTO whp2023_management VALUES(?,?,?,?)",
                     ("Grand Total",record("management_jurisdiction", "Grand Total", 999),
                      "b" * 64,"c" * 64))
        conn.commit()
        conn.close()

    def fake_fema(self, file):
        conn = sqlite3.connect(file)
        conn.execute("""
            CREATE TABLE fema_source_features (
                source_key TEXT,objectid INTEGER,dfirm_id TEXT,fld_ar_id TEXT,
                flood_zone TEXT,zone_subtype TEXT,sfha_tf TEXT,source_cit TEXT,
                version_id TEXT,original_reply_sha256 TEXT,
                geometry_tolerance_degrees REAL,feature_json TEXT
            )
        """)
        conn.execute("INSERT INTO fema_source_features VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                     ("dfirm:22071C:fld_ar:22071C_6650", 42, "22071C",
                      "22071C_6650", "AE", None, "T", "22071C_STUDY13",
                      "1.1.1.0", "a" * 64, 0.000005, "{}"))
        conn.commit()
        conn.close()

    def test_source_grain_identity_and_unknown_area(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "whp.sqlite"
            self.fake_whp(path)
            r = source_whp_record(path, "zip", "00029")
            self.assertEqual(r["native_geographic_id"], "00029")
            self.assertEqual(r["total_acres"], 1387.0)
            self.assertFalse(r["physical_site_verified"])
            self.assertFalse(r["app_deployed"])
            unassessed = source_whp_record(path, "zip", "10168")
            self.assertIsNone(unassessed["total_acres"])
            self.assertEqual(unassessed["source_coverage"], "UNKNOWN_NO_AREA_VALUES")
            total = source_whp_record(path, "management_jurisdiction", "Grand Total")
            self.assertEqual(total["source_grain" if "source_grain" in total else "source_geography_type"],
                             "management_jurisdiction")
            self.assertEqual(source_whp_record(path, "zip", "99999")["risk_assessment"],
                             "UNKNOWN")
            with self.assertRaisesRegex(ValueError, "retain"):
                source_whp_record(path, "zip", "29")
            with self.assertRaisesRegex(ValueError, "grain"):
                source_whp_record(path, "company", "00029")

    def test_fema_polygon_native_key_not_insured_site(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "fema.sqlite"
            self.fake_fema(path)
            row = source_fema_polygon(path, "dfirm:22071C:fld_ar:22071C_6650")
            self.assertEqual(row["flood_zone"], "AE")
            self.assertEqual(row["geometry_precision"], "GENERALIZED_REVIEW_REQUIRED")
            self.assertEqual(row["source_response_sha256"], "a" * 64)
            self.assertFalse(row["effective_date_verified"])
            self.assertFalse(row["physical_site_verified"])
            self.assertFalse(row["app_deployed"])
            absent = source_fema_polygon(path, "dfirm:123:fld_ar:unknown")
            self.assertEqual(absent["risk_assessment"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
