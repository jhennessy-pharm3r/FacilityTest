import tempfile,unittest
from pathlib import Path
from zipfile import ZipFile
from scripts.lane_b_epa.crosswalk_audit import candidate_audit

class EPAReviewOnlyCandidateAuditTests(unittest.TestCase):
    def test_native_frs_key_only_and_quarantine(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            echo=root/"echo.zip"
            with ZipFile(echo,"w") as z:
                z.writestr("ECHO_EXPORTER.csv",
                    "REGISTRY_ID,FAC_NAME\nR001,Same Name\nR002,Shared\n,Missing\nR002,Repeats\n")
            tri=root/"tri.csv"
            tri.write_text("1. YEAR,2. TRIFD,3. FRS ID,4. FACILITY NAME\n"
                           "2024,TRI1,R001,Other Name\n"
                           "2024,TRI1,R001,Other Name\n"
                           "2024,TRI2,R999,Shared\n"
                           "2024,TRI3,,Same Name\n")
            a=candidate_audit(echo,tri,2024)
            self.assertEqual(a["echo_raw_rows"],4)
            self.assertEqual(a["echo_native_registry_ids"],2)
            self.assertEqual(a["echo_rows_missing_registry_id"],1)
            self.assertEqual(a["echo_duplicate_native_registry_ids"],1)
            self.assertEqual(a["tri_raw_reports"],4)
            self.assertEqual(a["tri_distinct_native_trifd"],3)
            self.assertEqual(a["tri_reports_exact_frs_key_in_echo"],2)
            self.assertEqual(a["tri_reports_frs_key_absent_in_echo"],1)
            self.assertEqual(a["tri_missing_reported_frs_id_rows"],1)
            self.assertEqual(a["distinct_tri_reported_frs_ids_in_echo"],1)
            self.assertEqual(a["physical_property_matches_verified"],0)
            self.assertEqual(a["production_deployed_records"],0)
            with self.assertRaises(ValueError):
                candidate_audit(echo,tri,2023)
    def test_no_auto_matches_on_equal_names(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);echo=root/"echo.zip";tri=root/"tri.csv"
            with ZipFile(echo,"w") as z:
                z.writestr("ECHO_EXPORTER.csv","REGISTRY_ID,FAC_NAME\nECHO1,Acme Plant\n")
            tri.write_text("1. YEAR,2. TRIFD,3. FRS ID,4. FACILITY NAME\n2024,TRI1,FRS99,Acme Plant\n")
            a=candidate_audit(echo,tri,2024)
            self.assertEqual(a["tri_reports_exact_frs_key_in_echo"],0)
            self.assertEqual(a["tri_reports_frs_key_absent_in_echo"],1)
            self.assertEqual(a["physical_property_matches_verified"],0)

if __name__=="__main__":unittest.main()
