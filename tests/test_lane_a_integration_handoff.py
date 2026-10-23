import json
import tempfile
import unittest
from pathlib import Path

from scripts.lane_a_integration_handoff import generate


class LaneACoordinatorHandoffTests(unittest.TestCase):
    def test_missing_sources_are_unknown_not_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            doc = generate(temp)
            self.assertFalse(doc["national_source_completeness_verified"])
            self.assertEqual(doc["deployed_browser_rows"], 0)
            self.assertEqual(doc["physical_sites_automatically_matched"], 0)
            self.assertTrue(doc["all_facility_types_eligible"])
            self.assertTrue(all(x["state"] == "NOT_PRESENT_IN_THIS_RUN"
                                and x["source_only_indexed"] is None
                                for x in doc["source_sets"].values()))

    def test_national_count_and_older_state_sample_not_merged_into_national_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            p = root / "fema_distribution"
            p.mkdir()
            (p / "manifest.json").write_text(json.dumps({
                "rest_count_state": "DOWNLOADED_RESPONSE_ONLY",
                "reported_current_service_feature_count": 5813220,
                "checked_utc": "2026-10-23T16:30:02+00:00",
                "wfs_state": "PROBED",
                "wfs_error": "connection reset",
                "rest_count_receipt": {"sha256": "a" * 64},
            }))
            p = root / "massgis_2025"
            p.mkdir()
            (p / "manifest.json").write_text(json.dumps({
                "source_sample_validated": True,
                "sample_accepted": 10, "sample_raw": 10, "sample_rejected": 0,
                "indexed_observations": 10, "distinct_fema_native_keys": 10,
                "source_data_vintage": "FEMA as of 2025-07-18",
                "metadata": {"metadata_valid": True}, "samples": [],
            }))
            m = generate(root)
            total = m["source_sets"]["fema_nfhl_count_only"]
            self.assertEqual(total["state"], "PUBLISHER_COUNT_METADATA_ONLY")
            self.assertEqual(total["publisher_reported_national_feature_count_not_downloaded"], 5813220)
            self.assertEqual(total["real_downloaded_or_normalized"], 0)
            self.assertEqual(total["source_only_indexed"], 0)
            self.assertEqual(total["deployed"], 0)
            state = m["source_sets"]["massgis_ma_nfhl_2025_state_archive"]
            self.assertEqual(state["state"], "VERIFIED_DATED_STATE_SAMPLE")
            self.assertEqual(state["source_only_indexed"], 10)
            self.assertTrue(state["not_a_national_nfhl_replacement"])
            self.assertEqual(state["deployed"], 0)

    def test_realistic_source_grain_counts_separate_from_deployment(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            p = root / "whp_official_index"
            p.mkdir()
            (p / "manifest.json").write_text(json.dumps({
                "source_records_read": 35304, "normalized_records": 35304,
                "source_only_indexed_records": 35304, "rejected_records": 0,
                "reconciled": True, "source_coverage_missing": 60,
                "source_unique_geography_counts": {
                    "county": 3143, "state": 51, "zip": 32094,
                    "management_jurisdiction": 16,
                }, "management_grand_total_rows": 1, "duplicate_source_keys": 0,
                "source_zip_sha256": "a" * 64, "normalized_gzip_sha256": "b" * 64,
            }))
            p = root / "paged_windows"
            p.mkdir()
            (p / "manifest.json").write_text(json.dumps({
                "source_feature_count": 34, "all_requested_windows_complete": True,
                "successful_windows": 6, "requested_windows": 6,
                "distinct_dfirm_ids": 6, "geometry_generalized_observations": 3,
                "zone_distribution": {"AE": 10, "VE": 1, "X": 23},
                "windows": {"new_orleans": {"status": "COMPLETE_WITHIN_WINDOW"}},
            }))
            doc = generate(root)
            self.assertEqual(doc["source_sets"]["fema_nfhl"]["source_only_indexed"], 34)
            self.assertEqual(doc["source_sets"]["fema_nfhl"]["geometry_generalization_count"], 3)
            self.assertFalse(doc["source_sets"]["fema_nfhl"]["has_current_nationwide_raster_or_polygon_census"])
            usda = doc["source_sets"]["usfs_whp2023_admin_summaries"]
            self.assertEqual(usda["source_only_indexed"], 35304)
            self.assertEqual(usda["source_null_coverage"], 60)
            self.assertEqual(usda["source_key_duplicates"], 0)
            self.assertEqual(usda["durable_production_indexed"], 0)
            self.assertEqual(usda["deployed"], 0)
            self.assertEqual(usda["approved_site_links"], 0)


if __name__ == "__main__":
    unittest.main()
