"""Lane D: stage issuer-originated interruption statements without inventing site losses.

Consume a vetted catalog of SEC EDGAR source filings or user-supplied downloaded HTML.
Source excerpts are candidate financial evidence for independent review, NOT
claims/payouts, electricity outages or confirmed insured property damage.
"""
from __future__ import annotations
import argparse
import hashlib
from html.parser import HTMLParser
import json
import tomllib
import re
from pathlib import Path
from datetime import datetime, timezone
import urllib.parse
import urllib.request
from collections import Counter

SEC_PREFIX = "https://www.sec.gov/Archives/edgar/data/"
ACCESSION = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
CIK = re.compile(r"^[0-9]{1,10}$")
DEFAULT_CONTEXT = 2300
MAX_CONTEXT = 3200


def digest(content):
    return hashlib.sha256(content).hexdigest()


class FilingText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.part = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.hidden += 1
        if not self.hidden and tag in ("p", "div", "td", "tr", "li", "br", "h1", "h2", "h3"):
            self.part.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.hidden = max(0, self.hidden - 1)
        if not self.hidden and tag in ("p", "div", "td", "tr", "li", "br", "h1", "h2", "h3"):
            self.part.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.part.append(data)

    def text(self):
        return re.sub(r"\s+", " ", " ".join(self.part)).strip()


def validate_entry(entry):
    required = ("issuer_cik", "accession", "filename", "event_terms", "site_terms", "source_scope")
    if any(not entry.get(key) for key in required):
        raise ValueError("Catalog missing source identity, scope or evidence terms")
    cik = str(entry["issuer_cik"]).lstrip("0") or "0"
    accession = entry["accession"]
    if not CIK.fullmatch(cik) or not ACCESSION.fullmatch(accession):
        raise ValueError("Invalid issuer CIK or accession number")
    # SEC uses CIK folder, 18-digit accession without hyphens.
    filename = entry["filename"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.html?", filename, re.IGNORECASE):
        raise ValueError("Unsafe SEC archive filename")
    if any(not isinstance(value, str) or len(value.strip()) < 4 for value in entry["event_terms"] + entry["site_terms"]):
        raise ValueError("Empty or implausible evidence anchor")
    url = SEC_PREFIX + cik + "/" + accession.replace("-", "") + "/" + filename
    if entry.get("official_url") and entry["official_url"] != url:
        raise ValueError("Official SEC URL is inconsistent with issuer accession")
    return {**entry, "official_url": url, "issuer_cik": cik}


def nearby(content, item, span=DEFAULT_CONTEXT):
    return [(m.start(), content[max(0, m.start() - span):min(len(content), m.end() + span)])
            for m in re.finditer(re.escape(item), content, flags=re.I)]


def inspect_filing(entry, html_bytes):
    """Fail closed unless an actual EDGAR filing has locally corroborated anchors."""
    entry = validate_entry(entry)
    parser = FilingText()
    parser.feed(html_bytes.decode("utf-8", errors="replace"))
    text = parser.text()
    if len(text) < 150:
        raise ValueError("SEC filing body is too short to validate")
    if not re.search(r"\b(?:united states securities|form 10-q|form 10-k|quarterly report|annual report)\b", text, re.I):
        raise ValueError("SEC form/filing text evidence missing")
    best = None
    for event_term in entry["event_terms"]:
        for location, event_window in nearby(text, event_term, 1200):
            site_terms = [s for s in entry["site_terms"] if s.lower() in event_window.lower()]
            bi_context = any(term in event_window.lower() for term in (
                "business interruption", "operations", "reopen", "closed", "loss", "sales", "insurance"))
            score = int(bool(site_terms)) * 5 + int(bi_context) * 3 + len(event_window) / 100000
            if best is None or score > best[0]:
                best = (score, location, event_term, site_terms)
    if not best:
        raise ValueError("Event phrase absent from SEC filing")
    score, location, matched_event, sites = best
    # Source text is not a sourced numeric financial value. It is a bounded review excerpt.
    region = text[max(0, location - 700):min(len(text), location + 2400)]
    site_hit = any(s.lower() in region.lower() for s in entry["site_terms"])
    interruption_hit = "business interruption" in region.lower() or "disrupt" in region.lower()
    if not site_hit or not interruption_hit:
        raise ValueError("Named site and operations/BI anchor not co-located in this filing")
    record = {
        "source": "SEC_EDGAR_ISSUER_FILING",
        "official_url": entry["official_url"],
        "source_accession": entry["accession"],
        "source_cik": entry["issuer_cik"],
        "source_filename": entry["filename"],
        "source_scope": entry["source_scope"],
        "issuer_name": entry.get("issuer_name"),
        "event_type": entry.get("event_type"),
        "event_term_matched": matched_event,
        "reported_site_terms": [s for s in entry["site_terms"] if s.lower() in region.lower()],
        "filing_document_sha256": digest(html_bytes),
        "document_bytes": len(html_bytes),
        "extracted_text_sha256": digest(text.encode("utf-8")),
        "evidence_excerpt_sha256": digest(region.encode("utf-8")),
        "evidence_excerpt": region[:MAX_CONTEXT],
        "source_identity_verified": True,
        "issuer_disclosure_verified": True,
        "physical_site_independently_verified": False,
        "power_outage_verified": False,
        "duration_verified": False,
        "financial_amount_verified": False,
        "business_interruption_insurance_paid_verified": False,
        "loss_amount_usd": None,
        "claims_amount_usd": None,
        "amount_status": "NO_AUTOMATIC_MONETARY_ATTRIBUTION",
        "case_status": "ISSUER_DISCLOSURE_REQUIRES_INDEPENDENT_SITE_AND_FINANCIAL_REVIEW",
    }
    return record


def run(entry, out, html_path=None, user_agent=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    entry = validate_entry(entry)
    if html_path:
        path = Path(html_path)
        if not path.is_file():
            raise FileNotFoundError(str(path))
        content = path.read_bytes()
        origin = "local_primary_filing_copy"
    else:
        if not user_agent:
            raise ValueError("SEC download requires explicit truthful contact User-Agent")
        request = urllib.request.Request(entry["official_url"], headers={
            "User-Agent": user_agent, "Accept": "text/html"})
        with urllib.request.urlopen(request, timeout=50) as response:
            content = response.read(16_000_001)
        if len(content) > 16_000_000:
            raise ValueError("SEC filing download exceeded size ceiling")
        origin = "official_sec_download"
    record = inspect_filing(entry, content)
    (out / "evidence.jsonl").write_text(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest = {
        "source": "SEC_EDGAR_ISSUER_FILING",
        "official_url": entry["official_url"],
        "source_cik": entry["issuer_cik"],
        "source_accession": entry["accession"],
        "source_filename": entry["filename"],
        "source_scope": entry["source_scope"],
        "download_method": origin,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "document_sha256": record["filing_document_sha256"],
        "document_bytes": record["document_bytes"],
        "issuer_disclosures_accepted": 1,
        "source_documents_verified": 1,
        "independent_site_matches_verified": 0,
        "verified_outage_events": 0,
        "financial_amounts_verified": 0,
        "insured_claims_verified": 0,
        "durable_backend_indexed": 0,
        "deployed": 0,
        "restrictions": [
            "No numerical financial amounts extracted or auto-attributed.",
            "Same underlying event may reappear in later issuer filings: never sum without manual period reconciliation.",
            "Issuer description of a specific site is not an independent confirmed insured property crosswalk.",
            "Hurricane or flood business-interruption evidence is not an electric utility outage.",
            "Preserve raw official source only under authorized archival/data-retention practice.",
        ],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", type=Path, required=True)
    p.add_argument("--case", required=True, help="Exact catalog case ID")
    p.add_argument("--html", type=Path)
    p.add_argument("--user-agent")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    index = tomllib.loads(args.catalog.read_text(encoding="utf-8"))
    cases = [c for c in index.get("cases", []) if c.get("case_id") == args.case]
    if len(cases) != 1:
        raise ValueError("Exactly one cataloged case ID is required")
    print(json.dumps(run(cases[0], args.output, args.html, args.user_agent), indent=2))


if __name__ == "__main__":
    main()
