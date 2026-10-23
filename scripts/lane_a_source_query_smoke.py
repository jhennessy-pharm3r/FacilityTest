"""Read-only QA against downloaded official USDA WHP 2023 source-only SQLite.

Never claims a ZIP/county/state/jurisdiction is a real insured physical site.
"""
import argparse
import json
import pathlib
import sys

from facilityrisk.lane_a_source_query import source_whp_record


def validate(index_file):
    probes = (
        ("zip", "00029"),
        ("zip", "10168"),      # no WHP area values in original publisher XLSX
        ("county", "06017"),   # native county GEOID, includes leading zero
        ("state", "06"),       # publisher FIPS state identity
        ("management_jurisdiction", "US Forest Service"),
        ("management_jurisdiction", "Grand Total"),
    )
    result = {
        "source": "official_USDA_WHP_2023_geography_summaries",
        "queryable_source_geographies": [],
        "verified_physical_site_links": 0,
        "durable_serving_records": 0,
        "production_deployed_records": 0,
        "source_only": True,
        "all_probes_pass": False,
    }
    for kind, key in probes:
        observation = source_whp_record(index_file, kind, key)
        row = {
            "geography_type": kind, "native_source_id": key,
            "query_status": observation.get("query_record_status",
                                           observation.get("state")),
            "area_coverage": observation.get("source_coverage"),
            "area_acres": observation.get("total_acres"),
            "source_zip_sha256": observation.get("original_archive_sha256"),
            "source_workbook_sha256": observation.get("original_xlsx_sha256"),
            "physical_site_verified": observation.get("physical_site_verified"),
            "production_app_deployed": observation.get("app_deployed"),
        }
        result["queryable_source_geographies"].append(row)
    result["all_probes_pass"] = (
        all(x["query_status"] == "STAGED_SOURCE_AGGREGATE" for x in result["queryable_source_geographies"]) and
        all(x["source_zip_sha256"] and len(x["source_zip_sha256"]) == 64 for x in result["queryable_source_geographies"]) and
        all(not x["physical_site_verified"] and not x["production_app_deployed"]
            for x in result["queryable_source_geographies"]) and
        result["queryable_source_geographies"][1]["area_coverage"] == "UNKNOWN_NO_AREA_VALUES" and
        result["queryable_source_geographies"][1]["area_acres"] is None and
        result["queryable_source_geographies"][0]["area_acres"] == 1387.0
    )
    return result


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--index", default="data/lane_a/whp_official_index/whp2023-source-geographies.sqlite")
    p.add_argument("--receipt", default="data/lane_a/whp_official_index/read_only_query_smoke.json")
    args = p.parse_args(argv)
    result = validate(args.index)
    path = pathlib.Path(args.receipt)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("LANE_A_USDA_READONLY_QUERY=" + json.dumps(result, sort_keys=True))
    return 0 if result["all_probes_pass"] else 2


if __name__ == "__main__":
    sys.exit(main())
