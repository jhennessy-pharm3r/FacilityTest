import tempfile,unittest
from pathlib import Path
from scripts.lane_b_epa.ingest import ingest
from scripts.lane_b_epa.read_index import InvalidSourceIndex
from scripts.lane_b_epa.tri_history import lookup_history

class TRIHistoryIndexTests(unittest.TestCase):
    def test_two_source_years_remain_separate_and_queryable(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for y,chemical in [(2023,"CHEMICAL A"),(2024,"CHEMICAL B")]:
                p=root/(str(y)+".csv")
                p.write_text("1. YEAR,2. TRIFD,37. CHEMICAL,50. UNIT OF MEASURE,107. TOTAL RELEASES\n"+
                             f"{y},TEST00001,{chemical},Pounds,{y-2020}\n")
                ingest("tri",p,root/("tri_"+str(y)),year=y,
                      source_url=f"https://data.epa.gov/efservice/downloads/tri/mv_tri_basic_download/{y}_US/csv")
            result=lookup_history(root,"TEST00001",[2024,2023])
            self.assertEqual(result["total_matched_reporting_forms"],2)
            self.assertEqual([x["year"] for x in result["years"]],[2023,2024])
            self.assertNotEqual(result["years"][0]["source_archive_sha256"],result["years"][1]["source_archive_sha256"])
            self.assertEqual(result["years"][1]["rows"][0]["source_reported_findings"]["reported_chemical"],"CHEMICAL B")
            self.assertEqual(result["physical_site_linkage"],"NOT_REVIEWED")
            self.assertEqual(result["deployment_state"],"NOT_DEPLOYED")
            with self.assertRaises(InvalidSourceIndex):lookup_history(root,"TEST00001",[2023,2022])
            with self.assertRaises(ValueError):lookup_history(root,"TEST00001",[2023,2023])
            with self.assertRaises(ValueError):lookup_history(root,"TEST00001",[2025])
if __name__=="__main__":unittest.main()
