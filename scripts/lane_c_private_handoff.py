"""Opt-in PRIVATE handoff of source originals, normalized records and SQLite.

Never write source rows or original PHMSA/NRC/CSB files to public Pages or
GitHub Actions artifacts. Caller must provide a secured *outside-repository*
filesystem mount. This is NOT an authenticated deployed service.
"""
from __future__ import annotations
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import hashlib

def sha(path):
    with Path(path).open("rb") as f:
        d=hashlib.sha256()
        for chunk in iter(lambda:f.read(1024*1024),b""):
            d.update(chunk)
        return d.hexdigest()

def private_bundle(database, normalized_sources, raw_sources, destination, *, repo_root=None):
    """normalized_sources: list[(key,gzip_path,manifest_path)], raw_sources: dict key->raw_path."""
    root=Path(repo_root or Path.cwd()).resolve()
    target=Path(destination).expanduser().resolve()
    if target.is_relative_to(root):
        raise ValueError("Private handoff must be outside the repository / public Pages workspace")
    if target.exists():
        raise ValueError("Private handoff directory exists; refusing to overwrite unreviewed originals")
    if not target.parent.exists() or not target.parent.is_dir():
        raise ValueError("Private handoff parent must be a pre-provisioned authorized mount")
    target.mkdir(mode=0o700)
    try:
        def copy_checked(src,relative,expected=None):
            src=Path(src)
            dest=target/relative
            dest.parent.mkdir(mode=0o700,exist_ok=True)
            shutil.copyfile(src,dest)
            dest.chmod(0o600)
            result=sha(dest)
            if expected and expected!=result:
                raise ValueError("Private bundle source checksum mismatch for "+relative)
            return {"sha256":result,"bytes":dest.stat().st_size}
        indexed=copy_checked(database,"indexes/lane-c-source.sqlite")
        with sqlite3.connect(target/"indexes/lane-c-source.sqlite") as db:
            quick=db.execute("PRAGMA quick_check").fetchone()[0]
            accepted=db.execute("SELECT COUNT(*) FROM source_incidents").fetchone()[0]
            candidates=db.execute("SELECT COUNT(*) FROM lane_c_review_candidates").fetchone()[0]
            if quick!="ok":
                raise ValueError("Private index content integrity FAILED")
        source_set={}
        for key,gz,manifest_path in normalized_sources:
            if key not in raw_sources:
                raise ValueError("Missing original source bytes for "+key)
            details=json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            normalized=copy_checked(gz,f"normalized/{key}.csv.gz",details["normalized_sha256"])
            raw=copy_checked(raw_sources[key],f"originals/{key}{Path(raw_sources[key]).suffix}",details["raw_sha256"])
            manifest=copy_checked(manifest_path,f"manifests/{key}.json")
            source_set[key]={"original":raw,"normalized":normalized,
                              "manifest":manifest,"accepted":details["accepted_rows"]}
        if accepted!=sum(x["accepted"] for x in source_set.values()):
            raise ValueError("Private source bundle row counts diverge from SQL index")
        summary={
            "state":"PRIVATE_LOCAL_HANDOFF_READY_NOT_AUTHENTICATED_OR_DEPLOYED",
            "created_at":datetime.now(timezone.utc).isoformat(),
            "source_namespaces":sorted(source_set),
            "source_counts":{k:v["accepted"] for k,v in source_set.items()},
            "total_source_rows":accepted,"review_candidate_pairs":candidates,
            "index_sha256":indexed["sha256"],"index_bytes":indexed["bytes"],
            "source_provenance":source_set,"sqlite_quick_check":quick,
            "private_mount_requires_encryption_access_control":True,
            "production_indexed":0,"app_deployed":0,
            "notice":"Handoff is a copy for coordinator; not a live service or insured property registry. Keep files private and configure auth, encryption, logging separately."
        }
        record=target/"private-bundle-manifest.json"
        record.write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
        record.chmod(0o600)
        return {"state":summary["state"],"source_count":len(source_set),
                "records_exported_to_private_local_bundle":accepted,
                "review_candidate_pairs":candidates,"index_sha256":indexed["sha256"],
                "sqlite_quick_check":quick,"production_indexed":0,"app_deployed":0}
    except BaseException:
        # A failed handoff must not leave partial PII/source extracts behind.
        shutil.rmtree(target,ignore_errors=True)
        raise
