import tempfile,unittest
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
    def test_rcra_archive_skip(self):
        with tempfile.TemporaryDirectory() as d:
            x=Path(d);p=x/"rcra.zip"
            with ZipFile(p,"w") as z:
                z.writestr("handlers.csv","HANDLER_ID,NAME\nR001,Test\n")
                z.writestr("lookups.csv","CODE,VALUE\nX,Y\n")
            m=ingest("rcra",p,x/"out")
            self.assertEqual(m["indexed_rows"],1)
            self.assertEqual(m["archive_members"]["lookups.csv"]["state"],"skipped_no_identity_column")
    def test_no_false_facility_merge(self):
        with tempfile.TemporaryDirectory() as d:
            x=Path(d);p=x/"echo.csv";p.write_text("REGISTRY_ID,NAME\nA,Same\nB,Same\n")
            self.assertEqual(ingest("echo",p,x/"out")["indexed_rows"],2)
if __name__=="__main__":unittest.main()
