import tempfile
import unittest
from pathlib import Path
from scripts.lane_b_epa.findings import (
    source_decimal,tri_release_measure,tri_reported_measures,
    rcra_enforcement_measures,echo_summary_measures,
)
from scripts.lane_b_epa.ingest import ingest
from scripts.lane_b_epa.read_index import lookup, _date

class EnvironmentalReportedMeasureTests(unittest.TestCase):
    def test_safe_exact_tri_unit_conversion(self):
        pounds=tri_release_measure({"50_UNIT_OF_MEASURE":"Pounds","107_TOTAL_RELEASES":"2"},"107_TOTAL_RELEASES")
        self.assertEqual(pounds["kilograms"],"0.90718474")
        self.assertEqual(pounds["state"],"reported_numeric")
        grams=tri_release_measure({"50_UNIT_OF_MEASURE":"Grams","107_TOTAL_RELEASES":"0.3"},"107_TOTAL_RELEASES")
        self.assertEqual(grams["kilograms"],"0.0003")
        unknown=tri_release_measure({"50_UNIT_OF_MEASURE":"Unknown","107_TOTAL_RELEASES":"5"},"107_TOTAL_RELEASES")
        self.assertEqual(unknown["state"],"numeric_unrecognized_unit")
        self.assertIsNone(unknown["kilograms"])
    def test_negative_missing_and_unsafe_numeric_source_values(self):
        self.assertEqual(source_decimal("-1")["state"],"negative_value_requires_review")
        self.assertEqual(source_decimal("NA")["state"],"not_reported")
        self.assertEqual(source_decimal("NaN")["state"],"invalid_numeric")
        self.assertEqual(source_decimal("1e99999")["state"],"invalid_numeric")
        self.assertEqual(source_decimal("0")["state"],"reported_zero")
        self.assertEqual(source_decimal("1,234.5")["value"],"1234.5")
    def test_rcra_amount_categories_not_falsely_summed(self):
        r=rcra_enforcement_measures({"PMP_AMOUNT":"200","FMP_AMOUNT":"400","FSC_AMOUNT":"","SCR_AMOUNT":"0"})
        self.assertEqual(r["PMP_AMOUNT"]["value"],"200")
        self.assertEqual(r["SCR_AMOUNT"]["state"],"reported_zero")
        self.assertEqual(r["FSC_AMOUNT"]["state"],"not_reported")
        self.assertNotIn("total_penalty",r)
    def test_echo_compliance_summaries_are_not_event_findings(self):
        m=echo_summary_measures({"FAC_TOTAL_PENALTIES":"1,500","FAC_INSPECTION_COUNT":"2",
                                 "FAC_COMPLIANCE_STATUS":"Significant Violation","FAC_SNC_FLG":"N"})
        self.assertEqual(m["reported_total_penalties"]["value"],"1500")
        self.assertEqual(m["reported_compliance_status"],"Significant Violation")
        self.assertEqual(m["reported_snc_flag"],"N")
        self.assertTrue(m["reported_total_penalties"]["is_aggregate_facility_summary"])
    def test_unrealistic_regulator_year_not_silently_assigned(self):
        self.assertEqual(_date("10/01/1016")[1],"out_of_plausible_range")
        self.assertEqual(_date("1900-01-01")[1],"legacy_date_requires_manual_review")
        self.assertEqual(_date("1973-01-01")[0],"1973-01-01")
        self.assertEqual(_date("2024")[0],"2024")
    def test_real_source_shape_query_contains_typed_measure(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw=root/"tri.csv"
            raw.write_text(
                "1. YEAR,2. TRIFD,36. DOC CTRL NUM,37. CHEMICAL,50. UNIT OF MEASURE,107. TOTAL RELEASES\n"
                "2024,TRI0001,DOC0001,TEST CHEMICAL,Pounds,2\n")
            ingested=root/"out"
            ingest("tri",raw,ingested,year=2024)
            q=lookup(ingested/"tri.sqlite",ingested/"tri.manifest.json","tri","TRI0001")
            self.assertEqual(q["observations_available"],1)
            m=q["rows"][0]["source_reported_findings"]["normalized_reported_measures"]
            self.assertEqual(m["total_release"]["kilograms"],"0.90718474")
            self.assertEqual(m["total_release"]["reported_unit"],"Pounds")
            self.assertEqual(q["physical_site_linkage"],"NOT_REVIEWED")
if __name__=="__main__":
    unittest.main()
