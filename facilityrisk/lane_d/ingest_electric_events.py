"""Ingest official EIA Electric Power Monthly Tables B.1/B.2 (DOE-417 summaries).

These are reported power-system disturbance observations, not claims, confirmed
facility outages, or an exhaustive list of customer interruptions. Stdlib only.
"""
from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone

ROOT = "https://www.eia.gov/electricity/monthly/epm_table_grapher.php?t=epmt_"
SOURCE = {"b1": {"url": ROOT + "b_1", "year": 2024, "scope": "YEAR_TO_DATE_2024_PARTIAL"},
          "b2": {"url": ROOT + "b_2", "year": 2023, "scope": "ANNUAL_2023"}}
HEADERS = (
    "year", "month", "eventdateandtime", "restorationdateandtime",
    "duration", "utilitypowerpool", "nercregion", "areaaffected",
    "typeofdisturbance", "lossmegawatts", "numberofcustomersaffected",
)


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def digest(data):
    return hashlib.sha256(data).hexdigest()


class HtmlTables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.tables = []
        self.table_rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            if self.depth == 0:
                self.table_rows = []
            self.depth += 1
        elif self.depth and tag == "tr":
            self.row = []
        elif self.depth and tag in ("td", "th") and self.row is not None:
            self.cell = []
        elif self.cell is not None and tag == "br":
            self.cell.append(" ")

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(re.sub(r"\s+", " ", " ".join(self.cell)).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None and self.depth:
            if self.row:
                self.table_rows.append(self.row)
            self.row = None
        elif tag == "table" and self.depth:
            self.depth -= 1
            if self.depth == 0:
                self.tables.append(self.table_rows)
                self.table_rows = []


def parse_events(html_bytes, table):
    if table not in SOURCE:
        raise ValueError("Unsupported official EIA table")
    source = SOURCE[table]
    html = html_bytes.decode("utf-8-sig", errors="replace")
    parsed = HtmlTables()
    parsed.feed(html)
    candidates = []
    for rows in parsed.tables:
        for n, row in enumerate(rows):
            names = [norm(c) for c in row]
            if len(names) >= len(HEADERS) and all(h in names for h in HEADERS):
                candidates.append((rows, n, [names.index(h) for h in HEADERS]))
    if len(candidates) != 1:
        raise ValueError("Expected one official event table, found " + str(len(candidates)))
    rows, header_index, indices = candidates[0]
    if str(source["year"]) not in html:
        raise ValueError("Expected reporting year absent from publisher page")
    accepted, rejected = [], []
    for i, original in enumerate(rows[header_index + 1:], start=header_index + 2):
        fields = [original[col].strip() if col < len(original) else "" for col in indices]
        year, month, started, restored, duration, utility, nerc, area, category, mw, customers = fields
        why = None
        if year != str(source["year"]):
            why = "incorrect_or_missing_reporting_year"
        elif not re.fullmatch(r"(?:[1-9]|1[0-2])", month):
            why = "invalid_month"
        elif not started or not utility or not category:
            why = "missing_date_utility_or_event_type"
        if why:
            rejected.append({"table": table, "table_row_1based": i, "reason": why,
                             "raw_columns": original, "row_sha256": digest(json.dumps(original).encode())})
            continue
        # EIA's table has no native event ID; this is an expressly derived source-row ID.
        composite = [source["url"], table, i, fields]
        row_key = digest(json.dumps(composite, ensure_ascii=False).encode("utf-8"))
        def nvalue(s):
            return int(s.replace(",", "")) if re.fullmatch(r"[0-9][0-9,]*", s) else None
        accepted.append({
            "source": "EIA_EPM_DOE417_SUMMARY",
            "publisher": "U.S. Energy Information Administration",
            "source_url": source["url"],
            "source_table": "EPM_" + table.upper(),
            "coverage": source["scope"],
            "report_year": int(year), "source_table_row_1based": i,
            "source_event_id": None, "source_has_native_event_id": False,
            "derived_source_row_key": row_key,
            "row_sha256": digest(json.dumps(original, ensure_ascii=False).encode("utf-8")),
            "reported_start": started, "reported_restored": restored,
            "reported_duration": duration, "reported_utility": utility,
            "reported_nerc_region": nerc, "reported_area": area,
            "reported_disturbance_type": category,
            "reported_loss_mw": mw,
            "reported_customers_affected": customers,
            "customers_affected_number": nvalue(customers),
            "loss_mw_number": nvalue(mw),
            "source_description": "Major disturbances and unusual occurrences (DOE-417 derived EIA table)",
            "reported_service_loss_category": ("loss of electric service" in category.lower()),
            "facility_match_status": "NOT_ASSESSED",
            "site_specific_outage_verified": False,
            "business_interruption_verified": False,
            "claims_loss_verified": False,
            "raw_columns": original,
        })
    if not accepted:
        raise ValueError("No event rows accepted from official EIA table " + table)
    if len(accepted) + len(rejected) != len(rows) - header_index - 1:
        raise RuntimeError("EIA disturbance source-row reconciliation failed")
    return accepted, rejected, [rows[header_index][i] for i in indices]


def build_index(output, rows):
    path = output / "events_staging.sqlite"
    con = sqlite3.connect(path)
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS source_events (
            derived_source_row_key TEXT PRIMARY KEY, report_year INTEGER NOT NULL,
            reported_start TEXT, utility TEXT, reported_area TEXT,
            reported_disturbance_type TEXT, original_row_json TEXT NOT NULL
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_events_year_start ON source_events (report_year, reported_start)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_events_utility ON source_events (utility)")
        con.executemany(
            "INSERT INTO source_events VALUES (?,?,?,?,?,?,?)",
            [(r["derived_source_row_key"], r["report_year"], r["reported_start"],
              r["reported_utility"], r["reported_area"], r["reported_disturbance_type"],
              json.dumps(r["raw_columns"], ensure_ascii=False)) for r in rows],
        )
        con.commit()
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Disturbance SQLite integrity failure")
        count = con.execute("SELECT COUNT(*) FROM source_events").fetchone()[0]
        if count != len(rows):
            raise RuntimeError("Disturbance staged count mismatch")
        return count
    finally:
        con.close()


def run(table, input_html, output):
    if table not in SOURCE:
        raise ValueError("Only vetted EPM B.1 or B.2 sources are supported")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    data = Path(input_html).read_bytes()
    rows, rejected, columns = parse_events(data, table)
    for filename, records in (("events.jsonl", rows), ("rejected.jsonl", rejected)):
        with (output / filename).open("w", encoding="utf-8") as target:
            for row in records:
                target.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    stage_count = build_index(output, rows)
    src = SOURCE[table]
    manifest = {
        "source": "EIA_EPM_DOE417_SUMMARY", "source_url": src["url"],
        "publisher": "U.S. Energy Information Administration", "derived_from": "DOE-417",
        "table": table, "reporting_year": src["year"], "coverage": src["scope"],
        "source_retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "source_html_sha256": digest(data), "source_html_bytes": len(data),
        "source_id_policy": "No native event ID in EPM table; derived source-row key, source URL, table and raw cells retained.",
        "column_headers": columns, "accepted_source_rows": len(rows),
        "rejected_source_rows": len(rejected),
        "rejection_reasons": dict(Counter(r["reason"] for r in rejected)),
        "source_rows_reconciled": len(rows) + len(rejected),
        "rows_with_reported_service_loss_category": sum(r["reported_service_loss_category"] for r in rows),
        "rows_with_numeric_customers": sum(r["customers_affected_number"] is not None for r in rows),
        "rows_without_restoration_timestamp": sum(r["reported_restored"].startswith(".") or not r["reported_restored"] for r in rows),
        "indexed_local_staging": stage_count,
        "indexed_durable_backend": 0, "verified_facility_outages": 0,
        "verified_business_interruption_losses": 0, "deployed": 0,
        "data_state": "SOURCE_NORMALIZED_INDEXED_LOCALLY_ONLY",
        "caveats": [
            "EPM is an EIA-compiled subset of DOE-417 reporting, not a customer outage census.",
            "Customers affected are preliminary estimates per EIA note.",
            "Not all reported incidents are an actual power outage.",
            "Area named in an incident does not establish a specific property's outage.",
            "Unknown restoration is not zero downtime; customers counts do not equal insured losses.",
            "Table B.1 currently displays a partial 2024 period; not a full-year event denominator.",
        ],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--table", choices=list(SOURCE), required=True)
    p.add_argument("--html", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(run(args.table, args.html, args.output), indent=2))


if __name__ == "__main__":
    main()
