import hashlib,json,sqlite3,tempfile,unittest
from pathlib import Path
from scripts.lane_b_epa.chunk_index import pack,restore
from scripts.lane_b_epa.ingest import ingest

class ChunkStagingTests(unittest.TestCase):
    def test_roundtrip_real_sqlite_and_tampered_part_fail(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw=root/"echo.csv"
            raw.write_text("REGISTRY_ID,FAC_NAME,FAC_LAT,FAC_LONG\nA1,Facility,44,-69\nB2,Plant,43,-71\n")
            stage=root/"ingest"
            manifest=ingest("echo",raw,stage,source_url="https://echo.epa.gov/files/echodownloads/echo_exporter.zip")
            index=stage/"echo.sqlite"
            packed=pack(index,stage/"echo.manifest.json",root/"chunks",chunk_bytes=1031)
            self.assertGreater(len(packed["chunks"]),1)
            audit=restore(root/"chunks"/"chunk-manifest.json",root/"chunks",verify_only=True)
            self.assertTrue(audit["verified_only"])
            self.assertEqual(audit["sqlite_sha256"],manifest["index_sha256"])
            restored=root/"restored.sqlite"
            summary=restore(root/"chunks"/"chunk-manifest.json",root/"chunks",restored)
            self.assertEqual(summary["sqlite_sha256"],manifest["index_sha256"])
            with sqlite3.connect(restored) as con:
                self.assertEqual(con.execute("SELECT COUNT(*) FROM observation").fetchone()[0],2)
            path=root/"chunks"/packed["chunks"][0]["file"]
            with path.open("ab") as out:out.write(b"bad")
            with self.assertRaises(ValueError):
                restore(root/"chunks"/"chunk-manifest.json",root/"chunks",root/"should_not_exist.sqlite")
            self.assertFalse((root/"should_not_exist.sqlite").exists())
if __name__=="__main__":unittest.main()
