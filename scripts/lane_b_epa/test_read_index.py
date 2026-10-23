import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from scripts.lane_b_epa.ingest import ingest
from scripts.lane_b_epa.read_index import lookup,source_status,InvalidSourceIndex

class LaneBReadOnlyIndexTests(unittest.TestCase):
    def test_rcra_native_id_and_activity_location_are_distinct(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw=root/"RCRA_EVALUATIONS.csv"
            raw.write_text("ID_NUMBER,ACTIVITY_LOCATION,EVALUATION_IDENTIFIER,EVALUATION_START_DATE,EVALUATION_TYPE\n"
                           "ALD0001,AL,CE123,03/12/2024,CEI\n"
                           "ALD0001,GA,GA888,06/01/2025,CEI\n")
            out=root/"index";m=ingest("rcra",raw,out,source_url="https://echo.epa.gov/files/echodownloads/rcra_downloads.zip")
            status=source_status(out/"rcra.sqlite",out/"rcra.manifest.json","rcra")
            self.assertEqual(status["indexed_rows"],2)
            self.assertEqual(status["source_state"],"INDEXED_NOT_DEPLOYED")
            allrows=lookup(out/"rcra.sqlite",out/"rcra.manifest.json","rcra","ALD0001")
            self.assertEqual(allrows["observations_available"],2)
            al=lookup(out/"rcra.sqlite",out/"rcra.manifest.json","rcra","ALD0001",activity_location="AL")
            self.assertEqual(al["observations_available"],1)
            self.assertEqual(al["rows"][0]["native_event_identifier"],"CE123")
            self.assertEqual(al["rows"][0]["date"],"2024-03-12")
            self.assertEqual(al["rows"][0]["regulatory_observation_kind"],"rcra_evaluation")
            self.assertEqual(al["physical_site_linkage"],"NOT_REVIEWED")
    def test_tampering_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw=root/"tri.csv";raw.write_text("2. TRIFD,1. YEAR\nX0001,2024\n")
            out=root/"index";ingest("tri",raw,out,year=2024)
            manifest=out/"tri.manifest.json";m=json.loads(manifest.read_text())
            m["indexed_rows"]=500000;manifest.write_text(json.dumps(m))
            with self.assertRaises(InvalidSourceIndex):
                source_status(out/"tri.sqlite",manifest,"tri")
    def test_injection_is_exact_match(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw=root/"echo.csv";raw.write_text("REGISTRY_ID,FAC_NAME\nA001,Factory\n")
            out=root/"index";ingest("echo",raw,out)
            result=lookup(out/"echo.sqlite",out/"echo.manifest.json","echo","A001' OR 1=1 --")
            self.assertEqual(result["observations_available"],0)
            with self.assertRaises(ValueError):lookup(out/"echo.sqlite",out/"echo.manifest.json","echo","A001",limit=99999)

if __name__=="__main__":unittest.main()
