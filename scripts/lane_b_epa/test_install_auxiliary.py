import gzip
import tempfile
import unittest
from pathlib import Path

from scripts.lane_b_epa.ingest import ingest
from scripts.lane_b_epa.install_auxiliary import install_tri_year,install_public_rmp
from scripts.lane_b_epa.rmp_public import import_public

class PrivateAuxiliarySnapshotTests(unittest.TestCase):
    def test_tri_annual_source_vintage_hash_and_exact_lookup(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw=root/"original_tri.csv"
            raw.write_text("1. YEAR,2. TRIFD,37. CHEMICAL,50. UNIT OF MEASURE,107. TOTAL RELEASES\n"
                "2024,IN123456,TEST,Pounds,9\n",encoding="utf-8")
            source_url="https://data.epa.gov/efservice/downloads/tri/mv_tri_basic_download/2024_US/csv"
            out=root/"import";m=ingest("tri",raw,out,source_url=source_url,year=2024)
            zipped=root/"tri.sqlite.gz"
            with (out/"tri.sqlite").open("rb") as source,gzip.open(zipped,"wb") as target:
                target.write(source.read())
            parent=root/"private";parent.mkdir()
            receipt=install_tri_year(2024,raw,zipped,out/"tri.manifest.json",parent/"tri_2024")
            self.assertEqual(receipt["private_staged_index_rows"],1)
            self.assertEqual(receipt["original_source_rows"],1)
            self.assertEqual(receipt["production_deployed"],0)
            self.assertEqual(receipt["source_sqlite_sha256"],m["index_sha256"])
            self.assertTrue((parent/"tri_2024"/"tri.sqlite").exists())
            with self.assertRaises(FileExistsError):
                install_tri_year(2024,raw,zipped,out/"tri.manifest.json",parent/"tri_2024")
            with self.assertRaises(ValueError):
                install_tri_year(2023,raw,zipped,out/"tri.manifest.json",parent/"tri_2023")
            with raw.open("ab") as data:data.write(b"tamper")
            with self.assertRaises(ValueError):
                install_tri_year(2024,raw,zipped,out/"tri.manifest.json",parent/"tri_2024_bad")
            self.assertFalse((parent/"tri_2024_bad").exists())

    def test_public_rmp_source_only_and_tamper_guards(self):
        def fake(params):
            if "returnCountOnly" in params:return {"count":2}
            if "returnIdsOnly" in params:return {"objectIds":[1,2]}
            return {"features":[{"attributes":{"OBJECTID":int(value),"REGISTRY_ID":"FRS"+value,
                "PGM_SYS_ID":"RMP"+value,"LATITUDE83":42.2,"LONGITUDE83":-75.6}}
                for value in params["objectIds"].split(",")]}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            raw=root/"rmp_import";manifest=import_public(raw,fetch=fake)
            parent=root/"private";parent.mkdir()
            receipt=install_public_rmp(raw/"rmp_frs_public.raw.jsonl",
                raw/"rmp_frs_public.sqlite",raw/"rmp_frs_public.manifest.json",
                parent/"rmp_public")
            self.assertEqual(receipt["private_staged_index_rows"],2)
            self.assertEqual(receipt["distinct_native_program_ids"],2)
            self.assertEqual(receipt["source_sqlite_sha256"],manifest["index_sha256"])
            self.assertEqual(receipt["production_deployed"],0)
            self.assertEqual(receipt["verified_insured_property_links"],0)
            with self.assertRaises(FileExistsError):
                install_public_rmp(raw/"rmp_frs_public.raw.jsonl",raw/"rmp_frs_public.sqlite",
                    raw/"rmp_frs_public.manifest.json",parent/"rmp_public")
            with (raw/"rmp_frs_public.raw.jsonl").open("ab") as f:f.write(b"tamper")
            with self.assertRaises(ValueError):
                install_public_rmp(raw/"rmp_frs_public.raw.jsonl",raw/"rmp_frs_public.sqlite",
                    raw/"rmp_frs_public.manifest.json",parent/"rmp_bad")
            self.assertFalse((parent/"rmp_bad").exists())

if __name__=="__main__":unittest.main()
