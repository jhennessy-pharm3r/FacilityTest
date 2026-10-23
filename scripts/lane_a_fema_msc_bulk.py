"""FEMA MSC official county-product bulk download and native archive inventory.

No source rows are claimed unless archive content actually parses and reconciles.
Documented FEMA example productID=NFHL_51013C is a county-specific source,
not a national Census or a physical-site match. FEMA source rights prevail.
"""
import argparse
import hashlib
import io
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone

URL = "https://msc.fema.gov/portal/downloadProduct"
DOC = "https://msc.fema.gov/msccontent/FEMA_Hazard_Products_Direct_Download.pdf"
PRODUCT_ID = "NFHL_51013C"
MAX_BYTES = 150 * 1024 * 1024


def download(product_id=PRODUCT_ID):
    if not product_id.startswith("NFHL_") or not product_id[5:].isalnum():
        raise ValueError("Invalid documented FEMA MSC NFHL product ID")
    url = URL + "?" + urllib.parse.urlencode({"productID": product_id})
    req = urllib.request.Request(url, headers={
        "User-Agent": "FacilityRisk-LaneA-Official-FEMA-MSC/1.0",
        "Accept": "application/zip,application/octet-stream",
    })
    with urllib.request.urlopen(req, timeout=90) as response:
        raw = response.read(MAX_BYTES + 1)
        final_url = response.geturl()
    if len(raw) > MAX_BYTES:
        raise ValueError("County source package exceeds 150 MB bounded diagnostic")
    return raw, final_url


def run(out_dir, fetch=download, product_id=PRODUCT_ID):
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    m = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "FEMA Map Service Center NFHL county product",
        "documented_direct_download_instructions": DOC,
        "product_id": product_id,
        "source_url": URL + "?" + urllib.parse.urlencode({"productID": product_id}),
        "scope": "one officially documented county-product example, NOT national NFHL",
        "original_archive_downloaded": False, "file_format_verified": False,
        "normalized_polygon_count": None, "indexed_polygon_count": 0,
        "physically_correlated_insured_sites": 0, "deployed_count": 0,
        "records": [], "error": None,
    }
    try:
        raw, actual_url = fetch(product_id)
        m["actual_download_url"] = actual_url
        m["original_bytes_downloaded"] = len(raw)
        m["original_raw_sha256"] = hashlib.sha256(raw).hexdigest()
        if not zipfile.is_zipfile(io.BytesIO(raw)):
            raise ValueError("MSC response is not a ZIP (may be unavailable, HTML or access denied)")
        target = out_dir / (product_id + ".zip")
        target.write_bytes(raw)
        m["original_archive_downloaded"] = True
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            seen_names = set()
            for f in z.infolist():
                if f.is_dir():
                    continue
                path = pathlib.PurePosixPath(f.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("Rejected unsafe archive path")
                if f.filename in seen_names:
                    raise ValueError("Rejected duplicate archive filename")
                seen_names.add(f.filename)
                m["records"].append({
                    "source_file": f.filename,
                    "compressed_bytes": f.compress_size,
                    "uncompressed_bytes": f.file_size,
                    "crc32": f.CRC,
                    "file_type": pathlib.Path(f.filename).suffix.lower(),
                })
        m["archive_members"] = len(m["records"])
        m["archive_has_geodatabase_or_shapes"] = any(
            "/gdb/" in r["source_file"].lower() or
            r["file_type"] in (".gdbtable", ".shp", ".gpkg")
            for r in m["records"]
        )
        m["file_format_verified"] = m["archive_has_geodatabase_or_shapes"]
    except (OSError, ValueError, urllib.error.URLError, zipfile.BadZipFile) as exc:
        m["error"] = type(exc).__name__ + ": " + str(exc)[:500]
    (out_dir / "manifest.json").write_text(json.dumps(m, indent=2, sort_keys=True) + "\n")
    return m


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default="data/lane_a/fema_msc_county")
    args = p.parse_args(argv)
    m = run(args.out_dir)
    print("LANE_A_FEMA_MSC_COUNTY=" + json.dumps({
        "downloaded": m["original_archive_downloaded"], "format_verified": m["file_format_verified"],
        "product_id": m["product_id"], "bytes": m.get("original_bytes_downloaded"),
        "original_sha256": m.get("original_raw_sha256"),
        "archive_members": m.get("archive_members"), "types": sorted({
            r["file_type"] for r in m["records"]}),
        "normalized_polygon_count": m["normalized_polygon_count"],
        "indexed_polygon_count": m["indexed_polygon_count"],
        "error": m.get("error"),
    }, sort_keys=True))
    return 0 if m["original_archive_downloaded"] and m["file_format_verified"] else 2


if __name__ == "__main__":
    sys.exit(main())
