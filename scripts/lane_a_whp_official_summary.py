"""Official USDA WHP 2023 nationwide aggregate ZIP inventory with SHA-256.

Aggregate publisher summaries are contextual administrative geography only:
never a facility, raster cell, fire occurrence or loss claim.
"""
import argparse
import csv
import hashlib
import io
import json
import pathlib
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

USDA_ZIP = "https://research.fs.usda.gov/sites/default/files/2024-07/firelab-whp2023_datasummaries.zip"
MAX_BYTES = 60 * 1024 * 1024
MAX_MEMBER_BYTES = 250 * 1024 * 1024


def download(url=USDA_ZIP):
    req = urllib.request.Request(url, headers={
        "User-Agent": "FacilityRisk-LaneA-USDA-WHP-2023-Official/1.0",
        "Accept": "application/zip,application/octet-stream",
    })
    with urllib.request.urlopen(req, timeout=50) as response:
        raw = response.read(MAX_BYTES + 1)
        final_url = response.geturl()
    if len(raw) > MAX_BYTES:
        raise ValueError("Publisher summary archive unexpectedly exceeds 60MB limit")
    if not zipfile.is_zipfile(io.BytesIO(raw)):
        raise ValueError("Official publisher returned non-ZIP response")
    return raw, final_url


def member_summary(filename, raw):
    result = {"archive_path": filename, "bytes": len(raw),
              "sha256": hashlib.sha256(raw).hexdigest(), "state": "INVENTORIED"}
    if filename.lower().endswith(".csv"):
        text = raw.decode("utf-8-sig", errors="strict")
        rows = csv.reader(io.StringIO(text))
        head = next(rows, [])
        result.update({"field_names": head, "non_header_rows": sum(bool(r) for r in rows),
                       "format": "csv"})
    elif filename.lower().endswith(".xlsx"):
        result["format"] = "xlsx"
        with zipfile.ZipFile(io.BytesIO(raw)) as inner:
            worksheets = []
            for name in inner.namelist():
                if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"):
                    root = ET.fromstring(inner.read(name))
                    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                    sample = root.findall(".//x:sheetData/x:row", namespace)
                    worksheets.append({"part": name, "xml_row_elements": len(sample),
                                       "nonempty_record_rows_unknown": True})
            result["worksheets"] = worksheets
    elif filename.lower().endswith((".txt", ".md")) and len(raw) < 200_000:
        result["format"] = "text"
        result["line_count"] = len(raw.splitlines())
    else:
        result["format"] = "other"
    return result


def run(out_dir, fetch=download):
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    m = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
         "publisher": "USDA Forest Service Fire Modeling Institute",
         "source_url": USDA_ZIP, "product_version": "WHP 2023",
         "scope": "Official publisher ZIP data summaries, NOT 270m national raster",
         "not_site_level": True, "site_matches": 0, "durable_deployed": 0,
         "complete_source_raster": False, "source_downloaded": False,
         "archive_sha256": None, "source_members": [],
         "normalized_aggregate_rows": 0, "indexed_aggregate_rows": 0,
         "rejected_archive_members": [], "warnings": []}
    try:
        raw, url = fetch()
        target = out_dir / "whp2023_official_summaries.zip"
        target.write_bytes(raw)
        m["source_downloaded"] = True
        m["actual_download_url"] = url
        m["archive_bytes"] = len(raw)
        m["archive_sha256"] = hashlib.sha256(raw).hexdigest()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            members = z.infolist()
            m["archive_member_count"] = len(members)
            for entry in members:
                filename = entry.filename
                if entry.is_dir():
                    continue
                if (filename.startswith("/") or ".." in pathlib.PurePosixPath(filename).parts or
                        entry.file_size > MAX_MEMBER_BYTES):
                    m["rejected_archive_members"].append(
                        {"path": filename, "reason": "unsafe_member_path_or_size"})
                    continue
                data = z.read(entry)
                if len(data) != entry.file_size:
                    m["rejected_archive_members"].append(
                        {"path": filename, "reason": "uncompressed_member_size_mismatch"})
                    continue
                try:
                    result = member_summary(filename, data)
                except (ValueError, UnicodeError, ET.ParseError, zipfile.BadZipFile) as exc:
                    m["rejected_archive_members"].append({"path": filename, "reason": str(exc)[:250]})
                    continue
                m["source_members"].append(result)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        m["error"] = type(exc).__name__ + ": " + str(exc)[:500]
    m["inventory_verified"] = bool(
        m["source_downloaded"] and
        len(m["source_members"]) > 0 and
        len(m["rejected_archive_members"]) == 0 and
        len(m["archive_sha256"] or "") == 64
    )
    (out_dir / "manifest.json").write_text(json.dumps(m, indent=2, sort_keys=True) + "\n")
    return m


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default="data/lane_a/whp_official_summary")
    args = p.parse_args(argv)
    m = run(args.out_dir)
    print("LANE_A_USDA_SUMMARY=" + json.dumps({
        "inventory_verified": m["inventory_verified"],
        "archive_sha256": m["archive_sha256"],
        "archive_bytes": m.get("archive_bytes"),
        "member_count": m.get("archive_member_count"),
        "files": [{"name": f["archive_path"], "format": f["format"],
                   "rows": f.get("non_header_rows"),
                   "sheet_rows": f.get("worksheets")} for f in m["source_members"]],
        "rejected": m["rejected_archive_members"],
        "error": m.get("error"), "national_raster_complete": False,
    }, sort_keys=True))
    return 0 if m["inventory_verified"] else 2


if __name__ == "__main__":
    sys.exit(main())
