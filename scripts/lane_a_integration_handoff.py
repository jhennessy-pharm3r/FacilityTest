"""Produce a Lane-A-owned source health and index integration handoff.

This file is DATA for Lane E coordinator; do not write or mutate shared source
registry, public UI or tenant APIs. All source evidence is separate from an
insured physical-site match, policy, actual loss or live deployment.
"""
import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone

SOURCE_DEFINITIONS = (
    ("fema_nfhl", "paged_windows/manifest.json", "fema-window-index.sqlite"),
    ("usfs_whp2023_continuous", "whp_regions/manifest.json", "whp-regional-source-only.sqlite"),
    ("usfs_whp2023_classified", "whp_classified/manifest.json", "whp-classified-source-only.sqlite"),
    ("usfs_whp2023_admin_summaries", "whp_official_index/manifest.json", "whp2023-source-geographies.sqlite"),
)


def generate(root):
    root = pathlib.Path(root)
    contract = {
        "handoff_schema_version": "lane_a_source_evidence_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "owner": "Lane A: FEMA NFHL + USDA wildfire hazard",
        "source_data_may_include_non_site_records": True,
        "all_facility_types_eligible": True,
        "physical_sites_automatically_matched": 0,
        "insured_sites_independently_reviewed": 0,
        "durable_production_rows": 0,
        "deployed_browser_rows": 0,
        "production_source_health_must_not_be_changed_by_lane_a": True,
        "national_source_completeness_verified": False,
        "source_only_ci_indexes_are_ephemeral": True,
        "handoff_requires_coordinator_merge_private_backend_auth": True,
        "source_sets": {},
    }
    for name, relative, index_filename in SOURCE_DEFINITIONS:
        path = root / relative
        status = {
            "source_id": name, "manifest_path_in_artifact": relative,
            "ephemeral_source_only_sqlite": str(pathlib.PurePosixPath(relative).parent / index_filename),
            "durable_production_indexed": 0, "deployed": 0,
            "approved_site_links": 0, "has_current_nationwide_raster_or_polygon_census": False,
        }
        if not path.exists():
            status.update({"state": "NOT_PRESENT_IN_THIS_RUN",
                           "real_downloaded_or_normalized": None,
                           "source_only_indexed": None,
                           "coverage_or_access_errors": ["Manifest unavailable; do not claim zero publisher records"]})
        else:
            m = json.loads(path.read_text(encoding="utf-8"))
            if name == "fema_nfhl":
                indexed = m.get("source_feature_count")
                completeness = bool(m.get("all_requested_windows_complete"))
                status.update({
                    "state": "STAGED_GEO_WINDOWS" if completeness else "PARTIAL_SOURCE_ACCESS",
                    "real_downloaded_or_normalized": indexed,
                    "source_only_indexed": indexed,
                    "complete_source_windows": m.get("successful_windows"),
                    "requested_source_windows": m.get("requested_windows"),
                    "original_source_native_dfirm_count": m.get("distinct_dfirm_ids"),
                    "current_map_effective_dates_per_dfirm_verified": False,
                    "geometry_generalization_count": m.get("geometry_generalized_observations"),
                    "geometry_generalization_not_precise_property_boundary": True,
                    "source_zone_distribution": m.get("zone_distribution"),
                    "window_states": {k: x.get("status") for k, x in m.get("windows", {}).items()},
                    "source_coverage_level": "ONLY_SIX_SPECIFIED_SMALL_TEST_ENVELOPES",
                    "coverage_or_access_errors": [
                        {"window": k, "error": x.get("error")}
                        for k, x in m.get("windows", {}).items() if x.get("error")
                    ],
                })
            elif name.startswith("usfs_whp2023_") and name != "usfs_whp2023_admin_summaries":
                continuous = name.endswith("continuous")
                verified = bool(m.get("complete_geographic_probe_set") if continuous else
                                m.get("sample_complete"))
                status.update({
                    "state": "VERIFIED_BOUNDED_RASTER_SAMPLE" if verified else "PARTIAL_RASTER_SAMPLE",
                    "real_downloaded_or_normalized": m.get("downloaded_replies") if continuous else m.get("received"),
                    "source_only_indexed": m.get("indexed_point_observations") if continuous else m.get("indexed_observations"),
                    "raw_numeric_observations": m.get("accepted_numeric_pixels") if continuous else
                                                m.get("burnable_classes"),
                    "no_data_or_mask_count": m.get("no_data_pixels") if continuous else
                                             m.get("special_mask_classes", 0) + m.get("nodata", 0),
                    "rejected": m.get("rejected_pixels") if continuous else m.get("rejected"),
                    "source_network_errors": m.get("source_failures"),
                    "publisher_product_vintage": "2023 revised 2024-07-17",
                    "landscape_conditions_as_of": "2020",
                    "source_coverage_level": "70_GEO_QA_PIXELS_ACROSS_14_REGIONS_NOT_NATIONAL_GRID",
                    "source_pixel_is_not_fire_occurrence_or_insured_loss": True,
                })
            else:
                verified = bool(m.get("reconciled") and
                                m.get("source_records_read") == m.get("normalized_records") + m.get("rejected_records") and
                                m.get("source_only_indexed_records") == m.get("normalized_records"))
                status.update({
                    "state": "VERIFIED_NATIONAL_ADMIN_AGGREGATES" if verified else "INVALID_NATIONAL_ADMIN_AGGREGATES",
                    "real_downloaded_or_normalized": m.get("normalized_records"),
                    "source_only_indexed": m.get("source_only_indexed_records"),
                    "source_rows_read": m.get("source_records_read"),
                    "source_rejections": m.get("rejected_records"),
                    "source_key_duplicates": m.get("duplicate_source_keys"),
                    "source_null_coverage": m.get("source_coverage_missing"),
                    "source_geography_counts": m.get("source_unique_geography_counts"),
                    "management_publisher_total_rows": m.get("management_grand_total_rows"),
                    "official_source_zip_sha256": m.get("source_zip_sha256"),
                    "normalized_gzip_sha256": m.get("normalized_gzip_sha256"),
                    "publisher_product_vintage": "2023 revised 2024-07-17",
                    "source_coverage_level": "PUBLISHER_NATIONAL_ADMIN_SUMMARY_NOT_270M_RASTER",
                    "source_coverage_or_access_errors": [
                        {"record": i} for i in m.get("rejected_examples", [])[:10]
                    ],
                })
        contract["source_sets"][name] = status
    return contract


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--root", default="data/lane_a")
    p.add_argument("--output", default="data/lane_a/lane_a_integration_handoff.json")
    args = p.parse_args(argv)
    manifest = generate(args.root)
    dest = pathlib.Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("LANE_A_COORDINATOR_HANDOFF=" + json.dumps({
        "sources": {k: {"state": v["state"],
                        "downloaded_normalized": v["real_downloaded_or_normalized"],
                        "source_only_indexed": v["source_only_indexed"],
                        "durable_indexed": 0, "deployed": 0}
                    for k, v in manifest["source_sets"].items()},
        "site_matches": 0, "source_health_deployed": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
