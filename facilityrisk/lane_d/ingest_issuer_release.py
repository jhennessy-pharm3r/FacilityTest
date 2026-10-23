"""Lane D: first-party public issuer evidence for named operational interruptions.

Unlike a SEC accession-backed filing, a company press release is a *dated issuer
statement*. It does not verify power loss, property insurance coverage, claim
payment, or a risk score. The issuer event is de-duplicated by a curated event
key; each publication retains its own immutable SHA-256 and URL.
"""
from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sqlite3
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

USER_AGENT = "FacilityTest Lane D public source provenance validation (https://github.com/jhennessy-pharm3r/FacilityTest/issues/73)"
SOURCE_RECORDS = [
    {
        "id": "baxter-north-cove-2024-09-29",
        "event_key": "baxter-north-cove-helene-2024",
        "publisher": "Baxter International Inc.",
        "issuer_cik": "10456",
        "release_date": "September 29, 2024",
        "industry": "medical products manufacturing",
        "source_url": "https://investor.baxter.com/investors/events-and-news/news/press-release-details/2024/Baxter-Provides-Update-on-North-Cove-N.C.-Facility-and-Hurricane-Helene-Relief-Plans-for-Community/default.aspx",
        "expected_title": "Baxter Provides Update on North Cove",
        "event_terms": ("Hurricane Helene",),
        "site_terms": ("North Cove",),
        "effect_terms": ("closed for production", "disruption", "flooding"),
    },
    {
        "id": "baxter-north-cove-2024-11-08",
        "event_key": "baxter-north-cove-helene-2024",
        "publisher": "Baxter International Inc.",
        "issuer_cik": "10456",
        "release_date": "November 8, 2024",
        "industry": "medical products manufacturing",
        "source_url": "https://investor.baxter.com/investors/events-and-news/news/press-release-details/2024/Baxter-Reports-Third-Quarter-2024-Results/default.aspx",
        "expected_title": "Baxter Reports Third-Quarter 2024 Results",
        "event_terms": ("Hurricane Helene",),
        "site_terms": ("North Cove",),
        "effect_terms": ("production shutdown", "production has now restarted", "disruption"),
    },
    {
        "id": "baxter-north-cove-2025-02",
        "event_key": "baxter-north-cove-helene-2024",
        "publisher": "Baxter International Inc.",
        "issuer_cik": "10456",
        "release_date": "February 20, 2025",
        "industry": "medical products manufacturing",
        "source_url": "https://investor.baxter.com/investors/events-and-news/news/press-release-details/2025/Baxter-Reports-Fourth-Quarter-and-Full-Year-2024-Results/default.aspx",
        "expected_title": "Baxter Reports Fourth-Quarter and Full-Year 2024 Results",
        "event_terms": ("Hurricane Helene",),
        "site_terms": ("North Cove",),
        "effect_terms": ("production shutdown", "all 10", "restarted"),
    },
]
ALLOWED_SOURCE_HOSTS = {"investor.baxter.com"}
MAX_HTML_BYTES = 5_000_000


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ReadableHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sections: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.hidden += 1
        elif not self.hidden and tag in ("p", "li", "h1", "h2", "h3", "br", "div", "td"):
            self.sections.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.hidden = max(0, self.hidden - 1)
        elif not self.hidden and tag in ("p", "li", "h1", "h2", "h3", "br", "div", "td"):
            self.sections.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.sections.append(data)

    def text(self):
        return re.sub(r"\s+", " ", "".join(self.sections)).strip()


def validate_case(case: dict):
    url = case["source_url"]
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_SOURCE_HOSTS:
        raise ValueError("Source host not an approved first-party issuer domain")
    if not re.fullmatch(r"[0-9]{1,10}", case["issuer_cik"]):
        raise ValueError("Invalid issuer CIK")
    if not re.fullmatch(r"[a-z0-9-]{12,120}", case["id"]):
        raise ValueError("Invalid publication identity")
    return case


def extract_issuer_forecast(case: dict, content: str):
    """A specifically anchored 2024-Q4 issuer SALES FORECAST, never a loss or paid claim.

    For the Baxter Nov 8 2024 release, require the original source text to
    assert a forecast and exact amount. It is a forecast for the whole COMPANY,
    not actual site damage, insured BI loss or realized revenue.
    """
    if case["id"] != "baxter-north-cove-2024-11-08":
        return None
    matches=re.finditer(
        r"as a result of (?:the )?hurricane.{0,350}?fourth-quarter sales.{0,170}?approximately\s*\$200\s*million",
        content, flags=re.I,
    )
    for match in matches:
        excerpt=content[max(0,match.start()-90):min(len(content),match.end()+160)]
        if "negatively impacted" not in excerpt.lower():
            continue
        return {
            "published_as_of_date":"2024-11-08",
            "issuer":"Baxter International Inc.",
            "scope":"TOTAL_COMPANY_Q4_2024",
            "classification":"PROSPECTIVE_COMPANY_WIDE_SALES_DOWNSIDE_GUIDANCE",
            "original_amount_currency":"USD",
            "as_reported_approximate_amount":200000000,
            "estimated_not_realized":True,
            "not_facility_specific":True,
            "not_covered_loss":True,
            "not_paid_insurance":True,
            "matched_source_excerpt_sha256":digest(excerpt.encode("utf-8")),
            "source_snippet_for_review":excerpt[:300],
        }
    return None


def inspect_issuer_html(case: dict, data: bytes, actual_url: str, http_code: int):
    case = validate_case(case)
    if http_code != 200 or actual_url != case["source_url"]:
        raise ValueError("Unexpected publisher HTTPS response or redirect")
    if not (150 < len(data) < MAX_HTML_BYTES):
        raise ValueError("Source bytes out of accepted bounds")
    if b"<html" not in data[:5000].lower():
        raise ValueError("Expected publisher HTML document")
    parsed = ReadableHTML()
    parsed.feed(data.decode("utf-8-sig", errors="replace"))
    text = parsed.text()
    if len(text) < 500:
        raise ValueError("Issuer page contains too little visible text")
    if case["expected_title"].lower() not in text.lower():
        raise ValueError("Publisher title identity not found in downloaded document")
    if case["release_date"].lower() not in text.lower():
        raise ValueError("Publication date not corroborated by source document")
    matches = []
    for phrase in case["event_terms"]:
        for occurrence in re.finditer(re.escape(phrase), text, re.I):
            start = max(0, occurrence.start() - 350)
            end = min(len(text), occurrence.end() + 1650)
            window = text[start:end]
            matched_sites = [term for term in case["site_terms"] if term.lower() in window.lower()]
            matched_effects = [term for term in case["effect_terms"] if term.lower() in window.lower()]
            if matched_sites and matched_effects:
                matches.append((occurrence.start(), phrase, matched_sites, matched_effects, window))
    if not matches:
        raise ValueError("No co-located event, named site and operations-interruption evidence")
    pos, event, site, effect, excerpt = matches[0]
    key = digest((case["source_url"] + "\n" + digest(data)).encode("utf-8"))
    return {
        "source": "ISSUER_PRIMARY_RELEASE",
        "publisher": case["publisher"],
        "source_url": case["source_url"],
        "source_id": case["id"],
        "underlying_event_key": case["event_key"],
        "industry": case["industry"],
        "issuer_cik": case["issuer_cik"],
        "release_date": case["release_date"],
        "publication_sha256": digest(data),
        "publication_bytes": len(data),
        "evidence_row_key": key,
        "source_text_sha256": digest(text.encode("utf-8")),
        "event_anchor": event,
        "reported_site_anchors": site,
        "operational_effect_anchors": effect,
        "evidence_excerpt_hash": digest(excerpt.encode("utf-8")),
        # Short bounded excerpt for reviewer; publisher original stays available by URL.
        "evidence_excerpt": excerpt[:350],
        "source_authentication": "HTTPS_FIRST_PARTY_200_EXACT_URL",
        "issuer_reports_operational_interruption": True,
        "independently_verified_site_identity": False,
        "electrical_power_outage_verified": False,
        "actual_downtime_hours_verified": False,
        "reported_financial_impact_amount": None,
        "issuer_prospective_sales_guidance": extract_issuer_forecast(case, text),
        "insured_business_interruption_loss_verified": False,
        "claims_paid_verified": False,
        "record_status": "ISSUER_REPORTED_SITE_INTERRUPTION_REVIEW_ONLY",
    }


def fetch_case(case: dict, output: Path):
    case = validate_case(case)
    request = Request(case["source_url"], headers={
        "User-Agent": USER_AGENT, "Accept": "text/html",
    })
    with urlopen(request, timeout=45) as response:
        actual = response.geturl()
        code = response.status
        content = response.read(MAX_HTML_BYTES + 1)
    if len(content) > MAX_HTML_BYTES:
        raise ValueError("Response exceeds byte ceiling")
    record = inspect_issuer_html(case, content, actual, code)
    return record


def build_index(output: Path, entries: list[dict]):
    path = output / "issuer_evidence_staging.sqlite"
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS issuer_evidence (
            evidence_row_key TEXT PRIMARY KEY, source_id TEXT UNIQUE NOT NULL,
            source_url TEXT NOT NULL, publication_sha256 TEXT NOT NULL,
            event_key TEXT NOT NULL, issuer_cik TEXT NOT NULL, release_date TEXT NOT NULL,
            record_json TEXT NOT NULL
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_event_source ON issuer_evidence(event_key, release_date)")
        for r in entries:
            db.execute("INSERT INTO issuer_evidence VALUES (?,?,?,?,?,?,?,?)",
                       (r["evidence_row_key"],r["source_id"],r["source_url"],
                        r["publication_sha256"],r["underlying_event_key"],
                        r["issuer_cik"],r["release_date"],json.dumps(r, sort_keys=True)))
        db.commit()
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Issuer staging index failed integrity check")
        count = db.execute("SELECT count(*) FROM issuer_evidence").fetchone()[0]
        groups = db.execute("SELECT count(DISTINCT event_key) FROM issuer_evidence").fetchone()[0]
    if count != len(entries):
        raise RuntimeError("Indexed source documents did not reconcile")
    return count, groups


def run(output: Path, cases: list[dict] | None = None, min_success: int = 1):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    cases = SOURCE_RECORDS if cases is None else cases
    downloaded, failures, accepted = [], [], []
    for case in cases:
        try:
            record = fetch_case(case, output)
        except (ValueError, HTTPError, URLError, TimeoutError, OSError) as exc:
            failures.append({"source_id": case["id"], "source_url":case["source_url"],
                             "status": "BLOCKED_OR_REJECTED", "reason": str(exc)[:400]})
            continue
        accepted.append(record)
        downloaded.append({"source_id": case["id"], "url": case["source_url"],
                           "bytes": record["publication_bytes"], "sha256": record["publication_sha256"]})
    rows = output / "issuer_disclosures.jsonl"
    with rows.open("w", encoding="utf-8") as f:
        for record in accepted:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    staged, events = build_index(output, accepted)
    manifest = {
        "source": "FIRST_PARTY_ISSUER_RELEASES",
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "publisher_data_type": "PUBLIC_COMPANY_PRESS_RELEASE",
        "attempted": len(cases), "downloaded": len(downloaded),
        "normalized": len(accepted), "rejected_or_blocked": len(failures),
        "indexed_local_staging": staged, "distinct_named_underlying_events": events,
        "issuer_forecast_sales_guidance_observations": sum(r["issuer_prospective_sales_guidance"] is not None for r in accepted),
        "verified_realized_profit_loss_amounts": 0,
        "verified_paid_business_interruption_claims": 0,
        "downloaded_source_provenance": downloaded, "failed_sources": failures,
        "verified_insured_facility_ids": 0,
        "verified_meter_service_connections": 0,
        "verified_power_outages": 0,
        "verified_financial_claims": 0, "durable_backend_indexed": 0, "deployed": 0,
        "caveats": [
            "Company-origin releases support issuer statements; not independent site/meter verification",
            "Multiple dated publications about a single event are not separate loss events",
            "Financial outlook projections are not realized lost-profit or paid-insurance-claim amounts",
            "First-party storm/flood closure is not an independently verified electrical outage",
            "Local SQLite and GitHub Actions artifact remain nonproduction staging",
        ],
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if staged < min_success:
        raise RuntimeError("First-party source acceptance gate failed: "
                           + json.dumps(failures, ensure_ascii=False))
    return manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--min-success", type=int, default=1)
    args = p.parse_args()
    print(json.dumps(run(args.output, min_success=args.min_success), indent=2))


if __name__ == "__main__":
    main()
