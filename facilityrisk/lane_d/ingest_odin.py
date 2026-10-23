"""Lane D source-preserving public ORNL ODIN county outage snapshot importer.

Atomic public Open Energy Hub county-level JSON export, not a property/meter feed.
This is time-varying status evidence; source IDs and snapshot timestamp are kept
separately. Published area geometry is contextual, NOT the insured site location.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlparse
from urllib.request import Request, urlopen

SOURCE_URL = ("https://openenergyhub.ornl.gov/api/explore/v2.1/catalog/"
              "datasets/odin-real-time-outages-county/exports/json")
PAGE_URL = "https://openenergyhub.ornl.gov/explore/dataset/odin-real-time-outages-county/"
ALLOWED_HOST="openenergyhub.ornl.gov"
REQUIRED = ("utility_id","county","state","communitydescriptor","metersaffected",
            "reportedstarttime","statuskind")
MAX_BYTES=25_000_000


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def canonical(item):
    return json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def clean_numeric(value):
    if value is None or (isinstance(value,str) and value.strip() in ("","Unknown",".")):
        return None
    try:
        d=Decimal(str(value))
    except InvalidOperation:
        raise ValueError("Outage meter count not numeric")
    if not d.is_finite() or d<0 or d!=d.to_integral_value():
        raise ValueError("Outage meter count negative/non-integer/nonfinite")
    return int(d)


def parse(data, snapshot_utc):
    try:
        items = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError,json.JSONDecodeError) as e:
        raise ValueError("Invalid official JSON export") from e
    if not isinstance(items,list) or not items:
        raise ValueError("Public ODIN export is not a nonempty list")
    if len(items)>250_000:
        raise ValueError("Unexpectedly large ODIN public export")
    accepted,rejected=[],[]
    hashes=Counter()
    fips,countries,states=set(),set(),set()
    geography_null,geo_point_null,meters_null,status_counts=0,0,0,Counter()
    reported_times=[]
    for rownum, raw in enumerate(items, start=1):
        reason=None
        if not isinstance(raw,dict):
            reason="nonobject_record"
        elif not set(REQUIRED).issubset(raw):
            reason="missing_required_columns"
        else:
            id_ = str(raw["utility_id"] or "").strip()
            loc = str(raw["communitydescriptor"] or "").strip()
            state=str(raw["state"] or "").strip()
            county=str(raw["county"] or "").strip()
            started=str(raw["reportedstarttime"] or "").strip()
            if not id_:
                reason="missing_native_utility_id"
            elif not re.fullmatch(r"\d{5}",loc):
                reason="invalid_county_fips"
            elif not state or not county:
                reason="missing_county_or_state"
            else:
                try:
                    moment=datetime.fromisoformat(started.replace("Z","+00:00"))
                    if moment.tzinfo is None:
                        raise ValueError("No timezone in publisher timestamp")
                    if moment.year<2000 or moment>datetime.now(timezone.utc):
                        raise ValueError("Source date outside publication bounds")
                except ValueError:
                    reason="invalid_reported_start"
                if not reason:
                    try:
                        affected=clean_numeric(raw["metersaffected"])
                    except ValueError:
                        reason="invalid_affected_meter_count"
        digest=sha256(canonical(raw))
        if reason:
            rejected.append({"source_position":rownum,"source_row_sha256":digest,
                             "reason":reason,"raw":raw})
            continue
        hashes[digest]+=1
        fips.add(loc)
        states.add(state)
        status=str(raw.get("statuskind") or "")
        status_counts[status]+=1
        meters_null+=int(affected is None)
        geography_null+=int(raw.get("geom") is None)
        geo_point_null+=int(raw.get("geo_point_2d") is None)
        reported_times.append(moment.isoformat())
        incident=raw.get("incident")
        # ODIN incident may be nested or not globally unique. Preserve without inventing source event ID.
        native_incident_id = incident if isinstance(incident,(str,int)) and str(incident).strip() else None
        accepted.append({
            "source":"ORNL_ODIN_PUBLIC_COUNTY_OUTAGE",
            "source_dataset_url":PAGE_URL,
            "source_export_url":SOURCE_URL,
            "source_row_1based":rownum,
            "snapshot_utc":snapshot_utc,
            "native_utility_id":id_,
            "native_incident_id":native_incident_id,
            "native_county_fips":loc,
            "reported_state":state,
            "reported_county":county,
            "reported_start_time":started,
            "reported_status":status,
            "reported_meters_affected":affected,
            "source_record_sha256":digest,
            "source_row_key":sha256(canonical([snapshot_utc,rownum,digest])),
            "evidence_type":"COUNTY_LEVEL_PUBLIC_OUTAGE_STATUS",
            "geometry_scope":"COUNTY_PUBLISHER_CONTEXT_ONLY",
            "facility_identity_verified":False,
            "facility_outage_verified":False,
            "meter_account_verified":False,
            "business_interruption_verified":False,
            "raw":raw,
        })
    if not accepted:
        raise ValueError("No valid county outage records in public export")
    if len(rejected)+len(accepted)!=len(items):
        raise RuntimeError("ODIN snapshot reconciliation failed")
    return accepted,rejected,{
        "source_total_records":len(items),
        "accepted":len(accepted),
        "rejected":len(rejected),
        "rejection_reasons":dict(Counter(r["reason"] for r in rejected)),
        "distinct_county_fips":len(fips),
        "distinct_state_values":len(states),
        "states":sorted(states),
        "distinct_native_utility_ids":len({x["native_utility_id"] for x in accepted}),
        "exact_row_duplicate_fingerprints":sum(v-1 for v in hashes.values() if v>1),
        "missing_affected_meters":meters_null,
        "missing_publisher_geom":geography_null,
        "missing_publisher_geo_point":geo_point_null,
        "status_kind_counts":dict(status_counts),
        "earliest_reported_start":min(reported_times),
        "latest_reported_start":max(reported_times),
        "snapshot_time_type":"run_utc_observation",
    }


def run(path:Path, output:Path, expected_total=None, official_download=False):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    path=Path(path)
    data=path.read_bytes()
    if len(data)>MAX_BYTES:
        raise ValueError("ODIN raw public export exceeds size ceiling")
    snapshot=datetime.now(timezone.utc).isoformat()
    accepted,rejected,stats=parse(data,snapshot)
    if expected_total is not None and len(accepted)+len(rejected)!=expected_total:
        raise ValueError("Export record count mismatches independent official catalog total")
    for name,rows in (("accepted.jsonl",accepted),("rejected.jsonl",rejected)):
        with (output/name).open("w",encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")
    with sqlite3.connect(output/"odin_county_outage_staging.sqlite") as db:
        db.execute("""CREATE TABLE source_observations (
            source_row_key TEXT PRIMARY KEY, original_row_position INTEGER NOT NULL,
            native_utility_id TEXT, county_fips TEXT NOT NULL,
            reported_state TEXT, reported_county TEXT,
            reported_start_time TEXT, snapshot_utc TEXT,
            source_sha256 TEXT NOT NULL, raw_json TEXT NOT NULL
        )""")
        db.executemany("INSERT INTO source_observations VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(r["source_row_key"],r["source_row_1based"],r["native_utility_id"],
              r["native_county_fips"],r["reported_state"],r["reported_county"],
              r["reported_start_time"],r["snapshot_utc"],r["source_record_sha256"],
              json.dumps(r["raw"],ensure_ascii=False,sort_keys=True)) for r in accepted])
        db.execute("CREATE INDEX idx_odin_geography ON source_observations(county_fips,native_utility_id)")
        db.execute("CREATE INDEX idx_odin_time ON source_observations(reported_start_time)")
        db.commit()
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise RuntimeError("ODIN stage SQLite integrity check failed")
        idx_count=db.execute("SELECT count(*) FROM source_observations").fetchone()[0]
        if idx_count != len(accepted):
            raise RuntimeError("ODIN staging index mismatch")
    receipt={
        "source":"ORNL_ODIN_PUBLIC_COUNTY_OUTAGE",
        "source_url":SOURCE_URL,"source_publisher":"Oak Ridge National Laboratory",
        "snapshot_utc":snapshot, "raw_response_sha256":sha256(data),
        "raw_response_bytes":len(data),
        "input_source_kind":"official_https_download" if official_download else "local_source_copy",
        "downloaded_records":len(accepted)+len(rejected),
        "normalized_records":len(accepted),
        "rejected_records":len(rejected),
        "locally_indexed_records":idx_count,
        "durable_backend_indexed":0,"deployed":0,
        "site_outages_verified":0,"insured_business_interruption_verified":0,
        "qa":stats,
        "status":"PUBLIC_COUNTY_SNAPSHOT_LOCAL_STAGING_NOT_SITE_VERIFIED",
        "restrictions":[
            "Snapshot data are time-varying and must not be added across collection times",
            "County polygon and FIPS are context, not a physical facility geometry or meter link",
            "Number of meters affected is publisher-reported; not customer monetary loss",
            "No independent outage confirmation at a facility, no paid claims, no policy coverage",
            "Dataset use terms must be verified before redistribution",
        ],
    }
    (output/"manifest.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    return receipt


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--input",type=Path)
    p.add_argument("--expected-total",type=int)
    args=p.parse_args()
    if args.input:
        result=run(args.input,args.output,args.expected_total)
    else:
        if urlparse(SOURCE_URL).hostname!=ALLOWED_HOST:
            raise RuntimeError("Unapproved source host")
        args.output.mkdir(parents=True,exist_ok=True)
        source=args.output/"odin_official_snapshot.json"
        request=Request(SOURCE_URL,headers={"User-Agent":"FacilityRiskLaneD/1.0 official-public snapshot"})
        with urlopen(request,timeout=75) as response:
            if response.status!=200 or response.geturl()!=SOURCE_URL:
                raise RuntimeError("Publisher snapshot HTTP status or redirect changed")
            payload=response.read(MAX_BYTES+1)
        if len(payload)>MAX_BYTES:
            raise RuntimeError("Official ODIN snapshot exceeds configured maximum")
        source.write_bytes(payload)
        result=run(source,args.output,args.expected_total,official_download=True)
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
