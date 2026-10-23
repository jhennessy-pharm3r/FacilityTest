"""Normalize the real multi-table NRC annual FOIA workbook by native SEQNOS.

NRC calls are initially unverified notifications. A call is not a confirmed
incident, an affected insured property, or an insurance loss.
"""
from __future__ import annotations
import csv
import gzip
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from openpyxl import load_workbook
try:
    from scripts.industrial_incident_io import gzip_csv_writer
except ModuleNotFoundError:  # direct scripts/ entrypoint
    from industrial_incident_io import gzip_csv_writer
try:
    from scripts.build_industrial_incidents import as_date, digest
except ModuleNotFoundError:  # direct scripts/probe_lane_c_sources.py execution
    from build_industrial_incidents import as_date, digest

SHEETS = ("CALLS", "INCIDENT_COMMONS", "INCIDENT_DETAILS")
FIELDS = ("source_id", "incident_date", "date_precision", "company_as_reported",
          "incident_location_text", "incident_city", "incident_state",
          "latitude", "longitude", "coordinate_semantics",
          "reported_fatalities", "reported_injuries", "reported_damage_usd",
          "reported_evacuated", "fire_involved", "report_status",
          "site_link_status", "source_document")
SOURCE = "https://nrc.uscg.mil/FOIAFiles/CY25.xlsx"

def read_table(book, sheet, *, child=False):
    """Read NRC source-native SEQNOS without arbitrarily choosing ambiguous children.

    An INCIDENT_COMMONS duplicate is ambiguous incident identity and fails closed.
    A duplicate CALLS/INCIDENT_DETAILS key excludes child enrichment only, while
    preserving the incident master record. Keep exact rejected counts in manifest.
    """
    ws = book[sheet]
    rows = ws.iter_rows(values_only=True)
    header = [str(x or "").strip() for x in next(rows)]
    if "SEQNOS" not in header:
        raise ValueError(f"{sheet} missing native SEQNOS")
    table = {}
    ambiguous = set()
    blank_keys = 0
    observed = 0
    duplicate_rows = 0
    for index, values in enumerate(rows, 2):
        if not any(x is not None for x in values):
            continue
        observed += 1
        data = dict(zip(header, values))
        key = str(data.get("SEQNOS") or "").strip()
        if not key:
            blank_keys += 1
            continue
        if key in table or key in ambiguous:
            duplicate_rows += 1
            ambiguous.add(key)
            continue
        table[key] = data
    if not child and (blank_keys or duplicate_rows):
        raise ValueError(f"{sheet} master report identity invalid: blank={blank_keys}, duplicate={duplicate_rows}")
    # A duplicated child ID has no deterministic one-to-one row. Never choose
    # either version for reported injuries, fatalities, property damage, etc.
    for key in ambiguous:
        table.pop(key, None)
    return table, {
        "observed_rows": observed,
        "valid_unambiguous_native_ids": len(table),
        "blank_native_key_rows": blank_keys,
        "duplicate_native_key_rows": duplicate_rows,
        "ambiguous_native_ids": len(ambiguous),
    }

def dms(degree, minute, second, quad, *, latitude):
    if any(x is None or str(x).strip() == "" for x in (degree, minute, second, quad)):
        return ""
    try:
        d, m, s = map(float, (degree, minute, second))
        if not all(math.isfinite(x) for x in (d, m, s)):
            return ""
        if d < 0 or not 0 <= m < 60 or not 0 <= s < 60:
            return ""
        p = str(quad).strip().upper()
        if p not in (("N", "NORTH", "S", "SOUTH") if latitude else ("E", "EAST", "W", "WEST")):
            return ""
        value = d + m / 60 + s / 3600
        if value > (90 if latitude else 180):
            return ""
        if p[0] in ("S", "W"):
            value *= -1
        return str(round(value, 7))
    except (ValueError, TypeError):
        return ""

def reported_number(value):
    if value is None or str(value).strip() == "":
        return ""
    try:
        number = float(str(value).replace(",", "").replace("$", ""))
        if not math.isfinite(number) or number < 0:
            return ""
        return str(number)
    except ValueError:
        return ""

def stage_nrc(raw, output, manifest, *, year, minimum_rows=1000):
    raw, output, manifest = map(Path, (raw, output, manifest))
    temp = Path(str(output) + ".part")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    book = load_workbook(raw, read_only=True, data_only=True)
    try:
        for sheet in SHEETS:
            if sheet not in book.sheetnames:
                raise ValueError("NRC workbook missing required " + sheet)
        calls, call_quality = read_table(book, "CALLS", child=True)
        common, common_quality = read_table(book, "INCIDENT_COMMONS")
        details, detail_quality = read_table(book, "INCIDENT_DETAILS", child=True)
        ids = set(common)
        missing_call_links = len(ids - set(calls))
        missing_detail_links = len(ids - set(details))
        orphan_call_rows = len(set(calls) - ids)
        orphan_detail_rows = len(set(details) - ids)
        geo, bad_dates = 0, 0
        missing_raw_dms, invalid_raw_dms = 0, 0
        state_counts = Counter()
        dates = []
        with gzip_csv_writer(temp) as stream:
            writer = csv.DictWriter(stream, FIELDS)
            writer.writeheader()
            for seqno, row in sorted(common.items(), key=lambda item: item[0]):
                call = calls.get(seqno, {})
                detail = details.get(seqno, {})
                try:
                    when, precision = as_date(row.get("INCIDENT_DATE_TIME"))
                except ValueError:
                    when, precision = "", "missing_or_invalid"
                    bad_dates += 1
                if when:
                    dates.append(when)
                state_counts[str(row.get("LOCATION_STATE") or "").strip() or "<missing>"] += 1
                dms_parts = tuple(row.get(part) for part in (
                    "LAT_DEG","LAT_MIN","LAT_SEC","LAT_QUAD",
                    "LONG_DEG","LONG_MIN","LONG_SEC","LONG_QUAD"))
                no_raw_dms = any(value is None or str(value).strip()=="" for value in dms_parts)
                lat = dms(row.get("LAT_DEG"), row.get("LAT_MIN"), row.get("LAT_SEC"),
                          row.get("LAT_QUAD"), latitude=True)
                lon = dms(row.get("LONG_DEG"), row.get("LONG_MIN"), row.get("LONG_SEC"),
                          row.get("LONG_QUAD"), latitude=False)
                if not lat or not lon or (float(lat) == 0 and float(lon) == 0):
                    lat = lon = ""
                if lat:
                    geo += 1
                elif no_raw_dms:
                    missing_raw_dms += 1
                else:
                    invalid_raw_dms += 1
                writer.writerow(dict(zip(FIELDS, (
                    seqno, when, precision, str(call.get("RESPONSIBLE_COMPANY") or "").strip(),
                    str(row.get("INCIDENT_LOCATION") or "").strip(),
                    str(row.get("LOCATION_NEAREST_CITY") or "").strip(),
                    str(row.get("LOCATION_STATE") or "").strip(),
                    lat, lon,
                    "source_reported_DMS_approximate_not_property_geometry" if lat
                    else "missing_or_invalid_publisher_DMS",
                    reported_number(detail.get("NUMBER_FATALITIES")),
                    reported_number(detail.get("NUMBER_INJURED")),
                    reported_number(detail.get("DAMAGE_AMOUNT")),
                    reported_number(detail.get("NUMBER_EVACUATED")),
                    str(detail.get("FIRE_INVOLVED") or "").strip(),
                    "NRC_initial_notification_unverified", "candidate_only_not_matched",
                    f"https://nrc.uscg.mil/FOIAFiles/CY{year%100:02d}.xlsx"
                ))))
        if len(ids) < minimum_rows:
            raise ValueError("NRC cohort fails expected minimum verified-row threshold")
        temp.replace(output)
        result = {
            "state": "STAGED", "source": "USCG NRC Annual FOIA",
            "year": year, "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "source_url": f"https://nrc.uscg.mil/FOIAFiles/CY{year%100:02d}.xlsx",
            "raw_sha256": digest(raw), "normalized_sha256": digest(output),
            "nrc_reports": len(ids), "source_calls": len(calls),
            "source_commons": len(common), "source_details": len(details),
            "observed_sheet_rows": {
                "CALLS": call_quality, "INCIDENT_COMMONS": common_quality,
                "INCIDENT_DETAILS": detail_quality
            },
            "missing_cross_table_links": missing_call_links + missing_detail_links,
            "missing_calls_child_enrichment": missing_call_links,
            "missing_details_child_enrichment": missing_detail_links,
            "orphan_calls_native_ids": orphan_call_rows,
            "orphan_details_native_ids": orphan_detail_rows,
            "child_rows_dropped_as_ambiguous_or_blank": {
                "CALLS": call_quality["blank_native_key_rows"] + call_quality["duplicate_native_key_rows"],
                "INCIDENT_DETAILS": detail_quality["blank_native_key_rows"] + detail_quality["duplicate_native_key_rows"]
            },
            "coordinate_records": geo, "missing_coordinates": len(ids) - geo,
            "invalid_or_missing_incident_dates": bad_dates,
            "earliest_incident_date": min(dates) if dates else None,
            "latest_incident_date": max(dates) if dates else None,
            "state_counts": dict(sorted(state_counts.items())),
            "missing_raw_coordinate_components": missing_raw_dms,
            "invalid_or_sentinel_publisher_coordinates": invalid_raw_dms,
            "accepted_rows": len(ids), "rejected_rows": 0,
            "evidence_status": "unverified_report_not_confirmed_loss",
            "physical_facility_matches": 0, "deployment": "NOT_DEPLOYED",
            "caveat": "Coordinates and severity are reported values, not corroborated site exposure or insured loss."
        }
        manifest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        validate(output, result)
        return result
    finally:
        book.close()
        temp.unlink(missing_ok=True)

def validate(path, manifest):
    if digest(path) != manifest["normalized_sha256"]:
        raise ValueError("NRC normalized SHA mismatch")
    count, geo = 0, 0
    seen = set()
    with gzip.open(path, "rt", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError("NRC output fields changed")
        for row in reader:
            if not row["source_id"] or row["source_id"] in seen:
                raise ValueError("NRC missing/duplicate native SEQNOS")
            seen.add(row["source_id"])
            geo += bool(row["latitude"] and row["longitude"])
            if row["site_link_status"] != "candidate_only_not_matched":
                raise ValueError("NRC source row promoted to physical site")
            count += 1
    if count != manifest["accepted_rows"] or geo != manifest["coordinate_records"]:
        raise ValueError("NRC output counts disagree with manifest")
    return True
