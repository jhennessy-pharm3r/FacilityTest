import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.verify_lane_a_archive import verify_dir


class ArchivedLaneAProofTests(unittest.TestCase):
    def make_archive(self, root):
        dest = root / "live_validation"
        (dest / "raw").mkdir(parents=True)
        raw = b'{"features":[{"attributes":{"OBJECTID":7}}]}'
        (dest / "raw" / "fema.test.json").write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        receipt = {"raw_file": "fema.test.json", "raw_sha256": digest, "bytes": len(raw)}
        manifest = {"sources": {
            "fema_nfhl": {
                "metadata": {"state": "PROBED"}, "samples": [receipt],
                "sample_raw": 1, "sample_accepted": 1,
                "sample_rejected": 0, "indexed_observations": 1,
            },
            "usfs_whp_continuous_2023": {
                "metadata": {"state": "PROBED"}, "samples": [],
                "sample_raw": 0, "sample_accepted": 0,
                "sample_rejected": 0, "indexed_observations": 0,
            },
        }}
        (dest / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        db = sqlite3.connect(dest / "source-only.sqlite")
        db.executescript("""
            CREATE TABLE fema_source_observations(source_key TEXT);
            CREATE TABLE usfs_raster_observations(probe TEXT);
            INSERT INTO fema_source_observations VALUES ('service_objectid:7');
        """)
        db.commit()
        db.close()
        return dest

    def test_recomputes_original_hash_and_sqlite_counts(self):
        with tempfile.TemporaryDirectory() as d:
            dest = self.make_archive(Path(d))
            qa = verify_dir(Path(d))
            self.assertEqual(qa["total_preserved_source_responses"], 1)
            self.assertEqual(qa["source_directories"]["live_validation"]
                             ["tables"]["fema_nfhl"]["indexed_observations"], 1)

    def test_corrupt_response_fails_checksum(self):
        with tempfile.TemporaryDirectory() as d:
            dest = self.make_archive(Path(d))
            (dest / "raw" / "fema.test.json").write_bytes(b'{"tampered":true}')
            with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
                verify_dir(Path(d))

    def test_corrupt_index_count_fails(self):
        with tempfile.TemporaryDirectory() as d:
            dest = self.make_archive(Path(d))
            db = sqlite3.connect(dest / "source-only.sqlite")
            db.execute("DELETE FROM fema_source_observations")
            db.commit()
            db.close()
            with self.assertRaisesRegex(ValueError, "Indexed count mismatch"):
                verify_dir(Path(d))


if __name__ == "__main__":
    unittest.main()
