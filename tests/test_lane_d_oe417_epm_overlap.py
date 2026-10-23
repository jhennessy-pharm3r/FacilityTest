"""DOE OE417 annual vs EIA EPM: candidate overlap NEVER an automatic identity."""
import json
from pathlib import Path
import tempfile
import unittest
from facilityrisk.lane_d.audit_oe417_epm_overlap import norm_area,epm_start_date,assess


def oe(index,dt="2023-01-12",area="Washington: King County;",duplicate=False):
    return {"source_row_key":f"annual-{index}",
            "event_date_source":dt,"source_area_text":area,
            "is_exact_duplicate_publisher_record":duplicate}


def epm(index,dt="01/12/2023 12:45 AM",area="Washington: King County;"):
    return {"derived_source_row_key":f"epm-{index}",
            "reported_start":dt,"reported_area":area}


class OverlapTests(unittest.TestCase):
    def test_exact_calendar_day_and_source_area_only_for_review(self):
        a=assess([oe(1),oe(2,"2023-02-15","New York: Queens")],
                 [epm(1),epm(2,"02/15/2023 1:00 AM","New York: Queens")])
        self.assertEqual(a["exact_normalized_date_area_candidate_groups"],2)
        self.assertEqual(a["one_to_one_unverified_candidate_groups"],2)
        self.assertEqual(a["ambiguous_multiplicity_candidate_groups"],0)
        self.assertEqual(a["all_candidate_row_pairs_including_ambiguous_cartesian"],2)
        self.assertEqual(a["distinct_oe417_rows_in_candidate_groups"],2)
        self.assertEqual(a["independently_verified_same_incident_links"],0)
        self.assertEqual(a["verified_insured_site_outages"],0)
        self.assertEqual(a["deployed"],0)
        self.assertTrue(all(not g["independently_verified_same_incident"] for g in a["candidate_groups"]))
        self.assertEqual(norm_area("  NY:  Queens / County;"),"NY QUEENS COUNTY")

    def test_same_day_different_area_is_not_accepted(self):
        a=assess([oe(1)],[epm(1,area="Washington: Pierce County;")])
        self.assertEqual(a["exact_normalized_date_area_candidate_groups"],0)
        self.assertEqual(a["independently_verified_same_incident_links"],0)

    def test_literal_same_table_duplicates_and_undated_unknown_excluded(self):
        a=assess([oe(1),oe(2,duplicate=True),oe(3,dt=None),
                  oe(4,area=None)],[epm(1)])
        self.assertEqual(a["exact_normalized_date_area_candidate_groups"],1)
        self.assertEqual(a["oe417_source_rows_skipped_from_candidate_search"],{
            "literal_same_table_duplicate":1,"date_unknown":1,"area_unknown":1})
        self.assertEqual(a["distinct_oe417_rows_in_candidate_groups"],1)

    def test_multiple_same_date_area_remain_ambiguous_and_all_originals_preserved(self):
        a=assess([oe(1),oe(2)],[epm(1),epm(2)])
        self.assertEqual(a["exact_normalized_date_area_candidate_groups"],1)
        self.assertEqual(a["one_to_one_unverified_candidate_groups"],0)
        self.assertEqual(a["ambiguous_multiplicity_candidate_groups"],1)
        self.assertEqual(a["all_candidate_row_pairs_including_ambiguous_cartesian"],4)
        self.assertEqual(a["distinct_oe417_rows_in_candidate_groups"],2)
        self.assertEqual(a["distinct_epm_rows_in_candidate_groups"],2)
        self.assertEqual(a["candidate_groups"][0]["candidate_status"],"AMBIGUOUS_MULTIPLE_CANDIDATES")

    def test_date_parse_safely_does_not_impute_unknown(self):
        self.assertEqual(epm_start_date(epm(1,"01/12/2023 1:00 AM")),"2023-01-12")
        for dt in ("",None,"2023-01-12", "13/10/2023 1:00 PM",
                   "02/30/2023 1:00 PM",". ."):
            self.assertIsNone(epm_start_date(epm(1,dt)))
        self.assertEqual(norm_area(None),"")
        self.assertEqual(norm_area(" "),"")
        self.assertEqual(norm_area("North Carolina: Wake County;"),"NORTH CAROLINA WAKE COUNTY")


if __name__=="__main__":
    unittest.main()
