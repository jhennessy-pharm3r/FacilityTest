"""Lane D: public ORNL ODIN utility feed participation / freshness inventory.

Official non-authenticated publisher endpoint https://odin.ornl.gov/odi/status.
One row is a *feed data status* for a utility or provider, not an insured
property, individual outage or insurance claim. Original dataId/eiaId and
status/source timestamps are stored separately; no outage feed URL is followed.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib, json, re, sqlite3
from pathlib import Path
from urllib.request import Request,urlopen
SOURCE_URL="https://odin.ornl.gov/odi/status"
MAX_BYTES=2_000_000


def digest(value):
    return hashlib.sha256(value).hexdigest()


def raw_signature(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")


def parse(blob,snapshot_time):
    try:
        rows=json.loads(blob.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as e:
        raise ValueError("Bad ODIN utility status JSON") from e
    if not isinstance(rows,list) or len(rows)>25_000 or len(rows)==0:
        raise ValueError("ODIN utility status must be a finite non-empty array")
    accepted,rejected=[],[]
    duplicates=Counter()
    first_seen={}
    errors=Counter()
    eia_ids=set()
    missing_id=0
    for position,raw in enumerate(rows,start=1):
        hashed=digest(raw_signature(raw))
        if not isinstance(raw,dict):
            rejected.append({"source_row":position,"reason":"invalid_record","raw_sha256":hashed,"original":raw})
            continue
        source_id=raw.get("dataId")
        source_id=str(source_id).strip() if source_id is not None else ""
        if not source_id:
            rejected.append({"source_row":position,"reason":"missing_native_data_id","raw_sha256":hashed,"original":raw})
            continue
        eid=raw.get("eiaId")
        eid=str(eid).strip() if eid is not None and str(eid).strip() else None
        total=raw.get("totalOutages")
        if total is not None and str(total).strip():
            try:
                n=Decimal(str(total))
                if not n.is_finite() or n<0 or n!=n.to_integral_value():
                    raise ValueError
                outages=int(n)
            except (InvalidOperation,ValueError):
                rejected.append({"source_row":position,"reason":"invalid_outage_count","raw_sha256":hashed,"original":raw})
                continue
        else:
            outages=None
        if eid is not None:
            eia_ids.add(eid)
        else:
            missing_id+=1
        previous=first_seen.get(hashed)
        if previous is None:
            first_seen[hashed]=position
        duplicates[hashed]+=1
        has_error=raw.get("hasError")
        errors[str(has_error)]+=1
        accepted.append({
            "source":"ORNL_ODIN_PUBLIC_FEED_STATUS",
            "source_url":SOURCE_URL,"source_row":position,
            "snapshot_time_utc":snapshot_time,
            "native_data_id":source_id,
            "source_eia_utility_id":eid,
            "reported_utility_name":raw.get("name"),
            "reported_data_resolution":raw.get("dataResolution"),
            "reported_received_date":raw.get("receivedDate"),
            "reported_has_error":has_error,
            "reported_total_outages":outages,
            "original_sha256":hashed,
            "source_row_key":digest(raw_signature([snapshot_time,position,hashed])),
            "duplicate_of_source_row":previous,
            "source_kind":"PUBLISHER_FEED_HEALTH_NOT_UTILITY_TERRITORY",
            "insured_site_utility_assignment_verified":False,
            "insured_site_outage_verified":False,
            "source_original":raw,
        })
    stats={
        "downloaded_rows":len(rows),"normalized":len(accepted),"rejected":len(rejected),
        "rejection_reasons":dict(Counter(x["reason"] for x in rejected)),
        "distinct_native_data_ids":len(set(x["native_data_id"] for x in accepted)),
        "distinct_native_eia_utility_ids":len(eia_ids),
        "missing_eia_utility_ids":missing_id,
        "exact_source_row_duplicates":sum(x-1 for x in duplicates.values() if x>1),
        "publisher_has_error_flag_values":dict(errors),
        "null_reported_receive_timestamps":sum(x["reported_received_date"] in (None,"") for x in accepted),
        "null_reported_total_outages":sum(x["reported_total_outages"] is None for x in accepted),
    }
    if len(accepted)+len(rejected)!=len(rows) or not accepted:
        raise ValueError("Source utility feed status row reconciliation failed")
    return accepted,rejected,stats


def run(path,output,official=False):
    path=Path(path);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    original=path.read_bytes()
    if len(original)>MAX_BYTES:
        raise ValueError("Official ODIN status source exceeds configured byte ceiling")
    snapshot=datetime.now(timezone.utc).isoformat()
    accepted,rejected,stats=parse(original,snapshot)
    for name,records in (("accepted.jsonl",accepted),("rejected.jsonl",rejected)):
        with (output/name).open("w",encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r,sort_keys=True,ensure_ascii=False)+"\n")
    with sqlite3.connect(output/"odin_utility_status_staging.sqlite") as db:
        db.execute("""CREATE TABLE utility_feeds(
            row_key TEXT PRIMARY KEY,
            native_data_id TEXT NOT NULL,
            native_eia_id TEXT,
            publisher_received_date TEXT,
            publisher_has_error TEXT,
            publisher_total_outages INTEGER,
            source_row INTEGER NOT NULL,
            source_sha256 TEXT NOT NULL,
            raw_json TEXT NOT NULL
        )""")
        db.executemany("INSERT INTO utility_feeds VALUES (?,?,?,?,?,?,?,?,?)",
            [(r["source_row_key"],r["native_data_id"],r["source_eia_utility_id"],
              r["reported_received_date"],str(r["reported_has_error"]),
              r["reported_total_outages"],r["source_row"],r["original_sha256"],
              json.dumps(r["source_original"],ensure_ascii=False,sort_keys=True)) for r in accepted])
        db.execute("CREATE INDEX idx_source_eia ON utility_feeds(native_eia_id,native_data_id)")
        db.commit()
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise ValueError("ODIN utility feed health SQLite integrity error")
        count=db.execute("SELECT COUNT(*) FROM utility_feeds").fetchone()[0]
        if count!=len(accepted):
            raise ValueError("Staging counts mismatch")
    manifest={
        "source":"ORNL_ODIN_PUBLIC_PARTICIPANT_FEED_STATUS",
        "source_url":SOURCE_URL,
        "original_publisher_http":official,
        "downloaded_source_bytes":len(original),
        "downloaded_source_sha256":digest(original),
        "observed_utc":snapshot,
        "records_downloaded":len(accepted)+len(rejected),
        "normalized_accepted":len(accepted),
        "rejected":len(rejected),
        "indexed_local_sqlite":count,
        "verified_insured_site_utility_assignments":0,
        "durable_backend_indexed":0,
        "deployed":0,
        "statistics":stats,
        "limitations":[
            "Lists publisher utility feed status and reporting resolution; does not establish electric service for any insured facility",
            "Publisher totalOutages counts are utility-reported status, not insured electric claims or distinct physical sites",
            "hasError/receivedDate must be shown as source freshness or uncertainty; a feed record does not prove current coverage",
            "No links in outageFeed followed or authenticated ODIN access attempted",
        ],
    }
    (output/"manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return manifest


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    if args.input is None:
        args.output.mkdir(parents=True,exist_ok=True)
        with urlopen(Request(SOURCE_URL,headers={"User-Agent":"FacilityRiskLaneD/1.0 public participant status"}),timeout=70) as r:
            if r.status!=200 or r.geturl()!=SOURCE_URL:
                raise ValueError("Original ORNL utility-status publisher endpoint changed")
            payload=r.read(MAX_BYTES+1)
        if len(payload)>MAX_BYTES:
            raise ValueError("Original ORNL utility-status response too large")
        source=args.output/"odin_status_original.json"
        source.write_bytes(payload)
        result=run(source,args.output,official=True)
    else:
        result=run(args.input,args.output)
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
