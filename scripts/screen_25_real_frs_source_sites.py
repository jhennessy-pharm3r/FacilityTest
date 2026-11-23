"""25 REAL EPA FRS source-identity screening candidates against installed NRC/CSB.

This is a real-source *research queue* test, NOT verification of 25 insured
physical properties. Require original versioned FRS SQLite from the official
EPA import, and the separately installed Lane C read-only NRC/CSB index.

Sample FRS rows are SHA-key sorted and diversified across actual source
industry descriptions / states. No names, addresses or source identifiers
are written to the PUBLIC aggregate QA report.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from facilityrisk.industrial_facility_screen import screen_site
from facilityrisk.industrial_source_indices import _verified

def _sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for part in iter(lambda:f.read(1024*1024),b""):
            h.update(part)
    return h.hexdigest()

def select_cohort(frs_index,*,count=25):
    if not 1<=count<=25:
        raise ValueError("Research cohort size must be 1-25")
    path=Path(frs_index)
    if not path.is_file():
        raise ValueError("Official source-only EPA FRS indexed SQLite required")
    db=sqlite3.connect(path.resolve().as_uri()+"?mode=ro&immutable=1",uri=True,timeout=30)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    try:
        tables={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"universal_sites","universal_source_records"}.issubset(tables):
            raise ValueError("FRS official universal source index tables missing")
        selected=[]
        ids=set()
        industry_counts=Counter()
        states=Counter()
        examined=0
        # SHA-key source site IDs are naturally pseudo-random, rather than
        # alphabetic business listings. Batch bounded; never scan a private
        # insured-policy table or assume everything with a FRS ID is a property.
        for offset in range(0,75000,3000):
            rows=db.execute("""SELECT s.id,s.name,s.company,s.address,s.city,
                         s.state,s.country,s.industry,s.latitude,s.longitude,
                         s.coordinate_quality,s.site_status,r.source_identifier
                         FROM universal_source_records AS r
                         JOIN universal_sites AS s ON s.id=r.site_id
                         WHERE r.source_key='EPA_FRS'
                         ORDER BY r.site_id LIMIT 3000 OFFSET ?""",(offset,)).fetchall()
            examined+=len(rows)
            for row in rows:
                x=dict(row)
                if (not x["source_identifier"] or not x["city"] or
                    len(x["state"] or "")!=2 or x["country"]!="US" or
                    x["latitude"] is None or x["longitude"] is None or
                    x["site_status"]!="source_observation"):
                    continue
                industry=str(x["industry"] or "").strip()
                if not industry or industry.lower() in ("unclassified","unknown"):
                    continue
                industry_key=industry.casefold()[:75]
                if industry_counts[industry_key]>=3:
                    continue
                if x["id"] in ids:
                    continue
                ids.add(x["id"])
                selected.append(x)
                industry_counts[industry_key]+=1
                states[x["state"]]+=1
                if len(selected)>=count and len(industry_counts)>=5 and len(states)>=5:
                    return selected,{"frs_source_rows_examined":examined,
                                     "different_reported_industries":len(industry_counts),
                                     "different_reported_states":len(states)}
        raise ValueError(
            f"Cannot select {count} source-identified FRS site candidates across >=5 industry and state categories from checked cohort; got {len(selected)}, {len(industry_counts)}, {len(states)}"
        )
    finally:
        db.close()

def run(frs_index,industrial_root,output):
    frs=Path(frs_index).resolve()
    if not frs.is_file() or frs.stat().st_size<1000:
        raise ValueError("Missing full independent national EPA FRS source index")
    os.environ["FACILITY_RISK_LANE_C_ROOT"]=str(Path(industrial_root).resolve())
    found,facts=_verified("observations")
    if len(facts["source_counts"])!=18:
        raise ValueError("25-source research QA requires validated NRC 2010-2026 + CSB indexed release")
    sites,selection=select_cohort(frs,count=25)
    scanned=Counter()
    result_stats=Counter()
    unc=Counter()
    samples=0
    for row in sites:
        proposal=screen_site(row,radius_km=10,limit=30)
        if proposal["state"]!="REVIEWER_SOURCE_CANDIDATE_SCREEN_COMPLETED":
            raise ValueError("Official FRS site identity failed industry-agnostic screening")
        samples+=1
        result_stats["review_candidates_proposed"]+=proposal["candidate_rows_before_display_limit"]
        result_stats["source_region_rows_examined"]+=proposal["publisher_rows_examined"]
        result_stats["sites_with_candidate_source_reports"]+=bool(proposal["candidate_rows_before_display_limit"])
        result_stats["candidate_screens_capped"]+=proposal["source_scan_capped"]
        if (proposal["verified_insured_matches"] or proposal["verified_losses"] or
            proposal["complete_historical_incident_coverage"]):
            raise ValueError("An unreviewed EPA FRS site was automatically converted to validated insured loss")
        scanned[row["state"]]+=1
        unc[row["industry"][:75]]+=1
    if samples!=25 or len(scanned)<5 or len(unc)<5:
        raise ValueError("Insufficient FRS research source identity/geographic variety")
    summary={
      "status":"25_GENUINE_OFFICIAL_EPA_FRS_SOURCE_IDENTITIES_SCREENED_NOT_25_INSURED_PROPERTIES",
      "checked_at":datetime.now(timezone.utc).isoformat(),
      "source":"EPA Facility Registry Service, independently indexed official national source",
      "frs_index_sha256":_sha(frs),
      "lane_c_index_sha256":found["expected_sha"],
      "nrc_csb_source_observations_available":facts["rows"],
      "ephemeral_source_registry_records_screened":samples,
      "distinct_reported_sector_labels":len(unc),
      "distinct_reported_states":len(scanned),
      "selection_qa":selection,
      "screening_qa":dict(result_stats),
      "false_positive_and_actual_event_reviewer_conclusions":"NOT_PERFORMED",
      "independent_physically_verified_sites":0,
      "insured_site_coverage_confirmed":0,
      "confirmed_incident_outcomes":0,
      "calibrated_insurance_losses":0,
      "primary_phmsa_incident_census":"NOT_TESTED_ACCESS_BLOCKED",
      "raw_source_rows_or_unreviewed_frs_names_exported":0,
      "caveat":"FRS identity plus NRC/CSB source proximity/name is a research candidate only. Requires approved reviewer site identity and independent outcome evidence."
    }
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))
    return summary

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--frs-index",required=True,type=Path)
    p.add_argument("--industrial-root",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    args=p.parse_args()
    run(args.frs_index,args.industrial_root,args.output)

if __name__=="__main__":
    main()
