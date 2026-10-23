import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from facilityrisk.lane_a_installed import (
    installed_release, index_file, query_raster_probe, query_publisher_id,
)


class InstalledPublisherSourceReadOnlyTests(unittest.TestCase):
    def create_release(self, destination):
        destination = Path(destination)
        release_id = "a" * 24
        data = destination / "releases" / release_id / "data" / "lane_a"
        (data / "whp_regions").mkdir(parents=True)
        (data / "whp_classified").mkdir()
        (data / "whp_official_index").mkdir()
        continuous = data / "whp_regions/whp-regional-source-only.sqlite"
        classified = data / "whp_classified/whp-classified-source-only.sqlite"
        summary = data / "whp_official_index/whp2023-source-geographies.sqlite"
        db = sqlite3.connect(continuous)
        db.execute("""CREATE TABLE whp_geographic_probes(
            region TEXT,probe_index INTEGER,longitude REAL,latitude REAL,
            whp_release TEXT,source_url TEXT,raw_sha256 TEXT,
            pixel_state TEXT,pixel_value REAL)""")
        db.execute("INSERT INTO whp_geographic_probes VALUES(?,?,?,?,?,?,?,?,?)",
                   ("alaska",0,-150.1,61.4,"2023",
                    "https://imagery.geoplatform.gov/iipp/", "b"*64,
                    "VALUE",12345))
        db.commit()
        db.close()
        db = sqlite3.connect(classified)
        db.execute("""CREATE TABLE usfs_whp_classified_probes(
            region TEXT,probe_index INTEGER,longitude REAL,latitude REAL,
            raster_release TEXT,source_url TEXT,raw_sha256 TEXT,
            class_state TEXT,class_value INTEGER,class_label TEXT)""")
        db.execute("INSERT INTO usfs_whp_classified_probes VALUES(?,?,?,?,?,?,?,?,?,?)",
                   ("alaska",0,-150.1,61.4,"2023",
                    "https://imagery.geoplatform.gov/iipp/", "c"*64,
                    "BURNABLE_HAZARD_CLASS",4,"High"))
        db.commit()
        db.close()
        db = sqlite3.connect(summary)
        db.execute("""CREATE TABLE whp2023_geography (
            geography_type TEXT,native_geographic_id TEXT,
            raw_row_json TEXT,source_workbook_sha256 TEXT,
            source_zip_sha256 TEXT)""")
        db.execute("""CREATE TABLE whp2023_management(
            source_label TEXT,raw_row_json TEXT,
            source_workbook_sha256 TEXT,source_zip_sha256 TEXT)""")
        record = {
            "source_geography_type":"zip","native_geographic_id":"00029",
            "source_coverage":"AGGREGATE_AREA_VALUES","total_acres":1387,
            "original_xlsx_sha256":"d"*64,"original_archive_sha256":"e"*64}
        db.execute("INSERT INTO whp2023_geography VALUES(?,?,?,?,?)",
                   ("zip","00029",json.dumps(record),"d"*64,"e"*64))
        db.commit()
        db.close()
        pointer = {
            "schema_version":"facility_risk_lane_a_read_only_release_v1",
            "release_id":release_id,
            "relative_root":"releases/"+release_id+"/data/lane_a",
            "verified_source_only_rows":{
                "usda_continuous":1,"usda_classified":1,"usda_summary":1},
        }
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "current.json").write_text(json.dumps(pointer))
        return data

    def test_native_readonly_release_queries_remain_unmatched(self):
        with tempfile.TemporaryDirectory() as d:
            self.create_release(d)
            cont = query_raster_probe(d,"usda_continuous",region="alaska",grid_index=0)
            cat = query_raster_probe(d,"usda_classified",region="alaska",grid_index=0)
            self.assertEqual(cont["raster_release"], "2023")
            self.assertEqual(cont["pixel_value"],12345)
            self.assertEqual(cat["raster_release"], "2023")
            self.assertEqual(cat["class_label"],"High")
            self.assertFalse(cat["physical_site_verified"])
            self.assertIsNone(cat["source_native_pixel_id"])
            original = query_publisher_id(d,"usda_summary",
                geography_type="zip",original_id="00029")
            self.assertEqual(original["native_geographic_id"],"00029")
            self.assertFalse(original["physical_site_verified"])
            absent = query_raster_probe(d,"usda_classified",
                region="alaska",grid_index=4)
            self.assertEqual(absent["hazard_coverage"],"UNKNOWN")
            with self.assertRaisesRegex(ValueError, "region/grid"):
                query_raster_probe(d,"usda_continuous",region="../etc",grid_index=0)

    def test_untrusted_release_pointer_cannot_escape_storage_root(self):
        with tempfile.TemporaryDirectory() as d:
            self.create_release(d)
            p = Path(d) / "current.json"
            value = json.loads(p.read_text())
            value["relative_root"] = "../../outside"
            p.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "non-canonical"):
                installed_release(d)

    def test_missing_source_must_not_be_queried_as_zero_risk(self):
        with tempfile.TemporaryDirectory() as d:
            self.create_release(d)
            with self.assertRaisesRegex(FileNotFoundError, "not installed"):
                index_file(d,"fema_nfhl")
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                index_file(d,"lane_b")
            with self.assertRaisesRegex(ValueError, "do not publish"):
                query_publisher_id(d,"usda_continuous",original_id="test")


if __name__=="__main__":
    unittest.main()
