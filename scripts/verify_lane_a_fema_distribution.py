"""Independently verify official FEMA count-only and WFS source receipts.

A national feature count is publisher-reported metadata, NOT a downloaded
national polygon corpus or a site-linked risk dataset.
"""
import argparse
import hashlib
import json
import pathlib
import sys
import xml.etree.ElementTree as ET

from scripts.lane_a_fema_distribution import wfs_feature_types


def verify(directory):
    directory = pathlib.Path(directory)
    m = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    report = {
        "count_response_verified": False,
        "wfs_capabilities_verified": False,
        "national_fema_polygon_source_rows_downloaded": 0,
        "national_fema_polygon_source_rows_indexed": 0,
        "national_source_completeness": False,
        "source_count_from_response": None,
        "source_protocol_errors": [m.get("rest_count_error"), m.get("wfs_error")],
    }
    if (m.get("national_downloaded_polygons") != 0 or
            m.get("source_only_indexed_polygons") != 0 or
            m.get("full_national_download_verified")):
        raise ValueError("Misleading national download/index status in metadata-only probe")
    if m["rest_count_state"] == "DOWNLOADED_RESPONSE_ONLY":
        receipt = m["rest_count_receipt"]
        raw = (directory / "raw" / receipt["raw_file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != receipt["sha256"]:
            raise ValueError("FEMA source count original response SHA mismatch")
        if len(raw) != receipt["bytes"]:
            raise ValueError("FEMA source count original byte-count mismatch")
        doc = json.loads(raw)
        count = doc.get("count")
        if (not isinstance(count, int) or isinstance(count, bool) or
                count <= 0 or
                count != m["reported_current_service_feature_count"] or
                receipt["query_parameters"] !=
                {"f": "json", "where": "1=1", "returnCountOnly": "true"}):
            raise ValueError("Publisher count, query parameters or original response mismatched")
        if receipt.get("transport", {}).get("http_method") not in ("GET", "POST", "fixture_or_unspecified"):
            raise ValueError("No supported official ArcGIS request transport recorded")
        report["source_count_from_response"] = count
        report["count_response_verified"] = True
    elif m.get("reported_current_service_feature_count") is not None:
        raise ValueError("FEMA count unverified but numeric total present")
    if m["wfs_state"] == "DOWNLOADED_CAPABILITIES_ONLY":
        receipt = m["wfs_receipt"]
        raw = (directory / "raw" / receipt["raw_file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != receipt["sha256"]:
            raise ValueError("FEMA WFS source XML checksum mismatch")
        if len(raw) != receipt["bytes"]:
            raise ValueError("FEMA WFS response byte length mismatch")
        types = wfs_feature_types(raw)
        if types != m["wfs_source_feature_types"]:
            raise ValueError("FEMA WFS reported source schemas do not reconcile")
        report["wfs_capabilities_verified"] = True
        report["wfs_feature_type_count"] = len(types)
    if not (report["count_response_verified"] or report["wfs_capabilities_verified"]):
        raise ValueError("No successfully downloaded FEMA official national distribution response")
    return report


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--directory", default="data/lane_a/fema_distribution")
    args = p.parse_args(argv)
    try:
        result = verify(args.directory)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, ET.ParseError) as exc:
        print("LANE_A_FEMA_DISTRIBUTION_VERIFY_FAILED=" + str(exc), file=sys.stderr)
        return 2
    print("LANE_A_FEMA_DISTRIBUTION_VERIFY_PASS=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
