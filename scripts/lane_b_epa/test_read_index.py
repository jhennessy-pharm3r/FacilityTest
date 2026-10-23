import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
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
    def test_rcra_enforcement_native_join_never_matches_wrong_location(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);archive=root/"src.zip"
            with ZipFile(archive,"w") as f:
                f.writestr("RCRA_FACILITIES.csv","ID_NUMBER,ACTIVITY_LOCATION,FACILITY_NAME,LATITUDE83,LONGITUDE83\n"
                    "TXD123,TX,Reporting Handler,32,-97\n")
                f.writestr("RCRA_ENFORCEMENTS.csv","ID_NUMBER,ACTIVITY_LOCATION,ENFORCEMENT_IDENTIFIER,ENFORCEMENT_ACTION_DATE\n"
                    "TXD123,TX,EN1,04/01/2024\n"
                    "TXD123,OK,EN2,05/02/2024\n")
            out=root/"index";ingest("rcra",archive,out)
            good=lookup(out/"rcra.sqlite",out/"rcra.manifest.json","rcra","TXD123",activity_location="TX")
            match=[x for x in good["rows"] if x["regulatory_observation_kind"]=="rcra_enforcement"][0]
            self.assertEqual(match["rcra_same_source_handler_context"]["reported_handler_latitude"],32.0)
            self.assertFalse(match["rcra_same_source_handler_context"]["physical_property_match_verified"])
            wrong=lookup(out/"rcra.sqlite",out/"rcra.manifest.json","rcra","TXD123",activity_location="OK")
            self.assertEqual(wrong["rows"][0]["rcra_same_source_handler_context"]["join_state"],"no_unique_regulator_handler_match")
    def test_tampering_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw=root/"tri.csv";raw.write_text("2. TRIFD,1. YEAR\nX0001,2024\n")
            out=root/"index";ingest("tri",raw,out,year=2024)
            manifest=out/"tri.manifest.json";m=json.loads(manifest.read_text())
            m["indexed_rows"]=500000;manifest.write_text(json.dumps(m))
            with self.assertRaises(InvalidSourceIndex):
                source_status(out/"tri.sqlite",manifest,"tri")
    def test_same_size_and_mtime_replaced_sqlite_invalidates_integrity_cache(self):
        import os
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw=root/"echo.csv"
            raw.write_text("REGISTRY_ID,FAC_NAME\nE001,Warehouse\n")
            out=root/"out";ingest("echo",raw,out)
            db=out/"echo.sqlite";meta=out/"echo.manifest.json"
            self.assertEqual(source_status(db,meta,"echo")["indexed_rows"],1)
            original_stat=db.stat()
            tampered=db.with_suffix(".swap")
            data=bytearray(db.read_bytes())
            data[-1] ^= 1
            tampered.write_bytes(data)
            os.utime(tampered,ns=(original_stat.st_atime_ns,original_stat.st_mtime_ns))
            os.replace(tampered,db)
            self.assertEqual(db.stat().st_mtime_ns,original_stat.st_mtime_ns)
            self.assertEqual(db.stat().st_size,original_stat.st_size)
            with self.assertRaises(InvalidSourceIndex):
                source_status(db,meta,"echo")

    def test_injection_is_exact_match(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw=root/"echo.csv";raw.write_text("REGISTRY_ID,FAC_NAME\nA001,Factory\n")
            out=root/"index";ingest("echo",raw,out)
            result=lookup(out/"echo.sqlite",out/"echo.manifest.json","echo","A001' OR 1=1 --")
            self.assertEqual(result["observations_available"],0)
            with self.assertRaises(ValueError):lookup(out/"echo.sqlite",out/"echo.manifest.json","echo","A001",limit=99999)

if __name__=="__main__":unittest.main()
