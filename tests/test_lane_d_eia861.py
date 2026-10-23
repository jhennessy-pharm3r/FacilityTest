import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from facilityrisk.lane_d.ingest_eia861 import normalize, run

class LaneDTests(unittest.TestCase):
    def test_ids_duplicates_null_and_provenance(self):
        raw = ("Metadata row\nUtility Number,Utility Name,State,SAIDI With Major Events,SAIFI\n"
               "101,Utility One,ME,42.5,1.2\n"
               "101,Utility One,ME,42.5,1.2\n"
               "102,Utility Two,NY,,\n"
               "not-an-id,Invalid,NY,9,2\n")
        accepted, rejected, dup, null = normalize("Reliability_2025.csv", raw.encode(), 2025)
        self.assertEqual((len(accepted), len(rejected), dup, null), (2, 2, 1, 1))
        self.assertEqual(accepted[0]["source_utility_id"], "101")
        self.assertEqual(accepted[0]["facility_match_status"], "NOT_ASSESSED")
        self.assertEqual({b["reason"] for b in rejected}, {"invalid_utility_id", "duplicate_exact_row"})
    def test_end_to_end_local_archive(self):
        with tempfile.TemporaryDirectory() as t:
            archive = Path(t) / "source.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("Reliability_2025.csv", "Utility Number,State,SAIDI\n0101,ME,25\n")
                z.writestr("unrelated.csv", "anything\n")
            m = run(2025, Path(t)/"out", archive)
            self.assertEqual((m["accepted"], m["rejected"], m["indexed"], m["deployed"]), (1,0,0,0))
            self.assertEqual(m["unique_utility_ids"], 1)
            self.assertEqual(m["members"][0]["accepted"], 1)
            self.assertTrue((Path(t)/"out"/"manifest.json").exists())
            self.assertEqual(json.loads((Path(t)/"out"/"eia861_reliability.jsonl").read_text())["source_utility_id"] if False else json.loads((Path(t)/"out"/"eia861_reliability.jsonl").read_text().strip())["source_utility_id"], "0101")
    def test_no_reliability_file_is_failure(self):
        with tempfile.TemporaryDirectory() as t:
            archive = Path(t)/"source.zip"
            with zipfile.ZipFile(archive,"w") as z:
                z.writestr("Utility_2025.csv","Utility Number\n1\n")
            with self.assertRaisesRegex(ValueError, "No EIA-861 reliability"):
                run(2025,Path(t)/"out",archive)

if __name__ == "__main__":
    unittest.main()
