import tempfile,unittest,sqlite3,json
from pathlib import Path
from zipfile import ZipFile
from scripts.lane_b_epa.ingest import ingest,coordinate
class LaneBTests(unittest.TestCase):
    def test_coord(self):
        self.assertIsNone(coordinate("95",-90,90))
        self.assertIsNone(coordinate("nan",-90,90))
        self.assertEqual(coordinate("-70",-180,180),-70)
    def test_tri_reconciliation(self):
        with tempfile.TemporaryDirectory() as d:
            x=Path(d);p=x/"tri.csv"
            p.write_text("TRIFD,LATITUDE,LONGITUDE\nONE,40,-70\nONE,,\n,40,-70\n")
            m=ingest("tri",p,x/"out",year=2024)
            self.assertEqual((m["scanned_rows"],m["indexed_rows"],m["rejected_rows"]),(3,2,1))
            self.assertEqual(m["duplicate_member_ids"],1)
            self.assertEqual(m["valid_coordinate_pairs"],1)
    def test_official_numbered_tri_basic_header(self):
        with tempfile.TemporaryDirectory() as d:
            x=Path(d);p=x/"official_tri.csv"
            p.write_text("1. YEAR,2. TRIFD,12. LATITUDE,13. LONGITUDE,37. CHEMICAL,50. UNIT OF MEASURE\n2024,12000ABCDE,41,-72,CHLORINE,Pounds\n")
            m=ingest("tri",p,x/"out",year=2024)
            self.assertEqual(m["indexed_rows"],1)
            self.assertEqual(m["valid_coordinate_pairs"],1)
            self.assertEqual(m["archive_members"]["official_tri.csv"]["identity_column"],"2_TRIFD")
    def test_rcra_archive_skip(self):
        with tempfile.TemporaryDirectory() as d:
            x=Path(d);p=x/"rcra.zip"
            with ZipFile(p,"w") as z:
                z.writestr("handlers.csv","HANDLER_ID,NAME\nR001,Test\n")
                z.writestr("lookups.csv","CODE,VALUE\nX,Y\n")
            m=ingest("rcra",p,x/"out")
            self.assertEqual(m["indexed_rows"],1)
            self.assertEqual(m["archive_members"]["lookups.csv"]["state"],"skipped_no_identity_column")
    def test_official_rcra_national_columns(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/"rcra.zip"
            with ZipFile(source,"w") as z:
                z.writestr("RCRA_FACILITIES.csv","ID_NUMBER,FACILITY_NAME,LATITUDE83,LONGITUDE83\nNYD000000001,Industrial Site,42,-75\n")
                z.writestr("RCRA_VIOLATIONS.csv","ID_NUMBER,VIOLATION_TYPE\nNYD000000001,A\n")
            m=ingest("rcra",source,root/"out")
            self.assertEqual(m["indexed_rows"],2)
            self.assertEqual(m["valid_coordinate_pairs"],1)
            self.assertEqual(m["archive_members"]["RCRA_FACILITIES.csv"]["identity_column"],"ID_NUMBER")
    def test_echo_actual_fac_lat_long_and_explicit_reject_reasons(self):
        with tempfile.TemporaryDirectory() as d:
            x=Path(d);p=x/"export.csv"
            p.write_text("REGISTRY_ID,FAC_LAT,FAC_LONG,FAC_NAME\n1100,43,-72,Factory\n,43,-72,Missing ID\n")
            m=ingest("echo",p,x/"out")
            self.assertEqual(m["indexed_rows"],1)
            self.assertEqual(m["valid_coordinate_pairs"],1)
            self.assertEqual(m["reject_reason_counts"]["missing_native_id"],1)
    def test_rcrainfo_composite_source_identity_and_quarantine(self):
        with tempfile.TemporaryDirectory() as d:
            x=Path(d);p=x/"RCRA_FACILITIES.csv"
            p.write_text("ID_NUMBER,ACTIVITY_LOCATION,FACILITY_NAME,LATITUDE83,LONGITUDE83\n"
                         "TXD123,TX,Site 1,31,-97\n"
                         "TXD123,OK,Site 2,32,-96\n"
                         ",TX,Not uniquely identified,30,-95\n")
            m=ingest("rcra",p,x/"out")
            self.assertEqual((m["scanned_rows"],m["indexed_rows"],m["rejected_rows"]),(3,2,1))
            con=sqlite3.connect(x/"out"/"rcra.sqlite")
            self.assertEqual([r[0] for r in con.execute("SELECT activity_location FROM observation ORDER BY row_number")],["TX","OK"])
            kept=con.execute("SELECT reason,payload_json,row_sha256 FROM rejected").fetchone()
            self.assertEqual(kept[0],"missing_native_id")
            self.assertEqual(json.loads(kept[1])["FACILITY_NAME"],"Not uniquely identified")
            self.assertEqual(len(kept[2]),64)
            con.close()
    def test_zero_accepted_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            x=Path(d);p=x/"invalid.csv";p.write_text("UNKNOWN_ID,NAME\nA,Example\n")
            with self.assertRaises(ValueError):ingest("rcra",p,x/"out")
            self.assertFalse((x/"out"/"rcra.sqlite").exists())
    def test_no_false_facility_merge(self):
        with tempfile.TemporaryDirectory() as d:
            x=Path(d);p=x/"echo.csv";p.write_text("REGISTRY_ID,NAME\nA,Same\nB,Same\n")
            self.assertEqual(ingest("echo",p,x/"out")["indexed_rows"],2)
if __name__=="__main__":unittest.main()
