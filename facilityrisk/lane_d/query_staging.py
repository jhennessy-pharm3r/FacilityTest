"""Source-only read-only county outage context query contract for Lane E coordinator.

This module does NOT assign an insured facility's electric utility, verify meter
service, score an insured property, or deploy endpoints. Input FIPS must already
come from an independently verified site locality. Query event categories are
disjoint; use historical county episodes or ODIN snapshots separately.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import json
import re
import sqlite3
from urllib.parse import quote


def validate_fips(value):
    if not isinstance(value,str) or not re.fullmatch(r"[0-9]{5}",value):
        raise ValueError("An independently reviewed five-digit county FIPS string is required")
    return value


def ro_connect(path):
    path=Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    return sqlite3.connect("file:"+quote(str(path),safe="/")+ "?mode=ro",uri=True)


def get_county_context(fips, pnnl_db=None, odin_db=None, year=None, limit=25, odin_direct_db=None):
    fips=validate_fips(fips)
    if not isinstance(limit,int) or not 1<=limit<=100:
        raise ValueError("County QA query limit must be an integer from 1 to 100")
    if year is not None and (not isinstance(year,int) or not 2014<=year<=2023):
        raise ValueError("Historical PNNL year must be between 2014 and 2023")
    if odin_db is not None and odin_direct_db is not None:
        raise ValueError('Choose one ODIN publisher distribution per snapshot, not both overlapping feeds')
    findings=[]
    odin_direct_count=None
    odin_direct_duplicates=None
    pnnl_count=None
    odin_count=None
    if pnnl_db is not None:
        with ro_connect(pnnl_db) as db:
            sql="""SELECT source_kind,dataset_year,county_fips,state,county,
                            reported_start,reported_duration_hours,reported_mean_customers,
                            native_event_id,source_member,source_line_number,source_row_sha256
                     FROM source_observations
                     WHERE county_fips=? AND source_kind='county_episode'"""
            params=[fips]
            if year is not None:
                sql+=" AND dataset_year=?"
                params.append(year)
            pnnl_count=db.execute(
                "SELECT COUNT(*) FROM source_observations WHERE county_fips=? AND source_kind='county_episode'"
                + (" AND dataset_year=?" if year is not None else ""),params).fetchone()[0]
            sql+=" ORDER BY dataset_year DESC, reported_start DESC, source_row_sha256 LIMIT ?"
            params.append(limit)
            for r in db.execute(sql,params):
                findings.append({
                    "publisher":"DOE/PNNL",
                    "category":"HISTORICAL_COUNTY_OUTAGE_EPISODE",
                    "source_kind":r[0],"source_year":r[1],
                    "county_fips":r[2],"reported_state":r[3],"reported_county":r[4],
                    "reported_start_time_no_tz":r[5],
                    "published_county_episode_duration_hours":r[6],
                    "published_county_mean_affected_customers":r[7],
                    "native_event_id":r[8],
                    "source_member":r[9],"source_row":r[10],"source_sha256":r[11],
                    "insured_facility_outage_verified":False,
                })
    if odin_db is not None:
        with ro_connect(odin_db) as db:
            odin_count=db.execute(
                "SELECT COUNT(*) FROM source_observations WHERE county_fips=?",(fips,)).fetchone()[0]
            for row in db.execute(
                """SELECT original_row_position,native_utility_id,county_fips,reported_state,
                          reported_county,reported_start_time,snapshot_utc,source_sha256
                   FROM source_observations WHERE county_fips=?
                   ORDER BY reported_start_time DESC,original_row_position LIMIT ?""",(fips,limit)):
                findings.append({
                    "publisher":"DOE/ORNL ODIN",
                    "category":"PUBLIC_COUNTY_OUTAGE_SNAPSHOT",
                    "source_row":row[0],"reported_utility_id":row[1],
                    "county_fips":row[2],"reported_state":row[3],
                    "reported_county":row[4],"reported_start_time":row[5],
                    "snapshot_utc":row[6],"source_sha256":row[7],
                    "insured_facility_outage_verified":False,
                    "site_utility_assignment_verified":False,
                })
    if odin_direct_db is not None:
        with ro_connect(odin_direct_db) as db:
            odin_direct_count=db.execute(
                "SELECT COUNT(*) FROM source_observations WHERE native_county_fips=?",
                (fips,)).fetchone()[0]
            odin_direct_duplicates=db.execute(
                "SELECT COUNT(*) FROM source_observations WHERE native_county_fips=? AND is_exact_duplicate=1",
                (fips,)).fetchone()[0]
            for row in db.execute(
                """SELECT original_position,native_mrid,native_county_fips,native_eia_utility_id,
                          reported_start,meters_affected,snapshot_utc,original_row_sha256
                   FROM source_observations
                   WHERE native_county_fips=? AND is_exact_duplicate=0
                   ORDER BY reported_start DESC,original_position LIMIT ?""",
                (fips,limit)):
                findings.append({
                    "publisher":"DOE/ORNL ODIN FIRST_PARTY",
                    "category":"PUBLIC_COUNTY_OUTAGE_SNAPSHOT",
                    "source_distribution":"ODIN_DIRECT_NONAUTH_COUNTY",
                    "source_row":row[0],"native_mrid":row[1],
                    "county_fips":row[2],"reported_utility_id_EIA_authority":row[3],
                    "reported_start_time":row[4],
                    "published_current_outage_affected_meter_count":row[5],
                    "snapshot_utc":row[6],"source_sha256":row[7],
                    "exact_repeated_publisher_records_excluded":odin_direct_duplicates,
                    "insured_facility_outage_verified":False,
                    "site_utility_assignment_verified":False,
                    "verified_insurer_claim_amount":False,
                })
    return {
        "query_county_fips":fips,
        "query_status":"SOURCE_ONLY_CONTEXT_NOT_SITE_EVIDENCE",
        "candidate_counts":({
            "pnnl_historical_county_episodes":pnnl_count,
            "odin_public_county_snapshot_rows":odin_count,
        } | ({"odin_firstparty_public_county_snapshot_raw_rows":odin_direct_count,
               "odin_firstparty_exact_duplicate_rows_excluded":odin_direct_duplicates}
              if odin_direct_db is not None else {})),
        "returned_findings":findings,
        "per_source_limit":limit,
        "verified_insured_outages":0,
        "verified_business_interruption_claims":0,
        "restrictions":[
            "Requires independently corroborated property locality; county match is not a site match",
            "Source datasets cover different periods and publication conventions; do not add source rows",
            "PNNL source duration is a county-level research episode, not a property's downtime",
            "ODIN public snapshot rows are near-real-time statuses and must never be added over time",
            "Direct official ODIN and Open Energy Hub mirror are overlapping distributions and never additive",
            "No review candidate establishes electrical service connection or insurance coverage",
        ],
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--fips",required=True)
    p.add_argument("--pnnl-db",type=Path)
    p.add_argument("--odin-db",type=Path)
    p.add_argument("--odin-direct-db",type=Path)
    p.add_argument("--year",type=int)
    p.add_argument("--limit",type=int,default=25)
    a=p.parse_args()
    if a.pnnl_db is None and a.odin_db is None and a.odin_direct_db is None:
        raise ValueError("At least one source-only staging index must be supplied")
    print(json.dumps(get_county_context(a.fips,a.pnnl_db,a.odin_db,a.year,a.limit,a.odin_direct_db),indent=2))


if __name__=="__main__":
    main()
