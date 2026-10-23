"""Stage NOAA Storm Events details bulk exports with complete-year evidence.

Official yearly archives are *regional weather reports*. They are never
silently linked to a particular insured property, loss or policy.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
import gzip
import hashlib
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit

import requests
import json
import sys
import time

INDEX = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"
PUBLISHER = "NOAA NCEI Storm Events Details"
DETAIL = re.compile(r"StormEvents_details-ftp_v1\.0_d(\d{4})_c(\d{8})\.csv\.gz")
RAW_COLUMNS = frozenset((
    "EVENT_ID", "EPISODE_ID", "YEAR", "BEGIN_YEARMONTH", "BEGIN_DAY",
    "STATE", "EVENT_TYPE", "CZ_NAME", "BEGIN_LAT", "BEGIN_LON",
    "END_LAT", "END_LON", "DAMAGE_PROPERTY",
))
COLUMNS = (
    "event_id", "episode_id", "year", "begin_date", "state", "county_zone",
    "event_type", "begin_latitude", "begin_longitude", "end_latitude",
    "end_longitude", "damage_property_reported", "injuries_direct",
    "deaths_direct", "source_url", "coordinate_semantics",
)
SEMANTICS = "Reported NOAA event reference point, not hazard footprint or property loss"
MAX_RAW_BYTES = 100 * 1024 * 1024


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def choose_files(index_html: str, years: list[int]):
    if not years or len(set(years)) != len(years) or any(y < 1950 or y > 2100 for y in years):
        raise ValueError("Expected distinct NOAA source years between 1950 and 2100")
    candidates: dict[int, list[tuple[str, str]]] = {}
    for name, year_string, edition in ((m.group(0), m.group(1), m.group(2))
                                       for m in DETAIL.finditer(index_html)):
        y = int(year_string)
        candidates.setdefault(y, []).append((edition, name))
    missing = set(years) - set(candidates)
    if missing:
        raise ValueError(f"NOAA listing omitted requested years: {sorted(missing)}")
    return {y: max(candidates[y])[1] for y in sorted(years)}


def sha256(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download_file(session, url: str, dest: Path):
    """Bounded retries for upstream connection resets; never keep partial files."""
    if urlsplit(url).hostname != "www.ncei.noaa.gov" or not url.startswith(INDEX):
        raise ValueError("Source URL must use the official NOAA file directory")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(5):
        try:
            with session.get(
                url, stream=True, timeout=(20, 120),
                headers={"User-Agent": "Pharm3r-FacilityRisk-NOAA/1.0",
                         "Accept": "application/gzip", "Accept-Encoding": "identity"}
            ) as response:
                response.raise_for_status()
                if urlsplit(response.url).hostname != "www.ncei.noaa.gov":
                    raise ValueError("NOAA archive unexpectedly redirected off official host")
                size = 0
                with tmp.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            size += len(chunk)
                            if size > MAX_RAW_BYTES:
                                raise ValueError("Unexpectedly large NOAA yearly archive")
                            handle.write(chunk)
                with tmp.open("rb") as handle:
                    if size < 50 or handle.read(2) != b"\x1f\x8b":
                        raise ValueError("Downloaded NOAA file is missing gzip content")
            tmp.replace(dest)
            return dest
        except requests.RequestException as exc:
            # Only retry transient transport/429/5xx failures, not bad URLs,
            # access denial, changed source format or an invalid gzip payload.
            status = getattr(getattr(exc, "response", None), "status_code", None)
            retryable = status is None or status == 429 or 500 <= status < 600
            if not retryable or attempt == 4:
                raise
            delay = 2 ** attempt
            print(f"NOAA transient transfer error on attempt {attempt + 1}/5; "
                  f"retrying in {delay}s: {type(exc).__name__}", file=sys.stderr, flush=True)
            time.sleep(delay)
        finally:
            tmp.unlink(missing_ok=True)
    raise RuntimeError("Unreachable NOAA download retry boundary")

def _number(value: str, limit: int):
    raw = str(value or "").strip()
    if not raw:
        return ""
    n = int(raw)
    if n < 0 or n > limit:
        raise ValueError("Invalid source integer")
    return str(n)


def _coordinate(raw: str, limit: int):
    from math import isfinite
    raw = str(raw or "").strip()
    if not raw:
        return ""
    try:
        n = float(raw)
    except ValueError:
        return ""
    return str(n) if isfinite(n) and -limit <= n <= limit else ""


def normalize_year(raw_path: Path, year: int, source_url: str, writer, *,
                   minimum_rows: int = 1):
    seen = set()
    count = 0
    mapped = 0
    classes = set()
    with gzip.open(raw_path, "rt", newline="", encoding="utf-8-sig",
                   errors="replace") as stream:
        csv.field_size_limit(16 * 1024 * 1024)
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not RAW_COLUMNS.issubset(reader.fieldnames):
            raise ValueError("NOAA details schema changed: " +
                             ", ".join(sorted(RAW_COLUMNS - set(reader.fieldnames or ()))))
        for row in reader:
            eid = _number(row["EVENT_ID"], 10**15)
            if not eid or eid in seen:
                raise ValueError(f"Empty or duplicated NOAA EVENT_ID in {year}: {eid}")
            seen.add(eid)
            observed_year = _number(row.get("YEAR"), 2100)
            month_raw = str(row.get("BEGIN_YEARMONTH") or "").strip()
            day_raw = str(row.get("BEGIN_DAY") or "").strip()
            if observed_year != str(year) or not re.fullmatch(r"\d{6}", month_raw) or not day_raw.isdigit():
                raise ValueError(f"Unexpected NOAA source year or date in {year}")
            if int(month_raw[:4]) != year:
                raise ValueError("NOAA begin date refers to a different annual cohort")
            observed_date = date(year, int(month_raw[4:]), int(day_raw)).isoformat()
            event_type = str(row.get("EVENT_TYPE") or "").strip()
            state = str(row.get("STATE") or "").strip()
            if not event_type or not state:
                raise ValueError(f"NOAA mandatory category missing in {year}")
            lat = _coordinate(row.get("BEGIN_LAT"), 90)
            lon = _coordinate(row.get("BEGIN_LON"), 180)
            if not (lat and lon):
                lat = lon = ""
            else:
                mapped += 1
            writer.writerow({
                "event_id": eid, "episode_id": str(row.get("EPISODE_ID") or "").strip()[:30],
                "year": year, "begin_date": observed_date,
                "state": state[:90], "county_zone": str(row.get("CZ_NAME") or "").strip()[:160],
                "event_type": event_type[:100],
                "begin_latitude": lat, "begin_longitude": lon,
                "end_latitude": _coordinate(row.get("END_LAT"), 90),
                "end_longitude": _coordinate(row.get("END_LON"), 180),
                "damage_property_reported": str(row.get("DAMAGE_PROPERTY") or "").strip()[:40],
                "injuries_direct": _number(row.get("INJURIES_DIRECT"), 10**8),
                "deaths_direct": _number(row.get("DEATHS_DIRECT"), 10**8),
                "source_url": source_url, "coordinate_semantics": SEMANTICS,
            })
            count += 1
            classes.add(event_type)
    if count < minimum_rows:
        raise ValueError(f"Incomplete NOAA source year {year}: {count} < {minimum_rows}")
    return {"year": year, "event_records": count, "point_coordinates_reported": mapped,
            "point_coordinates_missing": count - mapped, "event_categories": len(classes),
            "source_url": source_url, "source_file": raw_path.name,
            "original_archive_sha256": sha256(raw_path), "original_archive_bytes": raw_path.stat().st_size}


def validate_normalized(path: Path, manifest: dict):
    if sha256(path) != manifest.get("normalized_sha256"):
        raise ValueError("NOAA normalized file SHA256 mismatch")
    counts = {}
    coords = {}
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise ValueError("NOAA normalized field names do not match contract")
        for row in reader:
            yr = int(row["year"])
            counts[yr] = counts.get(yr, 0) + 1
            if row["begin_latitude"] and row["begin_longitude"]:
                coords[yr] = coords.get(yr, 0) + 1
    expected = {x["year"]: x["event_records"] for x in manifest["partitions"]}
    if counts != expected or sum(counts.values()) != manifest["total_events"]:
        raise ValueError("NOAA source count mismatch in normalized artifact")
    for p in manifest["partitions"]:
        if coords.get(p["year"], 0) != p["point_coordinates_reported"]:
            raise ValueError("NOAA geographic completeness mismatch")
    return True


def public_summary(manifest: dict, run_url: str):
    years = sorted(x["year"] for x in manifest["partitions"])
    return {
        "schema_version": "1.0", "source": "NOAA Storm Events Details",
        "state": "staged_source_artifact",
        "records": manifest["total_events"],
        "checked_at": manifest["generated_at"],
        "scope": f"United States and adjoining waters; reported events for {years[0]}-{years[-1]} only",
        "details": ("Complete requested-year files normalized and archived as expiring GitHub Actions "
                    "artifacts. Not installed on permanent backend; regional NOAA damage estimates "
                    "are NOT losses or catastrophe overlays at any insured facility."),
        "documentation": INDEX,
        "artifact_run_url": run_url,
        "manifest_sha256": manifest["normalized_sha256"],
        "record_years": years,
        "point_coordinates_reported": sum(x["point_coordinates_reported"] for x in manifest["partitions"]),
        "year_partitions": [
            {"year": x["year"], "records": x["event_records"],
             "source_edition": x["source_file"], "sha256": x["original_archive_sha256"]}
            for x in manifest["partitions"]
        ],
    }


def stage(years: list[int], out: Path, manifest_path: Path, raw_dir: Path,
          summary_path: Path | None, session=None, minimum_rows: int = 1000,
          run_url: str = ""):
    session = session or requests.Session()
    listing = session.get(INDEX, timeout=40, headers={"User-Agent": "FacilityRisk-NOAA-Bulk/1.0"})
    listing.raise_for_status()
    files = choose_files(listing.text, years)
    out.parent.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    partial = out.with_suffix(out.suffix + ".part")
    parts = []
    try:
        with gzip.open(partial, "wt", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=COLUMNS, extrasaction="raise")
            writer.writeheader()
            for year, filename in files.items():
                url = urljoin(INDEX, filename)
                raw = raw_dir / filename
                download_file(session, url, raw)
                part = normalize_year(raw, year, url, writer, minimum_rows=minimum_rows)
                print(f"NOAA {year}: {part['event_records']} events; "
                      f"{part['point_coordinates_reported']} coordinate points", flush=True)
                parts.append(part)
        partial.replace(out)
    finally:
        partial.unlink(missing_ok=True)
    when = utcnow()
    manifest = {
        "schema_version": "1.0", "publisher": PUBLISHER, "source_index_url": INDEX,
        "generated_at": when, "complete_requested_years": True,
        "requested_years": sorted(years), "partitions": parts,
        "total_events": sum(x["event_records"] for x in parts),
        "normalized_fields": list(COLUMNS), "normalized_sha256": sha256(out),
        "scope_note": ("NOAA reported weather events, not verified physical facilities, "
                       "individual property losses, claims or a complete hazard footprint"),
    }
    validate_normalized(out, manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if summary_path:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(public_summary(manifest, run_url), indent=2) + "\n",
                                encoding="utf-8")
    return manifest


def years_arg(value: str):
    if "-" in value and "," not in value:
        a, b = value.split("-", 1)
        years = list(range(int(a), int(b) + 1))
    else:
        years = [int(x.strip()) for x in value.split(",")]
    if not years or len(years) > 40:
        raise ValueError("NOAA years must contain between one and forty annual partitions")
    return years


def main():
    p = argparse.ArgumentParser(description="Download official NOAA bulk Storm Events annual details")
    p.add_argument("--years", default="2023-2026")
    p.add_argument("--output", type=Path, default=Path("data/noaa/storm-events.csv.gz"))
    p.add_argument("--manifest", type=Path, default=Path("data/noaa/storm-events-manifest.json"))
    p.add_argument("--raw-dir", type=Path, default=Path("data/noaa/raw"))
    p.add_argument("--summary", type=Path, default=Path("web/ingestion/noaa-storm-events.json"))
    p.add_argument("--min-rows", type=int, default=5000)
    a = p.parse_args()
    import os
    repo = os.getenv("GITHUB_REPOSITORY", "jhennessy-pharm3r/FacilityTest")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    run_url = f"https://github.com/{repo}/actions/runs/{run_id}" if run_id else ""
    result = stage(years_arg(a.years), a.output, a.manifest, a.raw_dir,
                   a.summary, minimum_rows=a.min_rows, run_url=run_url)
    print(json.dumps({"rows": result["total_events"],
                      "years": result["requested_years"], "source": INDEX}, indent=2))


if __name__ == "__main__":
    main()
