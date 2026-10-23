"""Lane D: official DOE OE-417 annual disturbance research source (historical, 2023 catalog).

Official public-domain DOE CESER electric incident annual data mirrored by ORNL
Open Energy Hub. Publisher OpenDataSoft dataset metadata explicitly states the
2023 publication is intended for data discovery, not a complete time-series.
These records are NOT independent of DOE-417-derived EIA EPM event summaries;
do not add their counts or infer a physical insured property outage.
The annual summary has NO native event ID; preserve dataset/row identity.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date,datetime,timezone
from decimal import Decimal,InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.request import Request,urlopen
from urllib.parse import urlparse

DATASET_ID="oe-417-annual-summaries"
BASE_URL="https://openenergyhub.ornl.gov/api/explore/v2.1/catalog/datasets/"+DATASET_ID
EXPORT_URL=BASE_URL+"/exports/json"
DATASET_PAGE="https://openenergyhub.ornl.gov/explore/dataset/"+DATASET_ID+"/"
MAX_EXPORT_BYTES=5_000_000
MAX_METADATA_BYTES=200_000
EXPECTED_FIELDS=(
    "event_month","date_event_began","time_event_began","date_of_restoration",
    "time_of_restoration","area_affected","nerc_region","alert_criteria",
    "event_type","demand_loss_mw","number_of_customers_affected",
)


def digest(blob:bytes)->str:
    return hashlib.sha256(blob).hexdigest()


def canonical(v)->bytes:
    return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")


def date_or_none(value,field,required=False):
    if value is None or value=="":
        if required:
            raise ValueError("missing_"+field)
        return None
    if not isinstance(value,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",value):
        raise ValueError("invalid_"+field)
    try:
        d=date.fromisoformat(value)
    except ValueError as e:
        raise ValueError("invalid_"+field) from e
    if not 2000<=d.year<=2026:
        raise ValueError("unsupported_"+field+"_year")
    return d.isoformat()


def optional_nonnegative(value,name):
    if value is None or value=="":
        return None
    if isinstance(value,bool):
        raise ValueError("invalid_"+name)
    try:
        d=Decimal(str(value))
    except InvalidOperation as e:
        raise ValueError("invalid_"+name) from e
    if not d.is_finite() or d<0:
        raise ValueError("invalid_"+name)
    if name=="number_of_customers_affected":
        if d!=d.to_integral_value():
            raise ValueError("invalid_"+name)
        return int(d)
    return str(d)


def metadata_license(obj):
    if not isinstance(obj,dict) or obj.get("dataset_id")!=DATASET_ID:
        raise ValueError("Official publisher annual metadata has wrong dataset ID")
    license_value=(obj.get("metas",{}).get("default",{}) or {}).get("license")
    if str(license_value).strip().lower()!="public domain":
        raise ValueError("Official DOE OE417 declared dataset license changed or missing")
    return str(license_value).strip()


def parse(records_blob:bytes,metas:dict):
    license=metadata_license(metas)
    try:
        rows=json.loads(records_blob.decode("utf-8-sig"))
    except (UnicodeDecodeError,json.JSONDecodeError) as e:
        raise ValueError("Invalid official annual DOE OE417 source export JSON") from e
    if not isinstance(rows,list) or not 1<=len(rows)<=20_000:
        raise ValueError("Annual DOE OE417 data must be a finite nonempty JSON array")
    accepted,rejected=[],[]
    first_by_fingerprint={}
    years,types,regions=Counter(),Counter(),Counter()
    missing_customer=missing_restore=missing_mw=missing_area=0
    has_numeric_customers=0
    for position,raw in enumerate(rows,start=1):
        source_sha=digest(canonical(raw))
        try:
            if not isinstance(raw,dict) or set(raw)!=set(EXPECTED_FIELDS):
                raise ValueError("source_schema_drift_or_row_not_object")
            event_date=date_or_none(raw["date_event_began"],"date_event_began",required=True)
            restoration=date_or_none(raw["date_of_restoration"],"date_of_restoration")
            customers=optional_nonnegative(raw["number_of_customers_affected"],"number_of_customers_affected")
            demand=optional_nonnegative(raw["demand_loss_mw"],"demand_loss_mw")
            raw_area=raw["area_affected"]
            raw_type=raw["event_type"]
            if raw_area is not None and not isinstance(raw_area,str):
                raise ValueError("invalid_area_affected_type")
            if raw_type is not None and not isinstance(raw_type,str):
                raise ValueError("invalid_event_type")
        except ValueError as e:
            rejected.append({
                "publisher_dataset_id":DATASET_ID,
                "source_original_json_position_1based":position,
                "original_row_sha256":source_sha,
                "reason":str(e),"original_row":raw,
            })
            continue
        first=first_by_fingerprint.get(source_sha)
        if first is None:
            first_by_fingerprint[source_sha]=position
        years[event_date[:4]]+=1
        types[str(raw_type or "NOT_REPORTED")]+=1
        regions[str(raw["nerc_region"] or "NOT_REPORTED")]+=1
        missing_customer+=int(customers is None)
        has_numeric_customers+=int(customers is not None)
        missing_restore+=int(restoration is None)
        missing_mw+=int(demand is None)
        missing_area+=int(not raw_area or not raw_area.strip())
        accepted.append({
            "source":"DOE_CESER_OE417_2023_DISCOVERY_CATALOG",
            "publisher":"DOE CESER, public-domain annual summary distributed by ORNL",
            "official_export_url":EXPORT_URL,
            "official_dataset_page":DATASET_PAGE,
            "source_license":license,
            "publisher_native_event_id":None,
            "native_event_id_available":False,
            "source_original_position_1based":position,
            "original_row_sha256":source_sha,
            "source_row_key":digest(canonical([DATASET_ID,position,source_sha])),
            "is_exact_duplicate_publisher_record":first is not None,
            "duplicate_of_source_position":first,
            "event_date_source":event_date,
            "restoration_date_source":restoration,
            "source_time_event_began":raw["time_event_began"],
            "source_time_restoration":raw["time_of_restoration"],
            "source_area_text":raw_area,
            "source_nerc_region":raw["nerc_region"],
            "source_event_type":raw_type,
            "source_alert_criteria":raw["alert_criteria"],
            "reported_customers_affected":customers,
            "reported_demand_loss_mw_decimal":demand,
            "publishing_year":event_date[:4],
            "publisher_source_grain":"ANNUAL_ELECTRIC_EMERGENCY_REPORT_ROW_NOT_INSURED_SITE",
            "site_electric_outage_verified":False,
            "site_utility_meter_verified":False,
            "insured_business_interruption_claim_confirmed":False,
            "original_source_row":raw,
        })
    if len(accepted)+len(rejected)!=len(rows):
        raise RuntimeError("Official publisher source row reconciliation failed")
    if not accepted:
        raise ValueError("All official OE417 source rows rejected")
    summary={
        "source_rows_downloaded":len(rows),
        "normalized_accepted":len(accepted),
        "rejected":len(rejected),
        "exact_duplicate_source_rows":sum(r["is_exact_duplicate_publisher_record"] for r in accepted),
        "content_distinct_accepted_publisher_rows":sum(not r["is_exact_duplicate_publisher_record"] for r in accepted),
        "source_calendar_year_counts":dict(years),
        "source_event_type_counts":dict(types),
        "source_nerc_regions":dict(regions),
        "missing_reported_customer_count":missing_customer,
        "numeric_reported_customer_count":has_numeric_customers,
        "missing_restoration_date":missing_restore,
        "missing_demand_mw":missing_mw,
        "missing_source_area_text":missing_area,
        "records_with_site_coordinates":0,
        "rejection_reasons":dict(Counter(r["reason"] for r in rejected)),
        "original_header":list(EXPECTED_FIELDS),
    }
    return accepted,rejected,summary


def run(original_json:Path,metadata_json:Path,output:Path,downloaded_official=False):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    raw=Path(original_json).read_bytes()
    meta=Path(metadata_json).read_bytes()
    if len(raw)>MAX_EXPORT_BYTES or len(meta)>MAX_METADATA_BYTES:
        raise ValueError("Official annual DOE source exceeded expected size bounds")
    metadata=json.loads(meta)
    accepted,rejected,stats=parse(raw,metadata)
    for name,rows in (("accepted.jsonl",accepted),("rejected.jsonl",rejected)):
        with (output/name).open("w",encoding="utf-8") as f:
            for item in rows:
                f.write(json.dumps(item,sort_keys=True,ensure_ascii=False)+"\n")
    with sqlite3.connect(output/"oe417_annual_staging.sqlite") as db:
        db.execute("""CREATE TABLE source_observations(
            source_row_key TEXT PRIMARY KEY,original_position INTEGER NOT NULL,
            event_date TEXT,restoration_date TEXT,source_area_text TEXT,
            source_event_type TEXT,source_nerc_region TEXT,
            source_alert_criteria TEXT,reported_customers INTEGER,
            reported_demand_mw_decimal TEXT,
            exact_duplicate_source INTEGER NOT NULL,duplicate_of_source_position INTEGER,
            original_row_sha256 TEXT NOT NULL,raw_json TEXT NOT NULL
        )""")
        db.executemany("INSERT INTO source_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",[
            (x["source_row_key"],x["source_original_position_1based"],
             x["event_date_source"],x["restoration_date_source"],
             x["source_area_text"],x["source_event_type"],x["source_nerc_region"],
             x["source_alert_criteria"],x["reported_customers_affected"],
             x["reported_demand_loss_mw_decimal"],
             int(x["is_exact_duplicate_publisher_record"]),x["duplicate_of_source_position"],
             x["original_row_sha256"],json.dumps(x["original_source_row"],sort_keys=True,ensure_ascii=False))
            for x in accepted
        ])
        db.execute("CREATE INDEX idx_event_date ON source_observations(event_date,source_event_type)")
        db.execute("CREATE INDEX idx_nerc_region ON source_observations(source_nerc_region,event_date)")
        db.commit()
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise RuntimeError("Official DOE source-only SQLite integrity failure")
        count=db.execute("SELECT COUNT(*) FROM source_observations").fetchone()[0]
        dupl=db.execute("SELECT COUNT(*) FROM source_observations WHERE exact_duplicate_source=1").fetchone()[0]
        if count!=len(accepted) or dupl!=stats["exact_duplicate_source_rows"]:
            raise RuntimeError("Annual OE417 source count/duplicate index mismatch")
    manifest={
        "source":"DOE_CESER_OE417_2023_ANNUAL_DISCOVERY",
        "official_dataset_page":DATASET_PAGE,
        "original_publisher_export_url":EXPORT_URL,
        "original_publisher_metadata_url":BASE_URL,
        "metadata_declared_license":metadata_license(metadata),
        "publisher_reported_vintage":"2023 only per portal description, validate observed year distribution",
        "downloaded_official_original_json":downloaded_official,
        "downloaded_original_export_bytes":len(raw),
        "downloaded_original_export_sha256":digest(raw),
        "metadata_original_bytes":len(meta),
        "metadata_original_sha256":digest(meta),
        "observed_download_utc":datetime.now(timezone.utc).isoformat(),
        "original_source_rows":len(accepted)+len(rejected),
        "normalized_accepted":len(accepted),
        "rejected":len(rejected),
        "indexed_temporary_sqlite_rows":count,
        "durable_backend_indexed":0,
        "deployed":0,
        "independently_confirmed_property_outages":0,
        "independently_confirmed_insured_business_interruption_claims":0,
        "statistics":stats,
        "restrictions":[
            "This separately distributed DOE OE-417 2023 annual summary overlaps EIA DOE-417-derived EPM disturbance tables. Do not add event counts across them.",
            "Publisher native unique emergency event/incident ID is absent; record positions are derived IDs, NOT source-native incident keys.",
            "Date/time, area and affected customers are self-reported aggregate emergency observations, not confirmed insured-site outages.",
            "No street address, meter identity or coordinates; area_affected is free text, no automatic physical site match.",
            "Public-domain license asserted in ORNL source metadata, attribution retained to DOE CESER and ORNL distribution.",
            "No production index, insurance coverage, downtime or paid claim verified.",
        ]
    }
    (output/"manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n")
    return manifest


def _download(url,maxbytes: int,folder:Path,name:str):
    origin=urlparse(url)
    if origin.scheme!="https" or origin.hostname!="openenergyhub.ornl.gov":
        raise ValueError("Unrecognized official ORNL publisher")
    with urlopen(Request(url,headers={"User-Agent":"FacilityRiskLaneD/1.0 published OE417 schema"}),timeout=70) as response:
        if response.status!=200 or response.geturl()!=url:
            raise ValueError("Original official ORNL DOE publication redirected unexpectedly")
        raw=response.read(maxbytes+1)
    if len(raw)>maxbytes:
        raise ValueError("Official source response exceeded size ceiling")
    path=folder/name;path.write_bytes(raw)
    return path


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source-json",type=Path)
    p.add_argument("--metadata-json",type=Path)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if (a.source_json is None)!=(a.metadata_json is None):
        raise ValueError("Either provide both original source+metadata files, or use official network")
    a.output.mkdir(parents=True,exist_ok=True)
    if a.source_json is None:
        meta=_download(BASE_URL,MAX_METADATA_BYTES,a.output,"original_metadata.json")
        original=_download(EXPORT_URL,MAX_EXPORT_BYTES,a.output,"original_export.json")
        is_live=True
    else:
        original=a.source_json
        meta=a.metadata_json
        is_live=False
    print(json.dumps(run(original,meta,a.output,downloaded_official=is_live),indent=2))


if __name__=="__main__":
    main()
