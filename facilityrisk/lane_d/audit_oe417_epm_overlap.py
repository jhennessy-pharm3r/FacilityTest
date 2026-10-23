"""Lane D: explicitly UNVERIFIED EIA EPM vs DOE OE417 annual event candidates.

These are overlapping DOE-417-derived publishers without native stable incident
keys. Cross-publisher candidate associations require a matching actual event
start day + exact conservative normalized SOURCE-REPORTED affected-area text.
A candidate, even one-to-one, must NEVER be promoted to independently
confirmed same incident, property-level outage, or insurance claim.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from datetime import date,datetime
import argparse,hashlib,json,re
from pathlib import Path

from .ingest_electric_events import parse_events
from .ingest_oe417_annual import parse as parse_annual


def norm_area(s):
    if not isinstance(s,str):
        return ""
    return " ".join(re.findall(r"[A-Z0-9]+",s.upper())).strip()


def epm_start_date(row):
    text=row.get("reported_start","")
    if not isinstance(text,str):
        return None
    match=re.match(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\b",text)
    if not match:
        return None
    try:
        return date(int(match[3]),int(match[1]),int(match[2])).isoformat()
    except ValueError:
        return None


def assess(oe417: list[dict],epm: list[dict]):
    index=defaultdict(list)
    skipped_oe=Counter()
    for row in oe417:
        date_value=row.get("event_date_source")
        area=norm_area(row.get("source_area_text"))
        if row.get("is_exact_duplicate_publisher_record"):
            skipped_oe["literal_same_table_duplicate"]+=1
            continue
        if date_value is None:
            skipped_oe["date_unknown"]+=1
            continue
        if not area:
            skipped_oe["area_unknown"]+=1
            continue
        key=(date_value,area)
        index[key].append(row)
    match_groups=defaultdict(lambda:{"epm":[],"oe417":[]})
    skipped_epm=Counter()
    unparseable_start_samples=Counter()
    for row in epm:
        dt=epm_start_date(row)
        area=norm_area(row.get("reported_area"))
        if not dt:
            skipped_epm["unparseable_or_missing_start_date"]+=1
            unparseable_start_samples[str(row.get("reported_start"))[:100]]+=1
            continue
        if not area:
            skipped_epm["missing_affected_area"]+=1
            continue
        key=(dt,area)
        if key in index:
            match_groups[key]["epm"].append(row)
            match_groups[key]["oe417"]=index[key]
    one_to_one=ambiguous=0
    candidate_pairs=0
    seen_oe=set()
    seen_epm=set()
    groups=[]
    for key,items in sorted(match_groups.items()):
        ae=items["oe417"];ap=items["epm"]
        pairs=len(ae)*len(ap)
        candidate_pairs+=pairs
        ambiguous+=int(pairs>1)
        one_to_one+=int(pairs==1)
        seen_oe.update(x["source_row_key"] for x in ae)
        seen_epm.update(x["derived_source_row_key"] for x in ap)
        groups.append({
            "candidate_key_source_reported_date":key[0],
            "candidate_key_normalized_affected_area":key[1],
            "annual_source_row_keys":[x["source_row_key"] for x in ae],
            "epm_source_row_keys":[x["derived_source_row_key"] for x in ap],
            "annual_member_count":len(ae),
            "epm_member_count":len(ap),
            "cartesian_candidate_pair_count":pairs,
            "candidate_status":"AMBIGUOUS_MULTIPLE_CANDIDATES" if pairs>1 else "ONE_TO_ONE_TEXT_DATE_CANDIDATE_ONLY",
            "independently_verified_same_incident":False,
            "independently_verified_same_physical_site":False,
        })
    return {
        "source_pair":"DOE_CESER_OE417_2023_ANNUAL_VS_EIA_EPM_B2_2023",
        "oe417_annual_accepted_source_rows":len(oe417),
        "epm_b2_accepted_source_rows":len(epm),
        "oe417_candidate_eligible_date_area_rows":sum(map(len,index.values())),
        "oe417_source_rows_skipped_from_candidate_search":dict(skipped_oe),
        "epm_rows_skipped_from_candidate_search":dict(skipped_epm),
        "epm_unparseable_start_source_values":dict(unparseable_start_samples.most_common(25)),
        "exact_normalized_date_area_candidate_groups":len(groups),
        "one_to_one_unverified_candidate_groups":one_to_one,
        "ambiguous_multiplicity_candidate_groups":ambiguous,
        "all_candidate_row_pairs_including_ambiguous_cartesian":candidate_pairs,
        "distinct_oe417_rows_in_candidate_groups":len(seen_oe),
        "distinct_epm_rows_in_candidate_groups":len(seen_epm),
        "candidate_groups":groups,
        "independently_verified_same_incident_links":0,
        "verified_insured_site_outages":0,
        "deployed":0,
        "rules":[
            "Exact same calendar day and conservative alphanumeric SOURCE area text: review-only candidate; matching utility/incident identity not verified",
            "No native stable source event ID in either distribution; row keys are derived from original publication positions/digests",
            "One-to-one date-area match does not prove one actual incident; all same-source and cross-source originals retained",
            "NERC region/type/customer figures can disagree by source methods, so not accepted as independent matching proof",
            "Undated original DOE annual source rows remain unknown and are never assigned event dates",
            "DO NOT add either publisher row count to the other as distinct incidents, facilities or insurance losses",
        ],
    }


def run(eia_b2:Path,oe417_export:Path,oe417_metadata:Path,out:Path):
    out=Path(out)
    out.mkdir(parents=True,exist_ok=True)
    epm_bytes=Path(eia_b2).read_bytes()
    oe_bytes=Path(oe417_export).read_bytes()
    metadata_bytes=Path(oe417_metadata).read_bytes()
    epm,epm_rejected,_=parse_events(epm_bytes,"b2")
    oe,oe_rejected,_=parse_annual(oe_bytes,json.loads(metadata_bytes))
    audit=assess(oe,epm)
    audit.update({
        "original_eia_epm_b2_html_sha256":hashlib.sha256(epm_bytes).hexdigest(),
        "original_eia_epm_b2_html_bytes":len(epm_bytes),
        "original_doe_oe417_annual_json_sha256":hashlib.sha256(oe_bytes).hexdigest(),
        "original_doe_oe417_annual_json_bytes":len(oe_bytes),
        "original_doe_oe417_metadata_sha256":hashlib.sha256(metadata_bytes).hexdigest(),
        "epm_original_rejected_rows":len(epm_rejected),
        "oe417_original_rejected_rows":len(oe_rejected),
        "durable_backend_link_rows":0,
    })
    (out/"source_candidate_review.json").write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n")
    return audit


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--eia-b2-html",type=Path,required=True)
    p.add_argument("--oe417-json",type=Path,required=True)
    p.add_argument("--oe417-metadata",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    report=run(a.eia_b2_html,a.oe417_json,a.oe417_metadata,a.output)
    print(json.dumps({k:v for k,v in report.items() if k!="candidate_groups"},indent=2))


if __name__=="__main__":
    main()
