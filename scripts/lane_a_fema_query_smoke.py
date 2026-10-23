"""Independent live FEMA NFHL polygon/source-key/rtree query smoke test.

Does not create canonical facility links or infer flood status for unassessed
properties. Counts are strictly within independently enumerated test windows.
"""
import argparse
import json
import pathlib
import sqlite3
import sys

from facilityrisk.lane_a_source_query import source_fema_polygon


def validate(directory):
    directory = pathlib.Path(directory)
    m = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    dbpath = directory / "fema-window-index.sqlite"
    con = sqlite3.connect("file:" + str(dbpath.resolve()) + "?mode=ro", uri=True)
    try:
        integrity = con.execute("PRAGMA quick_check").fetchone()[0]
        total = con.execute("SELECT COUNT(*) FROM fema_source_features").fetchone()[0]
        index = con.execute("SELECT COUNT(*) FROM fema_source_bounds").fetchone()[0]
        membership = con.execute("SELECT COUNT(*) FROM fema_window_membership").fetchone()[0]
        distinct_keys = con.execute(
            "SELECT COUNT(DISTINCT source_key) FROM fema_source_features").fetchone()[0]
        generalized = con.execute(
            "SELECT COUNT(*) FROM fema_source_features WHERE geometry_tolerance_degrees>0"
        ).fetchone()[0]
        missing_legacy_ids = con.execute(
            "SELECT COUNT(*) FROM fema_source_features "
            "WHERE dfirm_id IS NULL OR fld_ar_id IS NULL").fetchone()[0]
        first = con.execute(
            "SELECT source_key FROM fema_source_features ORDER BY source_key LIMIT 1"
        ).fetchone()
        windows = {
            n: con.execute("SELECT COUNT(*) FROM fema_window_membership WHERE window=?", (n,)).fetchone()[0]
            for n in sorted(m.get("windows", {}))
        }
    finally:
        con.close()
    exemplar = source_fema_polygon(dbpath, first[0]) if first else None
    full_window_counts_match = all(
        w.get("status") == "COMPLETE_WITHIN_WINDOW" and
        w.get("server_count") == w.get("id_count") == windows.get(name)
        for name, w in m.get("windows", {}).items()
    )
    pass_gate = bool(
        m.get("all_requested_windows_complete") and full_window_counts_match
        and len(windows) == m.get("requested_windows") and
        total > 0 and total == distinct_keys == index ==
        m.get("source_feature_count") and
        membership == m.get("window_membership_count") ==
        sum(windows.values()) and
        generalized == m.get("geometry_generalized_observations") and
        missing_legacy_ids == 0 and integrity == "ok" and
        exemplar is not None and exemplar.get("source_polygon_geometry_indexed")
        and exemplar.get("original_reply_sha256") and
        exemplar["physical_site_verified"] is False and
        exemplar["app_deployed"] is False
    )
    return {
        "read_only_source_query_verified": pass_gate,
        "window_source_id_and_server_count_reconciled": full_window_counts_match,
        "source_windows": windows,
        "original_polygon_count": total,
        "distinct_source_native_keys": distinct_keys,
        "rtree_index_rows": index,
        "window_polygon_membership_count": membership,
        "source_polygons_missing_dfirm_or_area_id": missing_legacy_ids,
        "generalized_geometry_review_only": generalized,
        "first_source_key": exemplar["source_key"] if exemplar else None,
        "first_polygon_original_reply_sha256": (
            exemplar.get("original_reply_sha256") if exemplar else None
        ),
        "sqlite_integrity": integrity,
        "publisher_nationwide_count": None,
        "effective_date_per_dfirm_verified": False,
        "source_only_index": True,
        "independently_reviewed_facilities": 0,
        "durable_indexed": 0,
        "deployed": 0,
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--directory", default="data/lane_a/paged_windows")
    args = p.parse_args(argv)
    result = validate(args.directory)
    dest = pathlib.Path(args.directory) / "source_query_smoke.json"
    dest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("LANE_A_FEMA_READONLY_QUERY=" + json.dumps(result, sort_keys=True))
    return 0 if result["read_only_source_query_verified"] else 2


if __name__ == "__main__":
    sys.exit(main())
