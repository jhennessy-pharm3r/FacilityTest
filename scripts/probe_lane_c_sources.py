"""Download and inventory real official Lane C files on a network-enabled CI runner.

This is source-level QA, not validated unique incident ingestion. Write only
aggregate metadata; do not publish the private raw files as CI artifacts.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
import tempfile
import zipfile
import requests
from openpyxl import load_workbook
from build_industrial_incidents import stage

SOURCES = {
    "nrc_2025": ("https://nrc.uscg.mil/FOIAFiles/CY25.xlsx", 60_000_000),
    "csb_2026_09": ("https://www.csb.gov/assets/1/6/Copy_of_Accidental_Release_Events_2026-09-01.xlsx", 30_000_000),
    "phmsa_hazardous_liquid_2010_present": ("https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/data_statistics/pipeline/accident_hazardous_liquid_jan2010_present.zip", 150_000_000),
}
def download(url, limit, path):
    session = requests.Session()
    with session.get(url, timeout=(20, 150), stream=True,
                     headers={"User-Agent": "FacilityRisk-LaneC-SchemaProbe/1.0",
                              "Accept-Encoding": "identity"}) as response:
        response.raise_for_status()
        if not response.url.startswith("https://"):
            raise ValueError("Insecure official-source redirect")
        size = 0
        digest = hashlib.sha256()
        with path.open("wb") as target:
            for chunk in response.iter_content(1024 * 1024):
                if chunk:
                    size += len(chunk)
                    if size > limit:
                        raise ValueError("Publisher export beyond safety limit")
                    target.write(chunk)
                    digest.update(chunk)
    if size < 1024:
        raise ValueError("Publisher file unexpectedly small")
    return size, digest.hexdigest()
def workbook_probe(path):
    with zipfile.ZipFile(path) as archive:
        if "xl/workbook.xml" not in archive.namelist():
            raise ValueError("Not an XLSX workbook")
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        results = []
        for sh in book.worksheets:
            iterator = sh.iter_rows(values_only=True)
            header = next(iterator, [])
            # Actual observed nonempty rows, not sheet.max_row.
            observed = sum(any(x is not None for x in row) for row in iterator)
            candidates = []
            for idx, values in enumerate(sh.iter_rows(max_row=12, values_only=True), 1):
                words = [str(x or "").strip() for x in values]
                matches = sum(bool(re.search(r"(?i)\\b(date|time|incident|release|company|facility|state|address|city|fatal|injur|report|id)\\b", x)) for x in words)
                if matches >= 3:
                    candidates.append({"row": idx, "candidate_field_names": words[:35]})
            results.append({"sheet": sh.title, "actual_nonempty_data_rows": observed,
                            "header": [str(x or "")[:100] for x in header[:80]],
                            "header_candidates": candidates})
        return results
    finally:
        book.close()
def zip_probe(path):
    with zipfile.ZipFile(path) as archive:
        files = archive.infolist()
        if any(i.file_size > 600_000_000 or i.filename.startswith("/")
               or ".." in Path(i.filename).parts for i in files):
            raise ValueError("Unsafe publisher ZIP")
        return [{"name": i.filename, "bytes": i.file_size}
                for i in files if not i.is_dir()]
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {"checked_at": datetime.now(timezone.utc).isoformat(),
                "state": "DOWNLOADED_SCHEMA_PROBE_ONLY_NOT_NORMALIZED",
                "deployment": "NOT_DEPLOYED", "sources": {}}
    with tempfile.TemporaryDirectory() as work:
        for name, (url, limit) in SOURCES.items():
            target = Path(work) / (name + (".zip" if url.endswith(".zip") else ".xlsx"))
            report = {"source_url": url}
            try:
                report["downloaded_bytes"], report["raw_sha256"] = download(url, limit, target)
                report["content"] = zip_probe(target) if target.suffix == ".zip" else workbook_probe(target)
                report["state"] = "DOWNLOADED_AND_INVENTORIED_NOT_NORMALIZED"
                if name == "nrc_2025":
                    try:
                        result = stage("nrc", target, Path(work) / "nrc-normalized.csv.gz",
                            args.output / "nrc-normalized-manifest.json", source_url=url,
                            sheet="INCIDENT_COMMONS", mapping={
                                "id": "SEQNOS", "date": "INCIDENT_DATE_TIME",
                                "city": "LOCATION_NEAREST_CITY", "state": "LOCATION_STATE"},
                            minimum_rows=10000)
                        report["normalization"] = {
                            "raw_rows": result["raw_rows"],
                            "accepted_rows": result["accepted_rows"],
                            "rejected_rows": result["rejected_rows"],
                            "duplicate_source_ids": result["duplicate_source_ids"],
                            "missing_coordinates": result["missing_coordinates"],
                            "failure_reasons": result["failure_reasons"],
                            "normalized_sha256": result["normalized_sha256"]}
                        report["state"] = "STAGED_AND_CONTENT_VALIDATED_NOT_INDEXED"
                    except Exception as error:
                        report["normalization_blocker"] = type(error).__name__ + ": " + str(error)[:350]
            except Exception as error:
                report["state"] = "BLOCKED"
                report["error"] = type(error).__name__ + ": " + str(error)[:350]
            manifest["sources"][name] = report
            (args.output / "official-source-probe.json").write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: {"state": value["state"],
                            "bytes": value.get("downloaded_bytes"),
                            "tables": [{"table": t.get("sheet") or t.get("name"),
                                         "observed_rows": t.get("actual_nonempty_data_rows"),
                                         "headers": t.get("header", [])[:25],
                                         "header_candidates": t.get("header_candidates", [])}
                                        for t in value.get("content", [])],
                            "sha256": value.get("raw_sha256"),
                            "error": value.get("error"),
                            "normalization": value.get("normalization"),
                            "normalization_blocker": value.get("normalization_blocker")} for key, value
                      in manifest["sources"].items()}, indent=2))
    if any(item["state"] == "BLOCKED" for item in manifest["sources"].values()):
        raise SystemExit("One or more official-source downloads blocked; see artifact report")
if __name__ == "__main__":
    main()
