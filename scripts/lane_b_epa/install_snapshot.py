"""Install a verified EPA Lane B source-only snapshot in a versioned private staging path.

No public serving, authentication, insured-site matching or deployment is done here.
The Lane E coordinator must separately approve and mount these immutable snapshots.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from datetime import datetime,timezone

from .chunk_index import restore,filehash
from .read_index import source_status

def prepare(source,archive,manifest_path,parts_dir,chunks_manifest,destination):
    if source not in ("echo","rcra"):
        raise ValueError("This installer only handles chunked national ECHO/RCRA indices")
    archive=Path(archive)
    manifest_path=Path(manifest_path)
    meta=json.loads(manifest_path.read_text(encoding="utf-8"))
    chunks=json.loads(Path(chunks_manifest).read_text(encoding="utf-8"))
    if (meta.get("source")!=source or chunks.get("source")!=source or
        meta.get("schema_version")!=2 or meta.get("state")!="INDEXED" or
        meta.get("deployment_state")!="NOT_DEPLOYED" or
        meta.get("archive_sha256")!=chunks.get("source_archive_sha256") or
        meta.get("index_sha256")!=chunks.get("sqlite_sha256") or
        meta.get("index_bytes")!=chunks.get("sqlite_bytes") or
        meta.get("indexed_rows")!=chunks.get("indexed_rows") or
        meta.get("rejected_rows")!=chunks.get("rejected_rows")):
        raise ValueError("Mismatched original source/index and release manifest")
    if not archive.is_file() or filehash(archive)!=meta["archive_sha256"]:
        raise ValueError("Original regulator archive missing or SHA-256 mismatch")
    dest=Path(destination).expanduser().resolve()
    if dest.exists():raise FileExistsError("Refusing overwrite of existing source snapshot")
    if not dest.parent.is_dir():raise FileNotFoundError("Private source parent directory must already exist")
    scratch=Path(tempfile.mkdtemp(prefix=".lane_b_staging_",dir=dest.parent))
    try:
        index=scratch/(source+".sqlite")
        result=restore(chunks_manifest,parts_dir,index)
        if not result["sqlite_sha256"]==meta["index_sha256"]:
            raise AssertionError("Source reassembly differs from signed-off importer manifest")
        copy=scratch/(source+".manifest.json")
        shutil.copyfile(manifest_path,copy)
        facts=source_status(index,copy,source)
        if facts["indexed_rows"]!=meta["indexed_rows"] or facts["rejected_rows"]!=meta["rejected_rows"]:
            raise AssertionError("Private source bundle count reconciliation failed")
        rawname="official-"+source+".zip"
        raw=scratch/rawname
        shutil.copyfile(archive,raw)
        if filehash(raw)!=meta["archive_sha256"]:
            raise AssertionError("Private source archive copy corrupt")
        receipt=dict(source=source,original_archive_sha256=meta["archive_sha256"],
                     source_sqlite_sha256=meta["index_sha256"],
                     official_source_rows=meta["scanned_rows"],
                     normalized_accepted=meta["accepted_rows"],
                     indexed_staging_rows=facts["indexed_rows"],
                     rejected_quarantined=facts["rejected_rows"],
                     published_vintage=meta.get("retrieved_utc"),
                     checked_at_utc=datetime.now(timezone.utc).isoformat(),
                     staging_state="VERIFIED_SOURCE_SNAPSHOT_READY_FOR_COORDINATOR_REVIEW",
                     authenticated_production_deployed=0,
                     physical_site_matches_approved=0,
                     notice="Private source snapshot staging only; requires Lane E auth, host, source-health and property review")
        (scratch/"install-receipt.json").write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
        for path in [index,copy,raw,scratch/"install-receipt.json"]:
            os.chmod(path,0o444)
        os.replace(scratch,dest)
        return receipt
    except Exception:
        shutil.rmtree(scratch,ignore_errors=True)
        raise

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",choices=["echo","rcra"],required=True)
    p.add_argument("--official-zip",required=True)
    p.add_argument("--manifest",required=True)
    p.add_argument("--parts-dir",required=True)
    p.add_argument("--chunks-manifest",required=True)
    p.add_argument("--destination",required=True)
    a=p.parse_args()
    print(json.dumps(prepare(a.source,a.official_zip,a.manifest,a.parts_dir,
        a.chunks_manifest,a.destination),indent=2))
if __name__=="__main__":main()
