"""Lane D: authoritative public ORNL ODIN /odi county-level active outage snapshot.

Official non-authenticated publisher API: https://odin.ornl.gov/odi
Original source follows CIM-like event shape, with utility name/identifier
annotations (nameType == UtilityId/UtilityName) and nullable MRID. The public
source's county FIPS is *not* an insured physical facility location.

The public /odi source must NOT be added to the OpenEnergyHub ODIN mirror as
independent events, nor should two snapshots be added to count outages. Keep
native identifiers, raw rows, stable raw digest, and snapshot-specific keys.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urlparse
from urllib.request import Request, urlopen

SOURCE_URL="https://odin.ornl.gov/odi"
MAX_BYTES=15_000_000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(obj):
    return json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode("utf-8")


def tagged_names(names):
    """Publisher nameType and nameTypeAuthority keys retained, with EIA scope."""
    result={"EIA_UTILITY_ID":None,"EIA_UTILITY_NAME":None}
    if not isinstance(names,list):
        return result
    for item in names:
        if not isinstance(item,dict):
            continue
        name=str(item.get("name") or "").strip()
        if not name or str(item.get("nameTypeAuthority") or "").strip().upper()!="EIA":
            continue
        kind=item.get("nameType")
        if kind=="UtilityId" and result["EIA_UTILITY_ID"] is None:
            result["EIA_UTILITY_ID"]=name
        elif kind=="UtilityName" and result["EIA_UTILITY_NAME"] is None:
            result["EIA_UTILITY_NAME"]=name
    return result


def _parse_time(value):
    if value is None or value=="":
        return None
    if not isinstance(value,str):
        raise ValueError("invalid_reported_start_type")
    try:
        d=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError as e:
        raise ValueError("invalid_reported_start") from e
    if d.tzinfo is None or d.year<2000 or d>datetime.now(timezone.utc)+timedelta(days=1):
        raise ValueError("invalid_reported_start")
    return d.astimezone(timezone.utc).isoformat()


def affected_meters(value):
    if value is None or value=="":
        return None
    if isinstance(value,bool):
        raise ValueError("invalid_meters_affected")
    try:
        number=Decimal(str(value))
    except InvalidOperation as e:
        raise ValueError("invalid_meters_affected") from e
    if not number.is_finite() or number<0 or number!=number.to_integral_value():
        raise ValueError("invalid_meters_affected")
    return int(number)


def parse(raw_bytes, snapshot_utc):
    try:
        document=json.loads(raw_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError,json.JSONDecodeError) as e:
        raise ValueError("Invalid first-party ODIN JSON") from e
    if not isinstance(document,dict) or not isinstance(document.get("outage"),list):
        raise ValueError("Expected first-party CIM container with outage list")
    raw=document["outage"]
    if not raw or len(raw)>250_000:
        raise ValueError("Empty or unexpectedly large ODIN active county feed")
    accepted,rejected=[],[]
    exact_fingerprint_count=Counter()
    first_seen={}
    stats=Counter()
    kinds,utility_ids,county_fips,reported_dates=set(),set(),set(),[]
    mrid_count=Counter()
    for pos,source in enumerate(raw,start=1):
        row_hash=sha(canonical(source))
        try:
            if not isinstance(source,dict):
                raise ValueError("nonobject_outage")
            if not {"communityDescriptor","metersAffected","outageArea","names"}.issubset(source):
                raise ValueError("required_cim_fields_missing")
            county=source.get("communityDescriptor")
            if not isinstance(county,str) or not re.fullmatch(r"\d{5}",county) or county=="00000":
                raise ValueError("invalid_native_county_fips")
            area=source.get("outageArea")
            if not isinstance(area,dict) or area.get("outageAreaKind")!="county":
                raise ValueError("not_county_resolution")
            meters=affected_meters(source.get("metersAffected"))
            moment=_parse_time(source.get("reportedStartTime"))
            mrid_upper=source.get("MRID")
            mrid_lower=source.get("mrid")
            if mrid_upper is not None and not isinstance(mrid_upper,str):
                raise ValueError("invalid_native_mrid")
            if mrid_lower is not None and not isinstance(mrid_lower,str):
                raise ValueError("invalid_native_mrid")
            if mrid_upper is not None and mrid_lower is not None and mrid_upper!=mrid_lower:
                raise ValueError("conflicting_native_mrid_fields")
            native=mrid_upper if mrid_upper else mrid_lower if mrid_lower else None
            names=tagged_names(source.get("names"))
        except ValueError as e:
            rejected.append({
                "source_row_1based":pos,"reason":str(e),
                "original_row_sha256":row_hash,"original_row":source,
            })
            continue
        isdup=row_hash in first_seen
        previous=first_seen.get(row_hash)
        if not isdup:
            first_seen[row_hash]=pos
        exact_fingerprint_count[row_hash]+=1
        if native is None:
            stats["missing_native_mrid"]+=1
        else:
            mrid_count[native]+=1
        if names["EIA_UTILITY_ID"] is None:
            stats["missing_reported_eia_utility_id"]+=1
        else:
            utility_ids.add(names["EIA_UTILITY_ID"])
        if moment is None:
            stats["missing_reported_start"]+=1
        else:
            reported_dates.append(moment)
        if meters is None:
            stats["missing_affected_meter_count"]+=1
        if area.get("outageAreaKind"):
            kinds.add(area["outageAreaKind"])
        county_fips.add(county)
        accepted.append({
            "source":"DOE_ORNL_ODIN_DIRECT_PUBLIC_COUNTY",
            "publisher":"Oak Ridge National Laboratory / DOE",
            "publisher_source_url":SOURCE_URL,
            "source_row_1based":pos,
            "snapshot_utc":snapshot_utc,
            "source_native_MRID":mrid_upper,
            "source_native_mrid":mrid_lower,
            "source_native_county_fips":county,
            "source_utility_id_with_EIA_authority":names["EIA_UTILITY_ID"],
            "source_utility_name_with_EIA_authority":names["EIA_UTILITY_NAME"],
            "reported_meter_count_affected":meters,
            "reported_start_utc":moment,
            "reported_start_status":"UNKNOWN" if moment is None else "REPORTED",
            "source_row_sha256":row_hash,
            "source_row_key":sha(canonical([snapshot_utc,pos,row_hash])),
            "is_exact_duplicate_row_in_snapshot":isdup,
            "duplicate_of_source_row":previous,
            "source_observation_kind":"COUNTY_LEVEL_ACTIVE_UTILITY_STATUS",
            "native_event_id_available":native is not None,
            "native_event_id_unique_undetermined":True,
            "physical_site_outage_verified":False,
            "site_meter_account_verified":False,
            "insured_business_interruption_verified":False,
            "original_row":source,
        })
    if len(accepted)+len(rejected)!=len(raw) or not accepted:
        raise ValueError("ODIN native publisher row count failed reconciliation")
    observations=dict(stats)
    observations.update({
        "raw_source_rows_downloaded":len(raw),
        "accepted":len(accepted),
        "rejected":len(rejected),
        "distinct_native_county_fips":len(county_fips),
        "distinct_source_eia_utility_ids":len(utility_ids),
        "native_mrid_nonnull_rows":sum(mrid_count.values()),
        "distinct_nonnull_native_mrids":len(mrid_count),
        "repeated_nonnull_native_mrid_occurrences":sum(n-1 for n in mrid_count.values() if n>1),
        "exact_duplicate_source_rows_in_snapshot":sum(n-1 for n in exact_fingerprint_count.values() if n>1),
        "source_geographic_resolution_kinds":sorted(kinds),
        "first_reported_start":min(reported_dates) if reported_dates else None,
        "last_reported_start":max(reported_dates) if reported_dates else None,
        "reject_reasons":dict(Counter(r["reason"] for r in rejected)),
    })
    return accepted,rejected,observations


def run(path, output, official_https=False):
    path=Path(path);output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    original=path.read_bytes()
    if len(original)>MAX_BYTES:
        raise ValueError("Official direct ODIN JSON exceeds configured maximum")
    snapshot=datetime.now(timezone.utc).isoformat()
    accepted,rejected,stats=parse(original,snapshot)
    for name,rows in (("odin_direct_accepted.jsonl",accepted),("odin_direct_rejected.jsonl",rejected)):
        with (output/name).open("w",encoding="utf-8") as fd:
            for row in rows:
                fd.write(json.dumps(row,sort_keys=True,ensure_ascii=False)+"\n")
    db_path=output/"odin_direct_county_staging.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("""CREATE TABLE source_observations (
            source_row_key TEXT PRIMARY KEY,
            original_position INTEGER NOT NULL,
            native_mrid TEXT,
            native_county_fips TEXT NOT NULL,
            native_eia_utility_id TEXT,
            reported_start TEXT,
            meters_affected INTEGER,
            snapshot_utc TEXT NOT NULL,
            is_exact_duplicate INTEGER NOT NULL,
            duplicate_of_source_row INTEGER,
            original_row_sha256 TEXT NOT NULL,
            original_json TEXT NOT NULL
        )""")
        conn.executemany("INSERT INTO source_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [(r["source_row_key"],r["source_row_1based"],
              r["source_native_MRID"] or r["source_native_mrid"],r["source_native_county_fips"],
              r["source_utility_id_with_EIA_authority"],r["reported_start_utc"],
              r["reported_meter_count_affected"],r["snapshot_utc"],
              int(r["is_exact_duplicate_row_in_snapshot"]),r["duplicate_of_source_row"],
              r["source_row_sha256"],json.dumps(r["original_row"],sort_keys=True,ensure_ascii=False,
              separators=(",",":"))) for r in accepted])
        conn.execute("CREATE INDEX idx_odin_native_utility ON source_observations(native_eia_utility_id,native_county_fips)")
        conn.execute("CREATE INDEX idx_odin_native_mrid ON source_observations(native_mrid,native_county_fips)")
        conn.commit()
        if conn.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise ValueError("Native ODIN staging SQLite integrity failure")
        indexed=conn.execute("SELECT COUNT(*) FROM source_observations").fetchone()[0]
        marked_duplicates=conn.execute("SELECT COUNT(*) FROM source_observations WHERE is_exact_duplicate=1").fetchone()[0]
        if indexed!=len(accepted) or marked_duplicates!=stats["exact_duplicate_source_rows_in_snapshot"]:
            raise ValueError("ODIN source-versus-stage mismatch")
    manifest={
        "source":"DOE_ORNL_ODIN_DIRECT_NON_AUTH_COUNTY",
        "official_source_url":SOURCE_URL,
        "source_api_class":"ORNL_PUBLIC_NON_AUTHENTICATED_COUNTY",
        "download_utc":snapshot,
        "original_https_download":official_https,
        "original_raw_json_bytes":len(original),
        "original_raw_json_sha256":sha(original),
        "downloaded":len(accepted)+len(rejected),
        "normalized_accepted":len(accepted),
        "rejected":len(rejected),
        "indexed_ephemeral_local_sqlite":indexed,
        "durable_indexed":0,
        "deployed":0,
        "insured_facility_outages_verified":0,
        "insured_business_interruption_losses_verified":0,
        "source_schema_identity":{
            "native_outage_mrid":"original MRID/mrid; both preserved and may be NULL or repeat across counties",
            "native_utility_id":"names[nameType=UtilityId,nameTypeAuthority=EIA]",
            "native_county_id":"communityDescriptor (five-digit FIPS)",
            "source_snapshot_identity":"publisher HTTP body SHA256 + snapshot UTC + row position + raw row digest",
        },
        "observations":stats,
        "restrictions":[
            "Public ODIN county records are not property-level electrical service or actual insured-site outages",
            "A missing native MRID is unknown identity, not a missing outage; use publisher source position only within snapshot",
            "Same source outage may appear on OpenEnergyHub/ODIN mirror; never sum mirror and direct feed",
            "Different snapshots cannot be added as independent outage incidents",
            "Authenticated more-granular ODIN API was NOT accessed; requires ORNL approval",
            "Review applicable ORNL data redistribution terms before serving this dataset commercially",
        ],
    }
    (output/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    return manifest


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    if args.input is None:
        if urlparse(SOURCE_URL).hostname!="odin.ornl.gov":
            raise ValueError("Unexpected official source host")
        args.output.mkdir(parents=True,exist_ok=True)
        request=Request(SOURCE_URL,headers={"User-Agent":"FacilityRiskLaneD/1.0 public county provenance"})
        with urlopen(request,timeout=75) as resp:
            if resp.status!=200 or resp.geturl()!=SOURCE_URL:
                raise ValueError("First-party ODIN public URL changed or returned non-200")
            body=resp.read(MAX_BYTES+1)
        if len(body)>MAX_BYTES:
            raise ValueError("Publisher public source exceeds byte ceiling")
        source=args.output/"odin_direct_original.json"
        source.write_bytes(body)
        result=run(source,args.output,official_https=True)
    else:
        result=run(args.input,args.output)
    print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__=="__main__":
    main()
