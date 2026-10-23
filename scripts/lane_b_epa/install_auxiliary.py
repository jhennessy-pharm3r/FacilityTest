"""Fail-closed private *staging* of official TRI annual and public RMP identity bundles.

Never installs into the writable insured workspace, starts a server, or claims DEPLOYED.
Lane E supplies private authenticated hosting, tenant isolation and physical-site review.
"""
import argparse
from datetime import datetime,timezone
import gzip
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from .read_index import lookup,source_status
from .rmp_lookup import status as rmp_status
from .chunk_index import filehash

def _stage_dir(destination):
    dest=Path(destination).expanduser().resolve()
    if dest.exists():raise FileExistsError("Refusing to overwrite any versioned source bundle")
    if not dest.parent.is_dir():raise FileNotFoundError("Private parent directory must already exist")
    return dest,Path(tempfile.mkdtemp(prefix=".lane_b_aux_",dir=dest.parent))

def _seal(stage,dest,receipt):
    (stage/"install-receipt.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    for path in stage.iterdir():
        if path.is_file():os.chmod(path,0o444)
    os.replace(stage,dest)
    return receipt

def install_tri_year(year,official_csv,compressed_sqlite,manifest_path,destination):
    if type(year)!=int or not 1987<=year<=2024:raise ValueError("Published TRI Basic reporting year 1987-2024 required")
    raw=Path(official_csv);gz=Path(compressed_sqlite);meta=Path(manifest_path)
    if not all(p.is_file() for p in (raw,gz,meta)):raise FileNotFoundError("Original CSV, indexed gzip and matching manifest required")
    m=json.loads(meta.read_text())
    source_url="https://data.epa.gov/efservice/downloads/tri/mv_tri_basic_download/"+str(year)+"_US/csv"
    if (m.get("source")!="tri" or m.get("schema_version")!=2 or
        m.get("year")!=year or m.get("source_url")!=source_url or
        m.get("state")!="INDEXED" or m.get("deployment_state")!="NOT_DEPLOYED" or
        m.get("indexed_rows")!=m.get("accepted_rows") or
        m.get("scanned_rows")!=m.get("accepted_rows",0)+m.get("rejected_rows",0) or
        m.get("indexed_rows",0)<=0):
        raise ValueError("Wrong TRI source vintage or incomplete original source manifest")
    if filehash(raw)!=m.get("archive_sha256"):raise ValueError("Official original TRI CSV SHA256 mismatch")
    dest,stage=_stage_dir(destination)
    try:
        raw_copy=stage/("official-tri-"+str(year)+".csv")
        shutil.copyfile(raw,raw_copy)
        with gzip.open(gz,"rb") as src,(stage/"tri.sqlite").open("wb") as out:
            shutil.copyfileobj(src,out,length=1024*1024)
        manifest=stage/"tri.manifest.json"
        shutil.copyfile(meta,manifest)
        result=source_status(stage/"tri.sqlite",manifest,"tri")
        if result["indexed_rows"]!=m["accepted_rows"] or filehash(raw_copy)!=m["archive_sha256"]:
            raise ValueError("Independent TRI source-identity provenance check failed")
        import sqlite3
        with sqlite3.connect((stage/"tri.sqlite").as_uri()+"?mode=ro&immutable=1",uri=True) as db:
            rows=db.execute("SELECT json_extract(payload,'$.1_YEAR'),COUNT(*) FROM observation GROUP BY 1").fetchall()
            sample=db.execute("SELECT source_id FROM observation LIMIT 1").fetchone()
        if rows!=[(str(year),m["indexed_rows"])] or not sample:
            raise ValueError("Stored official TRI reporting-year content mismatch")
        query=lookup(stage/"tri.sqlite",manifest,"tri",sample[0],limit=2)
        if not query["observations_available"] or query["rows"][0]["source_reported_findings"]["reporting_year"]!=str(year):
            raise ValueError("Native TRI ID source lookup failed")
        receipt=dict(source="EPA TRI Basic",year=year,
            source_url=source_url,source_original_sha256=m["archive_sha256"],
            source_sqlite_sha256=m["index_sha256"],original_source_rows=m["scanned_rows"],
            accepted_normalized_rows=m["accepted_rows"],rejected_rows=m["rejected_rows"],
            private_staged_index_rows=m["indexed_rows"],
            validated_native_TRIFD_sample_sha256=__import__("hashlib").sha256(sample[0].encode()).hexdigest(),
            checked_at_utc=datetime.now(timezone.utc).isoformat(),
            staging_state="VERIFIED_READ_ONLY_SOURCE_SNAPSHOT_NOT_DEPLOYED",
            production_deployed=0,verified_insured_property_links=0,
            notice="Chemical report/year records, not distinct sites; source-only immutable staging.")
        return _seal(stage,dest,receipt)
    except Exception:
        shutil.rmtree(stage,ignore_errors=True)
        raise

def install_public_rmp(original_jsonl,sqlite_index,manifest_path,destination):
    original=Path(original_jsonl);index=Path(sqlite_index);meta=Path(manifest_path)
    if not all(p.is_file() for p in (original,index,meta)):
        raise FileNotFoundError("Public EPA FRS-RMP JSONL, SQLite and matching manifest required")
    m=json.loads(meta.read_text())
    if (m.get("source")!="EPA FRS RMP program interest" or
        m.get("schema_version")!=2 or m.get("state")!="INDEXED" or
        m.get("deployment_state")!="NOT_DEPLOYED" or
        m.get("reported_feature_count")!=m.get("indexed_rows") or
        m.get("indexed_rows",0)<=0 or m.get("object_id_coverage")!=m.get("indexed_rows")):
        raise ValueError("Public RMP index manifest mismatches official source")
    if filehash(original)!=m.get("raw_jsonl_sha256") or filehash(index)!=m.get("index_sha256"):
        raise ValueError("Original EPA public RMP source or SQLite SHA256 mismatch")
    dest,stage=_stage_dir(destination)
    try:
        shutil.copyfile(original,stage/"rmp_frs_public.raw.jsonl")
        shutil.copyfile(index,stage/"rmp_frs_public.sqlite")
        shutil.copyfile(meta,stage/"rmp_frs_public.manifest.json")
        facts=rmp_status(stage)
        if facts["records"]!=m["indexed_rows"] or facts["distinct_program_ids"]!=m["distinct_program_ids"]:
            raise ValueError("Public RMP native program IDs not reconciled")
        import sqlite3
        with sqlite3.connect((stage/"rmp_frs_public.sqlite").as_uri()+"?mode=ro&immutable=1",uri=True) as db:
            sample=db.execute("SELECT program_id FROM rmp_frs_public WHERE program_id<>'' LIMIT 1").fetchone()
        if not sample:raise ValueError("No public RMP program identifier")
        from .rmp_lookup import lookup
        query=lookup(stage,sample[0],limit=2)
        if query["observations_available"]<=0:raise ValueError("Public RMP exact native program lookup failed")
        receipt=dict(source="EPA public FRS-RMP program interests",
            source_url=m["source_url"],
            original_source_sha256=m["raw_jsonl_sha256"],source_sqlite_sha256=m["index_sha256"],
            original_source_rows=m["reported_feature_count"],
            accepted_normalized_rows=m["indexed_rows"],rejected_rows=0,
            private_staged_index_rows=m["indexed_rows"],
            distinct_native_program_ids=facts["distinct_program_ids"],
            checked_at_utc=datetime.now(timezone.utc).isoformat(),
            staging_state="VERIFIED_PUBLIC_REGISTRY_SOURCE_SNAPSHOT_NOT_DEPLOYED",
            production_deployed=0,verified_insured_property_links=0,
            scope_notice="Public RMP program registry only. No restricted RMP plans/OCA, property or accident outcomes.")
        return _seal(stage,dest,receipt)
    except Exception:
        shutil.rmtree(stage,ignore_errors=True)
        raise

def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="source",required=True)
    tri=sub.add_parser("tri")
    tri.add_argument("--year",type=int,required=True)
    tri.add_argument("--official-csv",required=True)
    tri.add_argument("--index-gz",required=True)
    tri.add_argument("--manifest",required=True)
    tri.add_argument("--destination",required=True)
    rmp=sub.add_parser("rmp-public")
    rmp.add_argument("--original-jsonl",required=True)
    rmp.add_argument("--index",required=True)
    rmp.add_argument("--manifest",required=True)
    rmp.add_argument("--destination",required=True)
    args=parser.parse_args()
    result=(install_tri_year(args.year,args.official_csv,args.index_gz,args.manifest,args.destination)
            if args.source=="tri" else
            install_public_rmp(args.original_jsonl,args.index,args.manifest,args.destination))
    print(json.dumps(result,indent=2))
if __name__=="__main__":main()
