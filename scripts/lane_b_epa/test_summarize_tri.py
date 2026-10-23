import json,tempfile,unittest
from pathlib import Path
from scripts.lane_b_epa.summarize_tri import summarize
class AnnualTRIReconciliationTests(unittest.TestCase):
    def test_all_years_required_and_no_site_count_sum(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for year,records in ((2018,5),(2019,7)):
                folder=root/f"lane-b-tri-historical-{year}-qa"
                folder.mkdir()
                source_hash="1"*64
                index_hash="2"*64
                m={"year":year,"source":"tri","schema_version":2,"state":"INDEXED",
                   "deployment_state":"NOT_DEPLOYED","scanned_rows":records,
                   "accepted_rows":records,"indexed_rows":records,"rejected_rows":0,
                   "valid_coordinate_pairs":records,"archive_sha256":source_hash,
                   "index_sha256":index_hash,
                   "source_url":f"https://data.epa.gov/efservice/downloads/tri/mv_tri_basic_download/{year}_US/csv"}
                q={"reporting_year":year,"scanned_downloaded_rows":records,
                   "accepted_normalized":records,"source_indexed":records,"rejected":0,
                   "distinct_native_TRI_facility_ids":2,"coordinate_pairs":records,
                   "source_reported_units":{"Pounds":records},
                   "source_sha256":source_hash,"index_sha256":index_hash,"deployed_records":0}
                (folder/"tri.manifest.json").write_text(json.dumps(m))
                (folder/"year_qa.json").write_text(json.dumps(q))
            result=summarize(root,[2018,2019])
            self.assertEqual(result["source_downloaded_rows"],12)
            self.assertEqual(result["source_indexed_staging_rows"],12)
            self.assertIsNone(result["cross_year_unique_facility_count"])
            self.assertEqual(result["deployed_private_service_rows"],0)
            with self.assertRaises(ValueError):summarize(root,[2017,2018,2019])
            with self.assertRaises(ValueError):summarize(root,[2018,2018])
            f=root/"lane-b-tri-historical-2018-qa"/"tri.manifest.json"
            corrupted=json.loads(f.read_text());corrupted["accepted_rows"]=4
            f.write_text(json.dumps(corrupted))
            with self.assertRaises(AssertionError):summarize(root,[2018,2019])
if __name__=="__main__":unittest.main()
