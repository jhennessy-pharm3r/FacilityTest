"""Public FRS-RMP interest registry lookup. Not an RMP plan or OCA API."""
import argparse
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import sqlite3

class InvalidRMPIndex(ValueError):pass
def _sha(path):
    digest=hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda:file.read(1048576),b""):digest.update(block)
    return digest.hexdigest()
@lru_cache(maxsize=8)
def _facts(directory,dbdev,dbino,dbsize,dbmtime,dbctime,metadev,metaind,metasize,metamtime,metactime,rawdev,rawino,rawsize,rawmtime,rawctime):
    base=Path(directory)
    db=base/"rmp_frs_public.sqlite"
    raw=base/"rmp_frs_public.raw.jsonl"
    manifest=json.loads((base/"rmp_frs_public.manifest.json").read_text())
    if (manifest.get("source")!="EPA FRS RMP program interest" or
        manifest.get("schema_version")!=2 or manifest.get("state")!="INDEXED" or
        manifest.get("deployment_state")!="NOT_DEPLOYED" or
        manifest.get("site_match_status")!="NOT_REVIEWED" or
        manifest.get("index_bytes")!=dbsize or
        not re.fullmatch(r"[a-fA-F0-9]{64}",manifest.get("index_sha256","")) or
        not re.fullmatch(r"[a-fA-F0-9]{64}",manifest.get("raw_jsonl_sha256","")) or
        _sha(db)!=manifest["index_sha256"] or _sha(raw)!=manifest["raw_jsonl_sha256"]):
        raise InvalidRMPIndex("FRS/RMP source-only manifest or hash validation failed")
    with sqlite3.connect(db.as_uri()+"?mode=ro&immutable=1",uri=True) as conn:
        tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "rmp_frs_public" not in tables or tables & {"facilities","evidence","insurance_terms","sec_findings"}:
            raise InvalidRMPIndex("Missing source-only table or unexpected private data")
        obs=conn.execute("SELECT COUNT(*) FROM rmp_frs_public").fetchone()[0]
        ids=conn.execute("SELECT COUNT(DISTINCT program_id) FROM rmp_frs_public").fetchone()[0]
        qc=conn.execute("PRAGMA quick_check").fetchone()[0]
        if (obs!=manifest.get("indexed_rows") or ids!=manifest.get("distinct_program_ids")
            or qc!="ok"):
            raise InvalidRMPIndex("Public RMP/FRS source-index counts disagree")
    return {"source":"EPA public FRS-RMP interests","index_state":"INDEXED_NOT_DEPLOYED",
            "records":obs,"distinct_program_ids":ids,
            "raw_jsonl_sha256":manifest["raw_jsonl_sha256"],
            "database_sha256":manifest["index_sha256"],
            "source_url":manifest["source_url"],
            "site_match_state":"NOT_REVIEWED",
            "notice":"Public program-interest list ONLY: no RMP plans, OCA, accident scenarios, verified properties or losses"}
def status(directory):
    base=Path(directory).expanduser().resolve()
    files=[base/"rmp_frs_public.sqlite",base/"rmp_frs_public.manifest.json",
           base/"rmp_frs_public.raw.jsonl"]
    if any(not f.is_file() for f in files):raise InvalidRMPIndex("All three official-source bundle files required")
    if (base/"rmp_frs_public.sqlite-wal").is_file() and (
        base/"rmp_frs_public.sqlite-wal").stat().st_size:
        raise InvalidRMPIndex("Uncheckpointed WAL in source-only snapshot")
    def fingerprint(p):
        st=p.stat()
        return (st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
    return _facts(str(base),*fingerprint(files[0]),*fingerprint(files[1]),*fingerprint(files[2]))
def lookup(directory,program_id,limit=50):
    if not isinstance(program_id,str) or not 1<=len(program_id.strip())<=160:
        raise ValueError("Exact native public RMP program ID required")
    if type(limit)!=int or not 1<=limit<=100:raise ValueError("Invalid limit")
    facts=status(directory)
    db=Path(directory).resolve()/"rmp_frs_public.sqlite"
    with sqlite3.connect(db.as_uri()+"?mode=ro&immutable=1",uri=True) as conn:
        conn.row_factory=sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        total=conn.execute("SELECT COUNT(*) FROM rmp_frs_public WHERE program_id=?",
                           (program_id.strip(),)).fetchone()[0]
        rows=conn.execute("SELECT * FROM rmp_frs_public WHERE program_id=? ORDER BY object_id LIMIT ?",
                          (program_id.strip(),limit)).fetchall()
        records=[dict(object_id=r["object_id"],registry_id=r["registry_id"],
                      program_id=r["program_id"],latitude=r["latitude"],
                      longitude=r["longitude"],reported_attributes=json.loads(r["attributes_json"]),
                      raw_sha256=r["raw_sha256"],location_verification="NOT_REVIEWED")
                 for r in rows]
    return {"source":facts["source"],"native_program_id":program_id,"observations_available":total,
            "records":records,"source_provenance":facts,
            "evidence_scope":"Public FRS RMP program association only; never an accident or consequence score"}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--directory",required=True)
    p.add_argument("--program-id",required=True)
    a=p.parse_args()
    print(json.dumps(lookup(a.directory,a.program_id),indent=2))
if __name__=="__main__":main()
