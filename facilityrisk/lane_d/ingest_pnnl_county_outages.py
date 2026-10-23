"""Lane D: ingest DOE/PNNL Event-Correlated Outage Dataset in America.

Official archive: https://data.openei.org/files/6458/Outage_Dataset_R1.zip
Report 2014-2023 annual source vintages as distinct source families:
  - merged county outage episodes
  - raw state/month aggregate (month=0 is published aggregate, not a month)
  - full event-correlated county observations
  - 8h and 24h lag *sensitivity variants*, not additional events/outages

Native event_id is retained *only* for correlated variants (may repeat across
county rows); merged episodes have no native event ID. County FIPS is NOT a
physical site, and duration does not prove an insured facility's downtime.
Stdlib streaming ZIP CSV > SQLite importer with source SHA and rejection ledger.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import zipfile


SOURCE_URL = "https://data.openei.org/files/6458/Outage_Dataset_R1.zip"
DATA_CATALOG = "https://data.openei.org/submissions/6458"
EXPECTED_YEARS=tuple(range(2014,2024))
MAX_UNCOMPRESSED=1_000_000_000
PATTERNS=(
    (re.compile(r"eaglei_outages_(20\d{2})_merged\.csv$",re.I),"county_episode"),
    (re.compile(r"eaglei_outages_(20\d{2})_group\.csv$",re.I),"state_month_aggregate"),
    (re.compile(r"eaglei_outages_with_events_(20\d{2})\.csv$",re.I),"correlated_event"),
    (re.compile(r"eaglei_outages_with_events_(20\d{2})_8_hours_lag\.csv$",re.I),"correlation_8h_sensitivity"),
    (re.compile(r"eaglei_outages_with_events_(20\d{2})_24_hours_lag\.csv$",re.I),"correlation_24h_sensitivity"),
)
COLUMNS={
    "county_episode": ("fips","state","county","start_time","duration","min_customers","max_customers","mean_customers"),
    "state_month_aggregate": ("state","year","month","outage_count","max_outage_duration","customer_weighted_hours"),
    "correlated_event": ("event_id","state_event","Datetime Event Began","Datetime Restoration",
                         "Event Type","fips","state","county","start_time","duration","end_time",
                         "min_customers","max_customers","mean_customers"),
    "correlation_8h_sensitivity": ("event_id","state_event","Datetime Event Began","Datetime Restoration",
                         "Event Type","fips","state","county","start_time","duration",
                         "min_customers","max_customers","mean_customers"),
    "correlation_24h_sensitivity": ("event_id","state_event","Datetime Event Began","Datetime Restoration",
                         "Event Type","fips","state","county","start_time","duration",
                         "min_customers","max_customers","mean_customers"),
}
EVENT_TYPES={"correlated_event","correlation_8h_sensitivity","correlation_24h_sensitivity"}
COUNTY_TYPES=EVENT_TYPES|{"county_episode"}
METRIC_NAMES=(
    "duration","min_customers","max_customers","mean_customers","outage_count",
    "max_outage_duration","customer_weighted_hours",
)
REJECT_METRIC={"nan","inf","infinity","-inf","-infinity"}
NULLS={"","n/a","na","null","none","nan","inf"}
BATCH_SIZE=5000


def sha(b):
    return hashlib.sha256(b).hexdigest()


def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):
            h.update(block)
    return h.hexdigest()


def member_type(name,years):
    if not name.startswith("Outage_Dataset/"):
        return None
    for pattern,kind in PATTERNS:
        m=pattern.fullmatch(Path(name).name)
        if m and int(m.group(1)) in years:
            return int(m.group(1)),kind
    return None


def typed_metrics(row,kind):
    result={}
    for field in METRIC_NAMES:
        if field not in row:
            continue
        literal=str(row[field] or "").strip()
        if literal.lower() in NULLS:
            result[field]=None
            continue
        try:
            val=Decimal(literal)
        except InvalidOperation as exc:
            raise ValueError("invalid_metric_"+field) from exc
        if not val.is_finite() or val<0:
            raise ValueError("invalid_metric_"+field)
        if field=="outage_count" and val!=val.to_integral_value():
            raise ValueError("noninteger_outage_count")
        result[field]=float(val)
    if {"min_customers","max_customers"}.issubset(result):
        lo,hi=result["min_customers"],result["max_customers"]
        if lo is not None and hi is not None and lo>hi:
            raise ValueError("min_customers_greater_than_max")
    return result


def validate_row(row,kind,year):
    if kind in COUNTY_TYPES:
        fips=str(row.get("fips") or "").strip()
        if not re.fullmatch(r"\d{1,5}",fips) or int(fips)<=0:
            raise ValueError("invalid_county_fips")
        if not str(row.get("state") or "").strip() or not str(row.get("county") or "").strip():
            raise ValueError("missing_state_county")
        original=row.get("start_time") or ""
        try:
            parsed=datetime.strptime(original,"%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise ValueError("invalid_start_timestamp") from exc
        fips=fips.zfill(5)
        native=row.get("event_id") if kind in EVENT_TYPES else None
        native=native.strip() if isinstance(native,str) and native.strip() else None
        values=typed_metrics(row,kind)
        return fips, parsed.isoformat(), native, values
    if kind=="state_month_aggregate":
        if not row.get("state","").strip():
            raise ValueError("missing_state")
        if str(row.get("year")) != str(year):
            raise ValueError("incorrect_aggregate_year")
        try:
            month=int(row.get("month",""))
        except (TypeError,ValueError) as exc:
            raise ValueError("invalid_source_month") from exc
        if not 0<=month<=12:
            raise ValueError("invalid_source_month")
        return None,None,None,typed_metrics(row,kind)
    raise ValueError("unknown_source_kind")


def normalize(archive,output,years=EXPECTED_YEARS):
    archive=Path(archive)
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    years=tuple(sorted(set(years)))
    if not years or min(years)<2014 or max(years)>2023:
        raise ValueError("Publication supports complete 2014-2023 source years only")
    if not zipfile.is_zipfile(archive):
        raise ValueError("DOE/PNNL input is not a ZIP")
    archive_hash=file_hash(archive)
    stats=[]
    accepted_total,rejected_total=0,0
    kind_counts,reason_counts=Counter(),Counter()
    exact_source_duplicate_rows=0
    fips,states=set(),set()
    published_start_min,published_start_max=None,None
    null_counts,native_event_ids=Counter(),set()
    native_empty_count=0
    cross_year_starts=Counter()
    natural_keys=Counter()
    db=sqlite3.connect(output/"pnnl_county_outage_staging.sqlite")
    rejected_path=output/"rejected.jsonl"
    normalized_path=output/"accepted.jsonl"
    try:
        db.execute("PRAGMA journal_mode=OFF")
        db.execute("PRAGMA synchronous=OFF")
        db.execute("""CREATE TABLE source_observations(
           source_row_key TEXT PRIMARY KEY,
           source_kind TEXT NOT NULL,
           dataset_year INTEGER NOT NULL,
           county_fips TEXT,
           state TEXT,
           county TEXT,
           reported_start TEXT,
           reported_duration_hours REAL,
           reported_mean_customers REAL,
           native_event_id TEXT,
           source_member TEXT NOT NULL,
           source_line_number INTEGER NOT NULL,
           source_row_sha256 TEXT NOT NULL,
           raw_json TEXT NOT NULL
        )""")
        with zipfile.ZipFile(archive) as z, normalized_path.open("w",encoding="utf-8") as accepted_out, rejected_path.open("w",encoding="utf-8") as rejected_out:
            members={name:member_type(name,years) for name in z.namelist()}
            members={k:v for k,v in members.items() if v is not None}
            expected_pairs={(y,k) for y in years for k in COLUMNS}
            found_pairs=set(members.values())
            if expected_pairs!=found_pairs or len(members)!=len(expected_pairs):
                raise ValueError("Missing/duplicated expected source tables, expected "
                                 + str(len(expected_pairs)) + " got " + str(len(members)))
            for member in sorted(members):
                year,kind=members[member]
                info=z.getinfo(member)
                if info.file_size>MAX_UNCOMPRESSED:
                    raise ValueError("Oversized official CSV member")
                raw=z.read(member)
                member_sha=sha(raw)
                head_row_count,member_good,member_bad=0,0,0
                member_null,member_exact=Counter(),Counter()
                min_ts,max_ts=None,None
                reader=csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
                if tuple(reader.fieldnames or ())!=COLUMNS[kind]:
                    raise ValueError("Official CSV schema drift: "+member+": "+str(reader.fieldnames))
                for line,row in enumerate(reader,start=2):
                    head_row_count+=1
                    actual=dict(row)
                    row_payload=json.dumps(actual,sort_keys=True,separators=(",",":"),ensure_ascii=False)
                    fingerprint=sha(row_payload.encode("utf-8"))
                    member_exact[fingerprint]+=1
                    try:
                        if any(k is None or v is None for k,v in actual.items()):
                            raise ValueError("ragged_source_csv_row")
                        county_fips,dt,native,typed=validate_row(row,kind,year)
                    except ValueError as exc:
                        reason=str(exc)
                        reason_counts[reason]+=1
                        member_bad+=1
                        rejected_out.write(json.dumps({"source_member":member,"source_kind":kind,
                            "source_line_number":line,"source_row_sha256":fingerprint,
                            "reason":reason,"raw":actual},sort_keys=True,ensure_ascii=False)+"\n")
                        continue
                    source_key=sha(json.dumps([member,line,fingerprint],separators=(",",":")).encode("utf-8"))
                    name=row.get("state","").strip()
                    cnty=row.get("county","").strip() if county_fips else None
                    fips.add(county_fips) if county_fips else None
                    states.add(name)
                    if native is not None:
                        native_event_ids.add((year,native))
                    elif kind in EVENT_TYPES:
                        native_empty_count+=1
                    if dt:
                        observed_year=int(dt[:4])
                        if observed_year!=year:
                            cross_year_starts[year]+=1
                        min_ts=dt if min_ts is None or dt<min_ts else min_ts
                        max_ts=dt if max_ts is None or dt>max_ts else max_ts
                        published_start_min=dt if published_start_min is None or dt<published_start_min else published_start_min
                        published_start_max=dt if published_start_max is None or dt>published_start_max else published_start_max
                    for field,value in typed.items():
                        if value is None:
                            null_counts[field]+=1
                            member_null[field]+=1
                    nk=(year,kind,county_fips,dt,native) if dt else (year,kind,name,row.get("month",""))
                    # Same county+start may have distinct source events: count candidates only.
                    natural_keys[nk]+=1
                    row_record={
                        "source":"DOE_PNNL_EVENT_CORRELATED_OUTAGE",
                        "publisher":"Pacific Northwest National Laboratory / DOE",
                        "archive_source_url":SOURCE_URL,
                        "source_member":member,"source_kind":kind,
                        "source_year":year,"source_line_number":line,
                        "source_row_key":source_key,"source_row_sha256":fingerprint,
                        "source_county_fips":county_fips,
                        "source_state":name,"source_county":cnty,
                        "source_start_time":dt,
                        "native_event_id":native,
                        "reported_metrics":typed,
                        "monthly_aggregate_sentinel":kind=="state_month_aggregate" and row.get("month","")=="0",
                        "evidence_status":"PUBLISHED_COUNTY_CONTEXT_NOT_INDEPENDENTLY_SITE_VERIFIED",
                        "facility_outage_verified":False,
                        "insurer_claim_verified":False,
                        "raw":actual,
                    }
                    accepted_out.write(json.dumps(row_record,sort_keys=True,ensure_ascii=False)+"\n")
                    db.execute("INSERT INTO source_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (source_key,kind,year,county_fips,name,cnty,dt,typed.get("duration"),
                         typed.get("mean_customers"),native,member,line,fingerprint,row_payload))
                    accepted_total+=1
                    member_good+=1
                    kind_counts[kind]+=1
                    if accepted_total%BATCH_SIZE==0:
                        db.commit()
                if head_row_count!=member_good+member_bad:
                    raise ValueError("Unreconciled member original row count: "+member)
                member_exact_duplicates=sum(v-1 for v in member_exact.values() if v>1)
                exact_source_duplicate_rows+=member_exact_duplicates
                stats.append({
                    "source_member":member,"source_year":year,"source_kind":kind,
                    "uncompressed_bytes":info.file_size,"member_sha256":member_sha,
                    "source_rows_scanned":head_row_count,"accepted":member_good,"rejected":member_bad,
                    "exact_duplicate_source_rows_in_member":member_exact_duplicates,
                    "observed_min_start":min_ts,"observed_max_start":max_ts,
                    "null_metrics":dict(member_null),
                    "source_header":list(COLUMNS[kind]),
                })
        db.commit()
        db.execute("CREATE INDEX idx_county_year_kind ON source_observations(county_fips,dataset_year,source_kind)")
        db.execute("CREATE INDEX idx_event_native_id ON source_observations(native_event_id,source_kind)")
        db.execute("CREATE INDEX idx_time_kind ON source_observations(reported_start,source_kind)")
        db.commit()
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise RuntimeError("DOE PNNL SQLite failed integrity_check")
        staged=db.execute("SELECT count(*) FROM source_observations").fetchone()[0]
        indexed_by_kind=dict(db.execute("SELECT source_kind,count(*) FROM source_observations GROUP BY source_kind"))
        if staged!=accepted_total or indexed_by_kind!=dict(kind_counts):
            raise RuntimeError("DOE PNNL SQLite counts disagree with source rows")
    finally:
        db.close()
    receipt={
        "source":"DOE_PNNL_EVENT_CORRELATED_OUTAGE",
        "source_url":SOURCE_URL,"catalog_url":DATA_CATALOG,
        "archive_sha256":archive_hash,"archive_bytes":archive.stat().st_size,
        "source_coverage_years":list(years),
        "source_vintage_type":"PUBLISHED_HISTORICAL_CORRELATION_RESEARCH_DATASET",
        "run_utc":datetime.now(timezone.utc).isoformat(),
        "published_csv_members":len(stats),"source_rows_scanned":accepted_total+sum(s["rejected"] for s in stats),
        "accepted":accepted_total,
        "rejected":sum(s["rejected"] for s in stats),
        "rejection_reasons":dict(reason_counts),
        "accepted_by_source_kind":dict(kind_counts),
        "locally_indexed":staged,"locally_indexed_by_source_kind":indexed_by_kind,
        "source_members":stats,
        "source_state_names":sorted(states),"distinct_state_names":len(states),
        "unique_county_fips":len(fips),
        "earliest_recorded_county_episode":published_start_min,
        "latest_recorded_county_episode":published_start_max,
        "null_numeric_metric_count":dict(null_counts),
        "missing_native_correlated_event_ids":native_empty_count,
        "unique_native_correlated_event_id_year_pairs":len(native_event_ids),
        "candidate_repeated_county_time_event_keys":sum(v-1 for v in natural_keys.values() if v>1),
        "exact_duplicate_source_rows_within_same_table":exact_source_duplicate_rows,
        "cross_publication_year_episode_starts":dict(cross_year_starts),
        "durable_backend_indexed":0,"verified_insured_facility_outages":0,
        "verified_financial_claims":0,"deployed":0,
        "data_model_notes":[
            "The 10 source groups contain month=0 annual summary records, NOT 0th calendar month",
            "Correlated event rows repeat native event_id by county; not distinct events",
            "8h and 24h lag files are alternative sensitivity joins, not additional outages",
            "Time resolution and published duration do not establish insured building downtime",
            "County code is normalized five-digit FIPS, while original unpadded FIPS is preserved verbatim",
            "Source is historical study dataset, 2014-2023; not a real-time monitoring feed",
            "Published source years are dataset vintages; timezone of raw start_time not provided",
            "Raw observations and rejected records are staged in transient runner SQLite",
        ],
    }
    if accepted_total !=sum(s["accepted"] for s in stats):
        raise RuntimeError("Publisher count reconciliation mismatch")
    (output/"manifest.json").write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({key:receipt[key] for key in (
        "archive_sha256","archive_bytes","source_rows_scanned","accepted","rejected","rejection_reasons",
        "accepted_by_source_kind","locally_indexed","distinct_state_names","unique_county_fips",
        "earliest_recorded_county_episode","latest_recorded_county_episode",
        "candidate_repeated_county_time_event_keys",
        "exact_duplicate_source_rows_within_same_table",
        "unique_native_correlated_event_id_year_pairs")},indent=2))
    return receipt


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--zip",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    normalize(a.zip,a.output)


if __name__=="__main__":
    main()
