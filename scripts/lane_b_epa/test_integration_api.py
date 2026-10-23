import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from scripts.lane_b_epa.ingest import ingest
from scripts.lane_b_epa.rmp_public import import_public
from scripts.lane_b_epa.integration_api import status,query_exact,reporting_years

class CoordinatorAPIContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        echo_raw=root/"echo.csv"
        echo_raw.write_text("REGISTRY_ID,FAC_NAME,FAC_LAT,FAC_LONG\nR100,Warehouse,40,-78\n")
        echo=root/"echo"
        ingest("echo",echo_raw,echo)
        rcra_raw=root/"rcra.zip"
        with ZipFile(rcra_raw,"w") as z:
            z.writestr("RCRA_FACILITIES.csv",
                "ID_NUMBER,ACTIVITY_LOCATION,FACILITY_NAME,LATITUDE83,LONGITUDE83\nID123,PA,Plant,40,-79\n")
        rcra=root/"rcra"
        ingest("rcra",rcra_raw,rcra)
        tri_raw=root/"tri.csv"
        tri_raw.write_text("1. YEAR,2. TRIFD,50. UNIT OF MEASURE\n2024,TRI123,Pounds\n")
        tri_dir=root/"tri"/"tri_2024"
        ingest("tri",tri_raw,tri_dir,year=2024)
        def fake(params):
            if "returnCountOnly" in params:return {"count":1}
            if "returnIdsOnly" in params:return {"objectIds":[1]}
            return {"features":[{"attributes":{"OBJECTID":1,"REGISTRY_ID":"R100",
                "PGM_SYS_ID":"RMP100","LATITUDE83":40.5,"LONGITUDE83":-79.2}}]}
        rmp=root/"rmp"
        import_public(rmp,fetch=fake)
        self.env={
            "FACILITY_RISK_LANE_B_ECHO_DIRECTORY":str(echo),
            "FACILITY_RISK_LANE_B_RCRA_DIRECTORY":str(rcra),
            "FACILITY_RISK_LANE_B_TRI_ROOT":str(root/"tri"),
            "FACILITY_RISK_LANE_B_TRI_YEARS":"2024",
            "FACILITY_RISK_LANE_B_RMP_DIRECTORY":str(rmp),
        }
        self.root=root
    def test_health_four_native_sources_and_no_deployment_claims(self):
        a=status(self.env)
        for source in ("echo","rcra","tri","rmp_public"):
            self.assertEqual(a["sources"][source]["state"],"mounted_source_only")
            self.assertEqual(a["sources"][source]["indexed_source_rows"],1)
            self.assertIsNone(a["sources"][source]["production_deployed_records"])
        self.assertEqual(a["physical_site_linkage"],"REVIEW_ONLY")
        self.assertEqual(a["production_deployment"],"UNASSESSED_BY_ADAPTER")
    def test_exact_native_identity_and_no_raw_fields_by_default(self):
        echo=query_exact("echo","R100",environ=self.env)
        self.assertEqual(echo["observations_available"],1)
        self.assertNotIn("raw_attributes",echo["rows"][0])
        full=query_exact("echo","R100",include_raw=True,environ=self.env)
        self.assertEqual(full["rows"][0]["raw_attributes"]["FAC_NAME"],"Warehouse")
        rcra=query_exact("rcra","ID123",activity_location="PA",environ=self.env)
        self.assertEqual(rcra["rows"][0]["activity_location"],"PA")
        self.assertEqual(rcra["physical_site_linkage"],"NOT_REVIEWED")
        tri=query_exact("tri","TRI123",year=2024,environ=self.env)
        self.assertEqual(tri["reporting_year"],2024)
        rmp=query_exact("rmp_public","RMP100",environ=self.env)
        self.assertEqual(rmp["observations_available"],1)
        self.assertNotIn("reported_attributes",rmp["records"][0])
        self.assertEqual(rmp["site_and_insured_loss_status"],"UNASSESSED")
    def test_fail_closed_unconfigured_year_and_unsupported_filters(self):
        self.assertEqual(status({})["sources"]["rcra"]["state"],"not_configured")
        self.assertEqual(reporting_years("2022-2024,2019"),[2019,2022,2023,2024])
        with self.assertRaises(ValueError):reporting_years("2024,2024")
        with self.assertRaises(ValueError):query_exact("rcra","ID123",environ=self.env)
        with self.assertRaises(ValueError):query_exact("tri","TRI123",year=2023,environ=self.env)
        with self.assertRaises(ValueError):query_exact("rmp_public","RMP100",offset=1,environ=self.env)
        with self.assertRaises(ValueError):query_exact("echo","R100",limit=200,environ=self.env)
        wrong=dict(self.env)
        wrong["FACILITY_RISK_LANE_B_TRI_YEARS"]="2020-2024"
        self.assertEqual(status(wrong)["sources"]["tri"]["state"],"unavailable")
        self.assertEqual(status(wrong)["sources"]["echo"]["state"],"mounted_source_only")

if __name__=="__main__":unittest.main()
