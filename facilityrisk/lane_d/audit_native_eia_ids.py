"""Lane D: exact cross-publisher EIA utility ID concordance, not physical-site linkage.

Compare ORNL ODIN's names[nameType=UtilityId,nameTypeAuthority=EIA] against
EIA-861 2025 native source utility IDs. Exact IDs identify reporting *utility
entities*, NOT an insured property's service provider, meter or electric outage.
Source name differences are surfaced for review rather than fuzzy-matched.
"""
from __future__ import annotations
from collections import defaultdict
import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote


def connect_readonly(path):
    p=Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))
    return sqlite3.connect("file:"+quote(str(p),safe="/")+"?mode=ro",uri=True)


def hash_file(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for x in iter(lambda:f.read(1024*1024),b""):
            h.update(x)
    return h.hexdigest()


def collapsed_name(s):
    return re.sub(r"\s+"," ",str(s or "").strip().upper())


def audit_native_utility_identity(eia_db, odin_db):
    eia_db,odin_db=Path(eia_db),Path(odin_db)
    with connect_readonly(eia_db) as db:
        if db.execute("PRAGMA quick_check").fetchone()[0]!="ok":
            raise ValueError("EIA source-only index failed integrity check")
        eia_rows=db.execute("""SELECT utility_id,source_kind,state,county,original_row_json
            FROM source_observations WHERE utility_id IS NOT NULL
            AND source_kind IN ('service_territory','reliability')""")
        lookup=defaultdict(lambda:{"reliability_states":set(),"territory_states":set(),
                                    "territory_counties":set(),"publisher_names":set()})
        for uid,kind,state,county,original in eia_rows:
            values=json.loads(original)
            if len(values)>2 and values[2]:
                lookup[uid]["publisher_names"].add(str(values[2]))
            if kind=="reliability":
                lookup[uid]["reliability_states"].add(state)
            else:
                lookup[uid]["territory_states"].add(state)
                lookup[uid]["territory_counties"].add((state,county))
        eia_counts=dict(db.execute("SELECT source_kind,count(*) FROM source_observations GROUP BY source_kind"))
    odin_utility=defaultdict(lambda:{"county_fips":set(),"source_names":set(),"original_rows":0})
    missing_id=0
    with connect_readonly(odin_db) as db:
        if db.execute("PRAGMA quick_check").fetchone()[0]!="ok":
            raise ValueError("ODIN first-party source-only index failed integrity check")
        for utility_id,county,raw in db.execute(
            "SELECT native_eia_utility_id,native_county_fips,original_json FROM source_observations"):
            if not utility_id:
                missing_id+=1
                continue
            rec=odin_utility[utility_id]
            rec["county_fips"].add(county)
            rec["original_rows"]+=1
            body=json.loads(raw)
            for item in body.get("names") or []:
                if isinstance(item,dict) and item.get("nameType")=="UtilityName" and item.get("nameTypeAuthority")=="EIA" and item.get("name"):
                    rec["source_names"].add(str(item["name"]))
        odin_rows=db.execute("SELECT COUNT(*) FROM source_observations").fetchone()[0]
    links=[]
    category_count={"in_both":0,"in_reliability_only":0,"in_territory_only":0,"missing_from_eia_2025":0}
    mismatched_names=0
    for uid,source in sorted(odin_utility.items()):
        reference=lookup.get(uid)
        if reference is None:
            category="missing_from_eia_2025"
        elif reference["reliability_states"] and reference["territory_states"]:
            category="in_both"
        elif reference["reliability_states"]:
            category="in_reliability_only"
        else:
            category="in_territory_only"
        category_count[category]+=1
        source_names=sorted(source["source_names"])
        eia_names=sorted(reference["publisher_names"]) if reference else []
        normalized_odin={collapsed_name(x) for x in source_names}
        normalized_eia={collapsed_name(x) for x in eia_names}
        conflict=bool(normalized_odin and normalized_eia and not normalized_odin.intersection(normalized_eia))
        mismatched_names+=int(conflict)
        links.append({
            "native_eia_utility_id":uid,
            "eia_2025_availability":category,
            "odin_source_names":source_names,
            "eia_2025_source_names":eia_names,
            "publisher_name_review_needed":conflict,
            "odin_county_fips_count":len(source["county_fips"]),
            "odin_observation_rows":source["original_rows"],
            "eia_territory_county_text_rows":len(reference["territory_counties"]) if reference else 0,
            "eia_reliability_state_row_candidates":len(reference["reliability_states"]) if reference else 0,
            "verified_insured_site_serving_utility":False,
            "verified_insured_site_power_outage":False,
        })
    if sum(x["odin_observation_rows"] for x in links)+missing_id!=odin_rows:
        raise ValueError("Source-only ODIN-native EIA utility linkage count not reconciled")
    return {
        "source":"LANE_D_EIA_UTILITY_ID_CONCORDANCE",
        "original_eia_2025_sqlite_sha256":hash_file(eia_db),
        "odin_current_snapshot_sqlite_sha256":hash_file(odin_db),
        "eia_source_kind_rows":eia_counts,
        "odin_public_county_status_rows":odin_rows,
        "odin_native_utility_id_missing_rows":missing_id,
        "odin_distinct_source_native_eia_utility_ids":len(odin_utility),
        "eia_distinct_source_native_utility_ids":len(lookup),
        "publisher_native_id_link_status":category_count,
        "native_id_matches":sum(category_count.values())-category_count["missing_from_eia_2025"],
        "source_utility_name_disagreement_candidates":mismatched_names,
        "links":links,
        "verified_physical_facility_power_provider_assignments":0,
        "verified_site_electric_outages":0,
        "durable_backend_links_indexed":0,
        "deployed":0,
        "review_policy":[
            "Match exact EIA authority utility numbers only, never source names or nearest-county geometry",
            "Native utility identity match does not prove an insured physical site is on that company's service circuit",
            "ODIN source county FIPS and EIA county name/state are different grains; no automatic county crosswalk",
            "EIA-861 is annual 2025 and ODIN is a changing live snapshot; missing utility ID may be vintage gap",
            "Reliability metrics apply to reporting utility/state, not an individual building or coverage limit",
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--eia-db",type=Path,required=True)
    p.add_argument("--odin-db",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    report=audit_native_utility_identity(a.eia_db,a.odin_db)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="links"},indent=2))


if __name__=="__main__":
    main()
