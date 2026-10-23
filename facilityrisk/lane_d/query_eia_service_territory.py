"""Lane D: EIA-861 source-only electric utility service-territory candidates.

The public EIA-861 county territory sheet names electric utility reporters that
serve somewhere within a county. It cannot identify the utility connected to
a particular building, electric meter, facility, or insured policy. Every result
is a review-only candidate, with EIA original source row and utility identifier.
Only exact source-reported state + county text matches are supported; ambiguous
counties are intentionally preserved as multiple candidate providers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote

MAX_RESULTS=100


def _readonly_db(path):
    p=Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return sqlite3.connect("file:"+quote(str(p),safe="/")+"?mode=ro",uri=True)


def service_territory_candidates(db_path, state, county, limit=50):
    """Return 2025 official electrical provider *candidates* for an exact county.

    Inputs state and county must be independently corroborated, but no site is
    auto-matched to these county-wide providers. Original EIA source keys stay
    distinct. No fuzzy canonical site/provider linkage or production writes.
    """
    if not isinstance(state,str) or not re.fullmatch(r"[A-Z]{2}",state):
        raise ValueError("EIA source state must be a two-letter uppercase code")
    if not isinstance(county,str) or not 2 <= len(county.strip()) <= 120 or any(c in county for c in "\r\n\t"):
        raise ValueError("EIA source county must be a literal 2-120 character name")
    if not isinstance(limit,int) or not 1<=limit<=MAX_RESULTS:
        raise ValueError("Limit must be a positive integer <= 100")
    county=county.strip()
    with _readonly_db(db_path) as db:
        where=("source_kind='service_territory' AND state=? "
               "AND county COLLATE NOCASE = ? COLLATE NOCASE")
        n=db.execute("SELECT COUNT(*) FROM source_observations WHERE "+where,(state,county)).fetchone()[0]
        rows=db.execute(
            """SELECT ingestion_row_key,utility_id,state,county,source_member,
                      source_sheet,source_row,row_sha256,original_row_json
                 FROM source_observations WHERE """+where+
            " ORDER BY utility_id,source_row LIMIT ?",(state,county,limit)).fetchall()
        candidates=[]
        for row in rows:
            key,utility_id,source_state,source_county,member,sheet,rownum,fingerprint,original_json=row
            original=json.loads(original_json)
            utility_name=original[2] if len(original)>2 else None
            reliability=db.execute(
                """SELECT ingestion_row_key,source_member,source_sheet,source_row,row_sha256,
                          original_row_json FROM source_observations
                   WHERE source_kind='reliability' AND utility_id=? AND state=?
                   ORDER BY source_row LIMIT 10""",(utility_id,state)).fetchall()
            links=[]
            for rid,rmember,rsheet,rrow,rsha,raw in reliability:
                values=json.loads(raw)
                links.append({
                    "reliability_source_row_key":rid,
                    "native_utility_id":utility_id,
                    "source_member":rmember,
                    "source_sheet":rsheet,
                    "source_row":rrow,
                    "row_sha256":rsha,
                    "reported_utility_name":values[2] if len(values)>2 else None,
                    "original_positional_values":values,
                    "metric_interpretation":"ORIGINAL_EIA_COLUMN_LAYOUT_REQUIRES_SHEET_HEADER",
                })
            candidates.append({
                "candidate_source":"EIA861_2025_COUNTY_UTILITY_TERRITORY",
                "source_row_key":key,
                "original_source_utility_id":utility_id,
                "source_state":source_state,
                "source_county":source_county,
                "source_utility_name":utility_name,
                "source_member":member,
                "source_sheet":sheet,
                "source_row":rownum,
                "source_row_sha256":fingerprint,
                "original_reported_cells":original,
                "same_state_utility_reliability_sources":links,
                "reported_service_area_grain":"COUNTY_CONTEXT",
                "site_serving_utility_verified":False,
                "facility_meter_connection_verified":False,
                "insured_site_outage_verified":False,
            })
    return {
        "requested_state":state,
        "requested_county_source_text":county,
        "source":"U.S. EIA-861 2025, Service Territory Counties_States",
        "source_area_match_method":"CASE_INSENSITIVE_EXACT_SOURCE_COUNTY_TEXT",
        "source_territory_observations":n,
        "candidate_records_returned":len(candidates),
        "truncated":n>limit,
        "returned_candidates":candidates,
        "verified_serving_facility_utility_connections":0,
        "verified_facility_outages":0,
        "verified_insured_business_interruption_claims":0,
        "limitations":[
            "A utility listed as serving some part of a county is NOT the confirmed utility at the specific insured property.",
            "Multiple provider candidates in the same county must not be deduplicated into one automatically.",
            "Same native utility ID and state may have separate reliability-source rows; return original EIA metrics, never an inferred site reliability score.",
            "Only EIA-reported 2025 electrical utility service county context; no gas, water, communications, or grid-circuit-level coverage.",
            "Exact county source text is not a geospatial boundary/FIPS crosswalk or a verified building address.",
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--state",required=True)
    p.add_argument("--county",required=True)
    p.add_argument("--limit",type=int,default=50)
    args=p.parse_args()
    print(json.dumps(service_territory_candidates(args.db,args.state,args.county,args.limit),ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
