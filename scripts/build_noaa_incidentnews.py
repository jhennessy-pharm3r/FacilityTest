"""Stage official NOAA OR&R IncidentNews selected spill-response incidents.

This is a selective scientific-response catalog, not USCG NRC's complete
spill-notification register, a facility inventory, or verified insured losses.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date, datetime, timezone
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit

import requests

URL = "https://incidentnews.noaa.gov/raw/incidents.csv"
DOCS = "https://incidentnews.noaa.gov/raw/index"
PUBLISHER = "NOAA Office of Response and Restoration IncidentNews"
MAX_BYTES = 20 * 1024 * 1024
RAW_REQUIRED = frozenset((
    "id", "open_date", "name", "location", "lat", "lon", "threat",
    "tags", "commodity", "max_ptl_release_gallons", "posts",
    "description",
))
MEASURES = ("measure_skim", "measure_shore", "measure_bio",
            "measure_disperse", "measure_burn")
COLUMNS = ("incident_id", "notification_date", "name", "location",
           "latitude", "longitude", "threat", "tags", "commodity",
           "potential_release_gallons_max", "response_posts",
           "measure_skim", "measure_shore", "measure_bio",
           "measure_disperse", "measure_burn", "description",
           "publisher_url", "coordinate_semantics")
POSITION_SCOPE = ("NOAA response incident reference coordinate, potentially "
                  "approximate; not a property boundary or affected footprint")


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def retrieve(session, target):
    """HTTPS-only bounded download; discard any incomplete file before retry."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".part")
    for attempt in range(4):
        try:
            with session.get(URL, stream=True, timeout=(20, 90),
                             allow_redirects=True,
                             headers={"User-Agent": "Pharm3r-FacilityRisk-IncidentNews/1.0",
                                      "Accept": "text/csv,application/octet-stream",
                                      "Accept-Encoding": "identity"}) as reply:
                reply.raise_for_status()
                address = urlsplit(reply.url)
                if address.scheme != "https" or address.hostname != "incidentnews.noaa.gov":
                    raise ValueError("IncidentNews redirected outside its official publisher")
                size = 0
                with temp.open("wb") as stream:
                    for chunk in reply.iter_content(chunk_size=512 * 1024):
                        if chunk:
                            size += len(chunk)
                            if size > MAX_BYTES:
                                raise ValueError("IncidentNews export exceeds source-size safety limit")
                            stream.write(chunk)
                if size < 100:
                    raise ValueError("IncidentNews export is unexpectedly empty")
                if temp.open("rb").read(1024).lstrip().lower().startswith(b"<!doctype html"):
                    raise ValueError("IncidentNews returned HTML instead of the official CSV")
            temp.replace(target)
            return target
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if attempt == 3 or (status is not None and status != 429 and status < 500):
                raise
            delay = 2 ** attempt
            print(f"IncidentNews transient transport error; retry {attempt+1}/4 "
                  f"after {delay}s", file=sys.stderr, flush=True)
            time.sleep(delay)
        finally:
            temp.unlink(missing_ok=True)
    raise RuntimeError("IncidentNews source download exhausted retries")


def _integer(value, label, *, missing=""):
    raw = str(value or "").strip()
    if not raw:
        return missing
    n = int(raw)
    if n < 0 or n > 10**12:
        raise ValueError(f"Invalid IncidentNews {label}")
    return str(n)


def _float(value, label, *, bound=None):
    raw = str(value or "").strip()
    if not raw:
        return ""
    n = float(raw)
    if not math.isfinite(n) or (bound is not None and not -bound <= n <= bound):
        raise ValueError(f"Invalid IncidentNews {label}")
    if label == "potential release" and n < 0:
        raise ValueError("Negative potential release")
    return str(n)


def _coordinate(value, bound):
    """Invalid/approximate upstream position cannot become a property point."""
    raw=str(value or "").strip()
    if not raw:
        return ""
    try:
        number=float(raw)
        if math.isfinite(number) and -bound <= number <= bound:
            return str(number)
    except (ValueError,OverflowError):
        pass
    # Keep the original source bytes unchanged in the raw archived file.
    # Invalid/sentinel coordinates are *missing*, never silently clamped.
    return ""


def _flag(value):
    raw = str(value or "").strip()
    if raw not in ("", "0", "1"):
        raise ValueError("Invalid IncidentNews reported response-measure flag")
    return raw


def _date(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError as exc:
        raise ValueError("Invalid IncidentNews response-notification date") from exc


def _text(value, limit=4000):
    return str(value or "").replace("\v", "\n").strip()[:limit]


def normalize(source, output, *, minimum_rows=100):
    """Streaming normalization; fail the entire stage on wrong schema/IDs."""
    count = 0
    geocoded = 0
    missing_dates = 0
    excluded_coordinate_rows = 0
    classes = Counter()
    dates = []
    seen = set()
    temp = Path(str(output)+".part")
    try:
        with Path(source).open("r", encoding="utf-8-sig", newline="") as inp, \
                gzip.open(temp, "wt", encoding="utf-8", newline="") as out:
            reader = csv.DictReader(inp)
            observed=list(reader.fieldnames or [])
            missing=sorted(RAW_REQUIRED-set(observed))
            # The current publisher CSV omits the documented is_ prefix.
            # Accept both exact field-name variants, but never assume the
            # measure is false if neither official spelling exists.
            measure_columns={name:(name if name in observed else "is_"+name)
                             for name in MEASURES}
            missing += [name for name,field in measure_columns.items()
                        if field not in observed]
            if missing:
                raise ValueError("Official IncidentNews CSV columns changed; "+
                    "missing="+repr(missing)+"; "+
                    "observed_header="+repr(observed[:45]))
            writer = csv.DictWriter(out, fieldnames=COLUMNS)
            writer.writeheader()
            for raw in reader:
                incident_id = _integer(raw.get("id"), "incident identifier")
                if not incident_id or incident_id == "0" or incident_id in seen:
                    raise ValueError("Missing or duplicate IncidentNews incident identifier")
                seen.add(incident_id)
                when = _date(raw.get("open_date"))
                if not when:
                    missing_dates += 1
                else:
                    dates.append(when)
                latitude = _coordinate(raw.get("lat"), 90)
                longitude = _coordinate(raw.get("lon"), 180)
                if bool(latitude) != bool(longitude):
                    latitude = longitude = ""
                if latitude and longitude:
                    geocoded += 1
                elif str(raw.get("lat") or "").strip() or str(raw.get("lon") or "").strip():
                    excluded_coordinate_rows += 1
                threat = _text(raw.get("threat"), 80)
                if threat not in ("Oil", "Chemical", "Other", ""):
                    # New publisher categories require review, not silent mapping.
                    raise ValueError(f"Unexpected official IncidentNews threat category: {threat}")
                threat = threat or "Unspecified"
                classes[threat] += 1
                measure_flags = [_flag(raw.get(measure_columns[k])) for k in MEASURES]
                writer.writerow(dict(zip(COLUMNS, (
                    incident_id, when, _text(raw.get("name"), 500),
                    _text(raw.get("location"), 500),
                    latitude, longitude, threat, _text(raw.get("tags"), 1500),
                    _text(raw.get("commodity"), 1000),
                    _float(raw.get("max_ptl_release_gallons"), "potential release"),
                    _integer(raw.get("posts"), "publisher posts"),
                    *measure_flags, _text(raw.get("description"), 30000),
                    DOCS, POSITION_SCOPE
                ))))
                count += 1
        if count < minimum_rows:
            raise ValueError(f"IncidentNews source too small: {count} < {minimum_rows}")
        temp.replace(output)
        return {"records": count, "coordinate_records": geocoded,
                "excluded_coordinate_rows": excluded_coordinate_rows,
                "missing_notification_dates": missing_dates,
                "earliest_notification_date": min(dates) if dates else None,
                "latest_notification_date": max(dates) if dates else None,
                "threat_counts": dict(sorted(classes.items()))}
    finally:
        temp.unlink(missing_ok=True)


def validate(output, manifest):
    if sha256(output) != manifest.get("normalized_sha256"):
        raise ValueError("IncidentNews normalized checksum mismatch")
    found = Counter()
    geo = 0
    with gzip.open(output, "rt", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise ValueError("IncidentNews normalized schema drift")
        seen = set()
        for row in reader:
            if row["incident_id"] in seen:
                raise ValueError("IncidentNews duplicate ID in normalized export")
            seen.add(row["incident_id"])
            found[row["threat"]] += 1
            if row["latitude"] and row["longitude"]:
                geo += 1
    if dict(sorted(found.items())) != manifest.get("threat_counts") or \
            sum(found.values()) != manifest.get("records") or \
            geo != manifest.get("coordinate_records"):
        raise ValueError("IncidentNews normalized row counts disagree with source manifest")
    return True


def summary(manifest, run_url):
    return {
        "schema_version": "1.0", "source": "NOAA IncidentNews Selected Spills",
        "state": "staged_source_artifact", "records": manifest["records"],
        "checked_at": manifest["retrieved_at"],
        "scope": "Selected NOAA scientific-response spill/chemical incidents, not all reported spills",
        "details": ("Official NOAA OR&R selected incidents; location reference points may be "
                    "approximate. Potential release is NOT actual spilled volume, property damage "
                    "or insured loss. Private indexed source not durably hosted."),
        "documentation": DOCS, "artifact_run_url": run_url,
        "manifest_sha256": manifest["normalized_sha256"],
        "coordinate_records": manifest["coordinate_records"],
        "threat_counts": manifest["threat_counts"],
    }


def stage(raw, normalized, manifest_path, public_path=None, *, session=None,
          minimum_rows=100, run_url=""):
    session = session or requests.Session()
    retrieve(session, raw)
    Path(normalized).parent.mkdir(parents=True, exist_ok=True)
    info = normalize(raw, normalized, minimum_rows=minimum_rows)
    manifest = {
        "schema_version": "1.0",
        "publisher": PUBLISHER,
        "source_url": URL, "documentation": DOCS,
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "original_sha256": sha256(raw),
        "normalized_sha256": sha256(normalized),
        "original_bytes": Path(raw).stat().st_size,
        "normalized_columns": list(COLUMNS),
        "complete_publisher_snapshot": True,
        **info,
        "scope_note": "Selected NOAA OR&R response cases only; not a census of all releases",
    }
    validate(normalized, manifest)
    Path(manifest_path).parent.mkdir(parents=True, exist_ok=True)
    Path(manifest_path).write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    if public_path is not None:
        Path(public_path).parent.mkdir(parents=True, exist_ok=True)
        Path(public_path).write_text(json.dumps(summary(manifest, run_url), indent=2)+"\n", encoding="utf-8")
    return manifest


def main():
    p = argparse.ArgumentParser(description="Stage official NOAA IncidentNews selective spill source")
    p.add_argument("--raw", type=Path, default=Path("data/incidentnews/incidents.csv"))
    p.add_argument("--output", type=Path, default=Path("data/incidentnews/incidents.csv.gz"))
    p.add_argument("--manifest", type=Path, default=Path("data/incidentnews/manifest.json"))
    p.add_argument("--summary", type=Path, default=Path("web/ingestion/noaa-incidentnews.json"))
    p.add_argument("--min-rows", type=int, default=100)
    args = p.parse_args()
    import os
    repo = os.environ.get("GITHUB_REPOSITORY", "jhennessy-pharm3r/FacilityTest")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    result = stage(args.raw, args.output, args.manifest, args.summary,
                   minimum_rows=args.min_rows,
                   run_url=(f"https://github.com/{repo}/actions/runs/{run_id}" if run_id else ""))
    print(json.dumps({"source": URL, "rows": result["records"],
                      "coordinate_records": result["coordinate_records"],
                      "threat_counts": result["threat_counts"]}, indent=2))


if __name__ == "__main__":
    main()
