import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.lane_a_install import install, stage_sources, validate


def archive(destination, items):
    with zipfile.ZipFile(destination, "w") as z:
        for name, raw in items:
            z.writestr(name, raw)


class LaneAProductionArtifactInstallerTests(unittest.TestCase):
    def test_reject_zip_slip_and_unknown_source_paths(self):
        for path in ("../outside.sqlite", "/tmp/outside.sqlite",
                     "lane_b/manifest.json", "whp_regions/../../private.txt",
                     "whp_regions\\manifest.json"):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as d:
                archive(Path(d) / "bad.zip", [(path, b"no")])
                with self.assertRaisesRegex(ValueError, "unsafe|outside"):
                    stage_sources(Path(d) / "extract",
                                  artifact_paths=[Path(d) / "bad.zip"])
                self.assertFalse((Path(d) / "outside.sqlite").exists())

    def test_reject_conflicting_same_source_path(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.zip", Path(d) / "b.zip"
            archive(a, [("paged_windows/raw/polygon.json", b'{"id":1}')])
            archive(b, [("paged_windows/raw/polygon.json", b'{"id":2}')])
            with self.assertRaisesRegex(ValueError, "Conflicting source artifacts"):
                stage_sources(Path(d) / "staged", artifact_paths=[a, b])

    def test_idempotent_identical_artifact_files_and_source_sha(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.zip", Path(d) / "b.zip"
            raw = b'{"count":12}'
            archive(a, [("paged_windows/raw/ids.json", raw)])
            archive(b, [("paged_windows/raw/ids.json", raw)])
            rows = stage_sources(Path(d) / "staged", artifact_paths=[a, b])
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows["paged_windows/raw/ids.json"]["sha256"],
                             hashlib.sha256(raw).hexdigest())

    def test_no_servable_pointer_after_failed_verification(self):
        with tempfile.TemporaryDirectory() as d:
            a = Path(d) / "bad.zip"
            archive(a, [("paged_windows/manifest.json", b'{"all_requested_windows_complete":false}')])
            with self.assertRaises(ValueError):
                install(Path(d) / "install", archives=[a], required=["fema_nfhl"])
            self.assertFalse((Path(d) / "install" / "current.json").exists())

    def test_only_sources_with_all_required_real_files_can_activate(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "fake-sources"
            source.mkdir()
            (source / "whp_official_index").mkdir()
            (source / "whp_official_index" / "manifest.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "Partially supplied required files"):
                validate(source, required=["usda_summary"])

    def test_atomic_pointer_and_deterministic_release_id_only_after_checks(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "source"
            (source / "whp_official_index").mkdir(parents=True)
            (source / "whp_official_index" / "status.json").write_text('{"confirmed":true}')
            fake = {
                "source_only_indexes": {"usda_summary": {"rows": 1}},
                "read_only_verified": True, "physical_site_matches": 0,
            }
            with patch("scripts.lane_a_install.validate", return_value=fake):
                a = install(Path(d) / "persistent", source_root=source,
                            required=["usda_summary"])
                b = install(Path(d) / "persistent", source_root=source,
                            required=["usda_summary"])
            self.assertEqual(a["release_id"], b["release_id"])
            ptr = json.loads((Path(d) / "persistent" / "current.json").read_text())
            self.assertEqual(ptr["release_id"], a["release_id"])
            self.assertEqual(ptr["verified_source_only_rows"]["usda_summary"], 1)
            self.assertEqual(ptr["site_matches_verified"], 0)
            self.assertFalse(ptr["published_by_lane_a"])
            stored = Path(d) / "persistent" / ptr["relative_root"] / "whp_official_index" / "status.json"
            self.assertEqual(stored.stat().st_mode & 0o222, 0)
            self.assertTrue(stored.exists())


if __name__ == "__main__":
    unittest.main()
