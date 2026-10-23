"""Probe official FEMA NFHL REST national record count and OGC WFS capabilities.

NEVER equate publisher-reported national count with downloaded feature rows.
FEMA recommends the WFS for spatially bounded features (max 1000); entire
states/counties require authorized full downloads through the Map Service Center.
"""
import argparse
import hashlib
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from scripts.lane_a_nfhl_paged import FEMA_LAYER, query_http

WFS = "https://hazards.fema.gov/arcgis/services/public/NFHL/MapServer/WFSServer"
MAX_WFS_BYTES = 8_000_000


def fetch_wfs():
    params = {"service": "WFS", "request": "GetCapabilities", "version": "2.0.0"}
    url = WFS + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": "FacilityRisk-LaneA-Public-FEMA-WFS/1.0",
        "Accept": "application/xml,text/xml",
    })
    with urllib.request.urlopen(req, timeout=28) as response:
        data = response.read(MAX_WFS_BYTES + 1)
        final_url = response.geturl()
    if len(data) > MAX_WFS_BYTES:
        raise ValueError("Official WFS capabilities exceed bounded 8MB limit")
    return data, final_url


def wfs_feature_types(raw):
    root = ET.fromstring(raw)
    if root.tag.split("}")[-1] not in ("WFS_Capabilities", "WFS_CapabilitiesType"):
        raise ValueError("Government WFS response not WFS_Capabilities XML")
    names = []
    for item in root.iter():
        if item.tag.split("}")[-1] == "FeatureType":
            for child in item:
                if child.tag.split("}")[-1] == "Name" and child.text:
                    names.append(child.text.strip())
                    break
    if not names:
        raise ValueError("Government WFS capabilities contain no source feature types")
    return names


def run(out_dir, rest=query_http, wfs=fetch_wfs):
    out_dir = pathlib.Path(out_dir)
    rawdir = out_dir / "raw"
    rawdir.mkdir(parents=True, exist_ok=True)
    m = {
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "source_id": "FEMA_NFHL_OFFICIAL_NATIONAL_DISTRIBUTION_DIAGNOSTIC",
        "publisher": "FEMA", "arcgis_layer": FEMA_LAYER, "official_wfs": WFS,
        "national_downloaded_polygons": 0, "normalized_polygons": 0,
        "source_only_indexed_polygons": 0, "deployed_polygons": 0,
        "physical_sites_matched": 0,
        "rest_count_state": "PROBED", "wfs_state": "PROBED",
        "full_national_download_verified": False,
    }
    params = {"f": "json", "where": "1=1", "returnCountOnly": "true"}
    try:
        reply = rest(params)
        if len(reply) == 4:
            doc, raw, url, transport = reply
        else:
            doc, raw, url = reply
            transport = {"http_method": "fixture_or_unspecified"}
        count = doc.get("count")
        if (not isinstance(count, int) or isinstance(count, bool) or count <= 0):
            raise ValueError("FEMA national count is absent, invalid or zero")
        filename = "official_nfhl_28_national_count_only.json"
        (rawdir / filename).write_bytes(raw)
        m["rest_count_state"] = "DOWNLOADED_RESPONSE_ONLY"
        m["reported_current_service_feature_count"] = count
        m["reported_count_is_not_downloaded_rows"] = True
        m["rest_count_receipt"] = {
            "raw_file": filename, "source_url": url,
            "query_parameters": params, "transport": transport,
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
        }
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError, KeyError) as exc:
        m["rest_count_error"] = type(exc).__name__ + ": " + str(exc)[:500]
        m["reported_current_service_feature_count"] = None
    try:
        raw, url = wfs()
        types = wfs_feature_types(raw)
        filename = "official_wfs_capabilities.xml"
        (rawdir / filename).write_bytes(raw)
        m["wfs_state"] = "DOWNLOADED_CAPABILITIES_ONLY"
        m["wfs_source_feature_types"] = types
        m["wfs_flood_zone_candidates"] = [x for x in types
                                           if ("Flood" in x or "Haz" in x or "Fld" in x)]
        m["wfs_receipt"] = {
            "raw_file": filename, "source_url": url,
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "xml_feature_type_count": len(types),
        }
    except (OSError, ValueError, ET.ParseError) as exc:
        m["wfs_error"] = type(exc).__name__ + ": " + str(exc)[:500]
    m["at_least_one_official_distribution_reachable"] = (
        m["rest_count_state"] == "DOWNLOADED_RESPONSE_ONLY" or
        m["wfs_state"] == "DOWNLOADED_CAPABILITIES_ONLY"
    )
    (out_dir / "manifest.json").write_text(json.dumps(m, indent=2, sort_keys=True) + "\n")
    return m


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default="data/lane_a/fema_distribution")
    args = p.parse_args(argv)
    m = run(args.out_dir)
    print("LANE_A_FEMA_DISTRIBUTION=" + json.dumps({
        "fema_rest_status": m["rest_count_state"],
        "fema_rest_publisher_count_not_downloaded": m["reported_current_service_feature_count"],
        "wfs_status": m["wfs_state"],
        "wfs_feature_types": len(m.get("wfs_source_feature_types", [])),
        "wfs_flood_type_names": m.get("wfs_flood_zone_candidates", []),
        "official_distribution_success": m["at_least_one_official_distribution_reachable"],
        "errors": [m.get("rest_count_error"), m.get("wfs_error")],
        "actual_national_polygons_downloaded": 0,
    }, sort_keys=True))
    return 0 if m["at_least_one_official_distribution_reachable"] else 2


if __name__ == "__main__":
    sys.exit(main())
