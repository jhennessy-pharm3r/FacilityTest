"""Lane D: read-only official DOE OE-417 public annual research event context.

Queries the original public-domain DOE annual summary's source-native descriptive
fields, WITHOUT fuzzy insured-site joins or synthetic native event IDs. Historic
2023 discovery data may overlap EIA Electric Power Monthly DOE-417 reports and
must never be added to their event counts. Undated original rows are retrievable.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
from urllib.parse import quote


def annual_context(db_path, *, event_year=None, event_type=None, date_state="all", limit=50):
    if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=100:
        raise ValueError("Source-only query limit must be 1-100")
    if event_year is not None and (not isinstance(event_year,int) or isinstance(event_year,bool)
                                   or not 2000<=event_year<=2026):
        raise ValueError("Event year must be a verifiable 2000-2026 calendar year")
    if date_state not in ("all","dated","undated"):
        raise ValueError("date_state must be all, dated or undated")
    if event_year is not None and date_state=="undated":
        raise ValueError("Undated source rows cannot be assigned an event year")
    if event_type is not None and (not isinstance(event_type,str) or not 1<=len(event_type)<=120
                                   or any(c in event_type for c in "\n\r\t")):
        raise ValueError("An exact source-reported DOE OE417 event type is required")
    path=Path(db_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    predicates=["exact_duplicate_source=0"]
    args=[]
    if event_year is not None:
        predicates.append("substr(event_date,1,4)=?")
        args.append(str(event_year))
    if date_state=="dated":
        predicates.append("event_date IS NOT NULL")
    elif date_state=="undated":
        predicates.append("event_date IS NULL")
    if event_type is not None:
        predicates.append("source_event_type=?")
        args.append(event_type)
    where=" WHERE "+" AND ".join(predicates)
    with sqlite3.connect("file:"+quote(str(path),safe="/")+"?mode=ro",uri=True) as conn:
        raw_total=conn.execute("SELECT COUNT(*) FROM source_observations").fetchone()[0]
        exact_repeats=conn.execute(
            "SELECT COUNT(*) FROM source_observations WHERE exact_duplicate_source=1").fetchone()[0]
        matched=conn.execute("SELECT COUNT(*) FROM source_observations"+where,args).fetchone()[0]
        sql=("SELECT source_row_key,original_position,event_date,restoration_date,"
             "source_area_text,source_event_type,source_nerc_region,source_alert_criteria,"
             "reported_customers,reported_demand_mw_decimal,original_row_sha256"
             " FROM source_observations"+where+" ORDER BY event_date DESC,original_position LIMIT ?")
        results=[]
        for r in conn.execute(sql,args+[limit]):
            results.append({
                "category":"HISTORICAL_DOE_OE417_ANNUAL_SOURCE_OBSERVATION",
                "source":"DOE CESER OE-417 public 2023 discovery dataset distributed by ORNL",
                "publisher_native_event_id":None,
                "derived_original_source_row_key":r[0],
                "original_source_row_1based":r[1],
                "reported_incident_start_date":r[2],
                "date_status":"NOT_REPORTED" if r[2] is None else "REPORTED",
                "reported_restoration_date":r[3],
                "source_reported_affected_area_text":r[4],
                "source_reported_event_type":r[5],
                "source_reported_nerc_region":r[6],
                "source_reported_alert_criteria":r[7],
                "source_reported_affected_customers":r[8],
                "source_reported_demand_loss_mw_decimal":r[9],
                "original_source_row_sha256":r[10],
                "reported_as_insured_property":False,
                "insured_site_electric_outage_verified":False,
                "insured_policy_claim_payment_verified":False,
            })
    return {
        "query_status":"PUBLISHED_ANNUAL_ELECTRIC_DISTURBANCE_CONTEXT_NOT_PROPERTY_EVENT",
        "requested_source_event_year":event_year,
        "requested_date_state":date_state,
        "requested_exact_event_type":event_type,
        "original_source_rows_total":raw_total,
        "exact_duplicate_original_rows_withheld":exact_repeats,
        "matching_content_distinct_source_rows":matched,
        "returned":len(results),
        "truncated":matched>len(results),
        "source_records":results,
        "independently_confirmed_insured_facility_outages":0,
        "independently_confirmed_insurer_paid_business_interruption_claims":0,
        "deployed":0,
        "limitations":[
            "Publisher annual discovery dataset has no native event ID; derived row key must not imply unique emergency",
            "32 original undated source rows are unknown start dates; cannot impute an event year or zero risk",
            "Area affected is source-reported free text, not site geolocation or a verified utility meter",
            "These OE417 rows may overlap DOE417-derived EIA EPM reporting; source event counts are not additive",
            "This context is not an insured facility's downtime, utility service or insurance recovery validation",
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True,type=Path)
    p.add_argument("--year",type=int)
    p.add_argument("--event-type")
    p.add_argument("--date-state",choices=("all","dated","undated"),default="all")
    p.add_argument("--limit",type=int,default=50)
    a=p.parse_args()
    print(json.dumps(annual_context(a.db,event_year=a.year,event_type=a.event_type,
        date_state=a.date_state,limit=a.limit),indent=2,ensure_ascii=False))


if __name__=="__main__":
    main()
