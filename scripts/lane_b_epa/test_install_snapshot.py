import sqlite3,tempfile,unittest
from pathlib import Path
from zipfile import ZipFile
from scripts.lane_b_epa.ingest import ingest
from scripts.lane_b_epa.chunk_index import pack
from scripts.lane_b_epa.install_snapshot import prepare

class PrivateSourceOnlyInstallerTests(unittest.TestCase):
    def test_verified_immutable_staging_and_no_rewrite(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);raw=base/"original.zip"
            with ZipFile(raw,"w") as f:
                f.writestr("ECHO_EXPORTER.csv","REGISTRY_ID,FAC_NAME,FAC_LAT,FAC_LONG\n"
                                                    "E001,Factory A,41,-72\n"
                                                    ",Unkeyed Source Row,42,-73\n")
            imported=base/"import"
            m=ingest("echo",raw,imported,source_url="https://echo.epa.gov/files/echodownloads/echo_exporter.zip")
            chunks=base/"parts"
            p=pack(imported/"echo.sqlite",imported/"echo.manifest.json",chunks,chunk_bytes=1024)
            home=base/"private"
            home.mkdir()
            snapshot=home/"echo-source-20261023"
            receipt=prepare("echo",raw,imported/"echo.manifest.json",chunks,
                            chunks/"chunk-manifest.json",snapshot)
            self.assertEqual(receipt["indexed_staging_rows"],1)
            self.assertEqual(receipt["rejected_quarantined"],1)
            self.assertEqual(receipt["authenticated_production_deployed"],0)
            self.assertEqual(receipt["physical_site_matches_approved"],0)
            self.assertEqual(receipt["original_archive_sha256"],m["archive_sha256"])
            self.assertEqual(receipt["source_sqlite_sha256"],m["index_sha256"])
            self.assertTrue((snapshot/"official-echo.zip").exists())
            self.assertTrue((snapshot/"install-receipt.json").exists())
            with sqlite3.connect(snapshot/"echo.sqlite") as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM rejected").fetchone()[0],1)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM observation").fetchone()[0],1)
            with self.assertRaises(FileExistsError):
                prepare("echo",raw,imported/"echo.manifest.json",chunks,
                        chunks/"chunk-manifest.json",snapshot)
    def test_corrupt_original_archive_fails_without_target_directory(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);raw=base/"original.zip"
            with ZipFile(raw,"w") as f:
                f.writestr("ECHO_EXPORTER.csv","REGISTRY_ID,FAC_NAME\nE001,Plant\n")
            imported=base/"import";ingest("echo",raw,imported)
            chunks=base/"parts"
            pack(imported/"echo.sqlite",imported/"echo.manifest.json",chunks)
            with raw.open("ab") as f:f.write(b"tamper")
            home=base/"private";home.mkdir();dest=home/"nope"
            with self.assertRaises(ValueError):
                prepare("echo",raw,imported/"echo.manifest.json",chunks,
                        chunks/"chunk-manifest.json",dest)
            self.assertFalse(dest.exists())
if __name__=="__main__":unittest.main()
