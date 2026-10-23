"""ORNL EAGLE-I 2025 original 15-min county sample FULL source QA fixtures."""
import csv,hashlib,json
from pathlib import Path
import sqlite3
import tempfile
import unittest

try:
    import duckdb
except ImportError:
    duckdb=None

from facilityrisk.lane_d.ingest_eaglei_2025 import (
    run,source_metadata,hash_file,SOURCE_NAME,SOURCE_ID,FIGSHARE
)


def write_source(root):
    path=Path(root)/"eaglei_2025.csv"
    with path.open("w",newline="",encoding="utf-8") as f:
        writer=csv.writer(f)
        writer.writerow(["fips_code","county","state","customers_out","run_start_time"])
        writer.writerows([
            ["01001","Autauga","Alabama","6","2025-01-01 00:00:00"],
            ["01003","Baldwin","Alabama","0","2025-01-01 00:15:00"],
            ["01001","Autauga","Alabama","6","2025-01-01 00:00:00"],
            ["01001","Autauga","Alabama","500","2025-01-02 00:00:00"],
            ["bad","Unknown","Alabama","4","2025-01-03 00:00:00"],
            ["01001","Autauga","Alabama","bad","2025-01-03 00:00:00"],
            ["01001","Autauga","Alabama","5","2026-01-01 00:00:00"],
            ["01001","Autauga","Alabama","5","2025-01-02 00:00:00"],
        ])
    md5=hashlib.md5(path.read_bytes()).hexdigest()
    meta={
        "id":24237376,"version":4,
        "doi":"10.6084/m9.figshare.24237376.v4",
        "license":{"name":"CC BY 4.0","url":"https://creativecommons.org/licenses/by/4.0/"},
        "files":[{
            "id":SOURCE_ID,"name":SOURCE_NAME,"size":path.stat().st_size,
            "computed_md5":md5,
            "download_url":"https://ndownloader.figshare.com/files/62164877"
        }],
    }
    meta_path=Path(root)/"source_meta.json";meta_path.write_text(json.dumps(meta))
    return path,meta_path


@unittest.skipUnless(duckdb is not None,"duckdb must be installed")
class OriginalEagleiTests(unittest.TestCase):
    def test_source_identity_and_ccby_require_trusted_original_manifest(self):
        with tempfile.TemporaryDirectory() as t:
            path,meta=write_source(t)
            report=source_metadata(meta,path,allow_fixture=True)
            self.assertEqual(report["original_source_csv_bytes"],path.stat().st_size)
            self.assertEqual(report["publisher_version"],4)
            self.assertEqual(report["publisher_license"]["name"],"CC BY 4.0")
            src=json.loads(meta.read_text())
            for mutate in [
                ("version",3),
                ("license",{"name":"Proprietary"}),
            ]:
                wrong=dict(src);wrong[mutate[0]]=mutate[1]
                (Path(t)/"tampered.json").write_text(json.dumps(wrong))
                with self.assertRaises(ValueError):
                    source_metadata(Path(t)/"tampered.json",path,allow_fixture=True)
            with self.assertRaises(ValueError):
                source_metadata(meta,path,allow_fixture=False)

    def test_complete_original_rows_and_parquet_vs_countyday_index_reconcile(self):
        with tempfile.TemporaryDirectory() as t:
            csv_path,metadata=write_source(t)
            out=Path(t)/"stage"
            m=run(csv_path,metadata,out,allow_fixture=True)
            self.assertEqual(m["downloaded_original_source_rows"],8)
            self.assertEqual(m["accepted_normalized_source_readings"],5)
            self.assertEqual(m["rejected_original_source_rows"],3)
            self.assertEqual(m["staged_readonly_parquet_original_reading_rows"],5)
            self.assertEqual(m["staged_county_day_original_reading_reconciliation"],5)
            self.assertEqual(m["distinct_county_fips_in_accepted_source"],2)
            self.assertEqual(m["repeated_same_county_timestamp_source_keys"],2)
            self.assertEqual(m["original_zero_customers_out_reading_rows"],1)
            self.assertEqual(m["min_reported_customers_out_in_one_source_reading"],0)
            self.assertEqual(m["max_reported_customers_out_in_one_source_reading"],500)
            self.assertEqual(m["persistent_backend_indexed"],0)
            self.assertEqual(m["deployed"],0)
            self.assertEqual(m["independently_verified_paid_insured_bi_claims"],0)
            with sqlite3.connect(out/"eaglei_2025_county_day_staging.sqlite") as c:
                self.assertEqual(c.execute("PRAGMA integrity_check").fetchone()[0],"ok")
                self.assertEqual(c.execute("SELECT COUNT(*) FROM observed_county_day").fetchone()[0],3)
                self.assertEqual(c.execute("""SELECT accepted_source_readings,
                      repeated_county_time_keys FROM observed_county_day
                      WHERE county_fips='01001' AND observed_date_utc='2025-01-01'""").fetchone(),(2,1))
            with duckdb.connect() as c:
                self.assertEqual(c.execute("SELECT COUNT(*) FROM read_parquet(?)",
                                           [str(out/"eaglei_2025_readings.parquet")]).fetchone()[0],5)

    def test_original_md5_and_provenance_fail_closed_when_bytes_change(self):
        with tempfile.TemporaryDirectory() as t:
            path,meta=write_source(t)
            path.write_bytes(path.read_bytes()+b"\n")
            with self.assertRaisesRegex(ValueError,"MD5/length"):
                source_metadata(meta,path,allow_fixture=True)

    def test_second_run_requires_separate_immutable_stage(self):
        with tempfile.TemporaryDirectory() as t:
            path,meta=write_source(t)
            out=Path(t)/"stage"
            first=run(path,meta,out,allow_fixture=True)
            with self.assertRaises(FileExistsError):
                run(path,meta,out,allow_fixture=True)
            second=run(path,meta,Path(t)/"repeat",allow_fixture=True)
            self.assertEqual(first["accepted_normalized_source_readings"],second["accepted_normalized_source_readings"])
            self.assertEqual(first["staged_parquet_sha256"],second["staged_parquet_sha256"])
            self.assertEqual(first["staged_sqlite_aggregate_sha256"],second["staged_sqlite_aggregate_sha256"])


if __name__=="__main__":
    unittest.main()
