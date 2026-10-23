"""Read-only integration smoke against activated Lane A official source indexes.

The result proves storage and query contract, NOT authenticated application
hosting, source national completeness, insured-property links or deployment.
"""
import argparse
import json
import pathlib
import sqlite3
import sys

from facilityrisk.lane_a_installed import (
    installed_release, index_file, query_publisher_id, query_raster_probe,
)


def inspect(destination):
    root, pointer = installed_release(destination)
    sources = pointer["verified_source_only_rows"]
    result = {
        "release_id": pointer["release_id"],
        "read_only_indexes_queryable": False,
        "source_rows": {},
        "query_examples": {},
        "insured_site_matches_verified": 0,
        "browser_app_deployed": False,
        "national_fema_or_wildfire_raster_complete": False,
    }
    if "usda_summary" in sources:
        zip_row = query_publisher_id(destination, "usda_summary",
                                     geography_type="zip", original_id="00029")
        no_area = query_publisher_id(destination, "usda_summary",
                                     geography_type="zip", original_id="10168")
        county = query_publisher_id(destination, "usda_summary",
                                    geography_type="county", original_id="06017")
        management = query_publisher_id(destination, "usda_summary",
                                        geography_type="management_jurisdiction",
                                        original_id="Grand Total")
        if (zip_row.get("native_geographic_id") != "00029" or
                no_area.get("total_acres") is not None or
                no_area.get("source_coverage") != "UNKNOWN_NO_AREA_VALUES" or
                county.get("native_geographic_id") != "06017" or
                not management.get("is_publisher_grand_total") or
                zip_row.get("physical_site_verified") is not False):
            raise ValueError("Real USDA source native-ID query or unknown acreage probe failed")
        result["query_examples"]["usda_summary"] = {
            "source_identity": "ZIP:00029",
            "unknown_coverage_identity": "ZIP:10168",
            "county_identity": "06017",
            "management_publisher_total": True,
            "original_archive_sha256": zip_row["original_archive_sha256"],
        }
    if "fema_nfhl" in sources:
        dbpath = index_file(destination, "fema_nfhl")
        with sqlite3.connect("file:" + str(dbpath.resolve()) + "?mode=ro", uri=True) as db:
            first = db.execute("SELECT source_key FROM fema_source_features "
                               "ORDER BY source_key LIMIT 1").fetchone()
        if not first:
            raise ValueError("No original FEMA polygons in installed source index")
        feature = query_publisher_id(destination, "fema_nfhl", original_id=first[0])
        if (feature["source_key"] != first[0] or
                feature["physical_site_verified"] is not False or
                not feature["original_reply_sha256"]):
            raise ValueError("FEMA source-native polygon read-only query failed")
        result["query_examples"]["fema_nfhl"] = {
            "native_source_key": first[0],
            "source_flood_zone": feature["flood_zone"],
            "original_response_sha256": feature["original_reply_sha256"],
            "geometry_precision": feature["geometry_precision"],
            "map_effective_date_verified": False,
        }
    for source in ("usda_continuous", "usda_classified"):
        if source not in sources:
            continue
        obs = query_raster_probe(destination, source, region="alaska", grid_index=0)
        if (obs.get("source") != source or
                obs.get("status") != "ORIGINAL_QA_RASTER_SAMPLE_NOT_FACILITY" or
                not obs.get("raw_sha256") or
                obs.get("physical_site_verified") is not False):
            raise ValueError("Original USDA raster pixel evidence missing: " + source)
        result["query_examples"][source] = {
            "original_QA_region": obs["region"],
            "grid_index": obs["probe_index"],
            "raw_response_sha256": obs["raw_sha256"],
            "classified_value": obs.get("class_value"),
            "continuous_raw_value": obs.get("pixel_value"),
            "not_a_physical_site": True,
        }
    result["source_rows"] = dict(sources)
    result["read_only_indexes_queryable"] = (
        bool(sources) and set(result["query_examples"]) == set(sources)
        and all(isinstance(x, int) and x > 0 for x in sources.values())
    )
    return result


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--destination", required=True)
    p.add_argument("--receipt")
    args = p.parse_args(argv)
    result = inspect(args.destination)
    if args.receipt:
        path = pathlib.Path(args.receipt)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("LANE_A_INSTALLED_READONLY_SMOKE=" + json.dumps(result, sort_keys=True))
    return 0 if result["read_only_indexes_queryable"] else 2


if __name__ == "__main__":
    sys.exit(main())
