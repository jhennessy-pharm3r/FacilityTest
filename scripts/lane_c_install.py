"""Install Lane C verified PRIVATE handoff into a versioned read-only source index.

The bundle comes from scripts/lane_c_private_handoff.py on an explicitly
authorized private filesystem. It MUST NOT be hosted on GitHub Pages.
No unauthenticated HTTP service is provided. Lane E owns authentication,
tenant authorization, property review, API exposure and actual deployment.

Installation creates a never-overwritten release and atomically updates a
small active-release.json pointer ONLY AFTER checksums, SQLite integrity and
source counts pass. Previous releases remain available for rollback.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import tempfile
from urllib.parse import quote

SOURCE_PATTERN = re.compile(r"(?:nrc_20[0-9]{2}|csb)\Z")
RELEASE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")
EXPECTED_TABLE_COLUMNS = {
    "source","source_id","publisher_native_id","source_vintage",
    "incident_date","city","state","latitude","longitude",
    "evidence_status","site_link_status","source_url","source_json"
}

def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def _safe_file(root,relative):
    root = Path(root).resolve()
    rel = Path(relative)
    if rel.is_absolute() or any(x in ("..","") for x in rel.parts):
        raise ValueError("Unsafe private bundle relative file path")
    path = root / rel
    if any(p.is_symlink() for p in [path,*list(path.parents)[:len(rel.parts)] ]):
        raise ValueError("Symlinks not permitted in private source bundles")
    if not path.resolve().is_relative_to(root):
        raise ValueError("Private bundle path escapes its release root")
    if not path.is_file() or not path.stat().st_size:
        raise ValueError("Private bundle file missing/empty: "+str(rel))
    return path

def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def _readonly_db(path):
    uri = "file:" + quote(str(Path(path).resolve()), safe="/") + "?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    db.execute("PRAGMA query_only=ON")
    return db

def verify_bundle(bundle):
    """Fail closed on missing/tampered originals, normalized data or index."""
    bundle = Path(bundle).resolve()
    if not bundle.is_dir():
        raise ValueError("Private source bundle directory missing")
    manifest = _read_json(_safe_file(bundle,"private-bundle-manifest.json"))
    if manifest.get("state")!="PRIVATE_LOCAL_HANDOFF_READY_NOT_AUTHENTICATED_OR_DEPLOYED":
        raise ValueError("Unrecognized Lane C private source handoff state")
    if manifest.get("production_indexed")!=0 or manifest.get("app_deployed")!=0:
        raise ValueError("Input handoff misrepresents actual deployed stage")
    declared = manifest.get("source_counts")
    provenance = manifest.get("source_provenance")
    if not isinstance(declared,dict) or not isinstance(provenance,dict):
        raise ValueError("Source namespace manifests required for installation")
    if (set(declared)!=set(provenance) or
        len(declared)<1 or
        set(declared)!=set(manifest.get("source_namespaces",[])) or
        any(not SOURCE_PATTERN.fullmatch(x) for x in declared)):
        raise ValueError("Manifest source namespace coverage/format invalid")

    verified_sources = {}
    count = 0
    for name in sorted(declared):
        record = provenance[name]
        if not isinstance(record,dict):
            raise ValueError("Missing source provenance record")
        manifest_file = _safe_file(bundle,"manifests/"+name+".json")
        source_manifest = _read_json(manifest_file)
        expected_sha = record.get("manifest",{}).get("sha256")
        if not expected_sha or file_sha256(manifest_file)!=expected_sha:
            raise ValueError("Source manifest SHA mismatch: "+name)
        if (source_manifest.get("accepted_rows")!=declared[name] or
            declared[name]<=0 or record.get("accepted")!=declared[name]):
            raise ValueError("Source accepted count mismatches handoff: "+name)
        raw_matches = sorted((bundle/"originals").glob(name+".*"))
        if len(raw_matches)!=1:
            raise ValueError("Must have exactly one original first-party file: "+name)
        paths = {
            "original":_safe_file(bundle,raw_matches[0].relative_to(bundle)),
            "normalized":_safe_file(bundle,"normalized/"+name+".csv.gz")
        }
        for kind,path in paths.items():
            declared_hash=record.get(kind,{}).get("sha256")
            source_hash=source_manifest.get("raw_sha256" if kind=="original" else "normalized_sha256")
            if not declared_hash or declared_hash!=source_hash or file_sha256(path)!=declared_hash:
                raise ValueError("Private original/normalized provenance checksum failed: "+name+" "+kind)
        verified_sources[name]=int(declared[name])
        count+=int(declared[name])

    index = _safe_file(bundle,"indexes/lane-c-source.sqlite")
    if file_sha256(index)!=manifest.get("index_sha256"):
        raise ValueError("SQLite index SHA mismatch")
    with _readonly_db(index) as db:
        if db.execute("PRAGMA quick_check").fetchone()[0]!="ok":
            raise ValueError("Read-only source index SQLite quick_check failure")
        cols={x[1] for x in db.execute("PRAGMA table_info(source_incidents)")}
        if not EXPECTED_TABLE_COLUMNS.issubset(cols):
            raise ValueError("Unknown source index schema, columns missing")
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='lane_c_review_candidates'").fetchone():
            raise ValueError("Missing reviewer-only cross-source candidate table")
        actual=dict(db.execute("SELECT source,COUNT(*) FROM source_incidents GROUP BY source"))
        if actual!=verified_sources:
            raise ValueError("Normalized source counts do not match index")
        total=sum(actual.values())
        candidates=db.execute("SELECT COUNT(*) FROM lane_c_review_candidates").fetchone()[0]
        if total!=manifest.get("total_source_rows") or total!=count:
            raise ValueError("Installed source count does not reconcile")
        if candidates!=manifest.get("review_candidate_pairs"):
            raise ValueError("Candidate-only review count differs from manifest")
        violations=db.execute("""SELECT COUNT(*) FROM source_incidents
                                WHERE site_link_status <> 'candidate_only_not_matched'""").fetchone()[0]
        if violations:
            raise ValueError("Disallowed automatic site match in private index")
        reviews=db.execute("""SELECT COUNT(*) FROM lane_c_review_candidates
             WHERE status <> 'review_candidate_not_corrob'""").fetchone()[0]
        if reviews:
            raise ValueError("Source reviewer candidates automatically promoted")
        sample={}
        for name,expected in actual.items():
            row=db.execute("""SELECT source_id,source_vintage,incident_date,site_link_status
                              FROM source_incidents WHERE source=? LIMIT 1""",(name,)).fetchone()
            if not row or row[3]!="candidate_only_not_matched":
                raise ValueError("Read-only source query failed: "+name)
            sample[name]={"indexed_rows":expected,"query":"PASS"}
    return {
        "validation":"PASS","source_counts":verified_sources,
        "index_sha256":manifest["index_sha256"],
        "total_indexed_source_observations":count,
        "review_candidate_pairs":candidates,
        "sqlite_quick_check":"ok",
        "source_index_read_only_query":"PASS",
        "physical_insured_sites_verified":0,
        "app_deployed_records":0
    }

def _store_root(path,repo_root):
    root=Path(path).expanduser().resolve()
    repo=Path(repo_root).resolve()
    if root.is_relative_to(repo):
        raise ValueError("Private install root must be outside repository and GitHub Pages")
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Use a pre-provisioned, non-symlink private installation directory")
    if stat.S_IMODE(root.stat().st_mode) & 0o007:
        raise ValueError("Private install root must not be accessible to other users")
    return root

def _active(root):
    pointer=root/"active-release.json"
    if not pointer.exists():
        return None
    if pointer.is_symlink():
        raise ValueError("Active release manifest must not be a symbolic link")
    data=_read_json(pointer)
    if not RELEASE_PATTERN.fullmatch(data.get("release_id","")):
        raise ValueError("Invalid current active release ID")
    return data

def _write_active(root,payload):
    fd,temp=tempfile.mkstemp(prefix=".active-release-",suffix=".json",dir=root)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(payload,stream,indent=2,sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp,0o600)
        os.replace(temp,root/"active-release.json")
    finally:
        Path(temp).unlink(missing_ok=True)

def install(bundle,store_root,*,release_id=None,repo_root=None):
    root=_store_root(store_root,repo_root or Path(__file__).resolve().parents[1])
    source=Path(bundle).expanduser().resolve()
    if source.is_relative_to(root):
        raise ValueError("Do not install from inside the target release store")
    proven=verify_bundle(source)
    release_id=release_id or (
        datetime.now(timezone.utc).strftime("%Y%m%d") + "-" + proven["index_sha256"][:12])
    if not RELEASE_PATTERN.fullmatch(release_id) or release_id.startswith("."):
        raise ValueError("Unsafe release name")
    releases=root/"releases"
    releases.mkdir(mode=0o700,exist_ok=True)
    target=releases/release_id
    if target.exists():
        current=verify_bundle(target)
        if current["index_sha256"]!=proven["index_sha256"]:
            raise ValueError("An immutable release ID already exists with different source data")
        # Idempotent only when source data are unchanged, never overwrite.
        result={"installation":"ALREADY_INSTALLED_CHECKSUM_VERIFIED","release_id":release_id,**current}
    else:
        staging=Path(tempfile.mkdtemp(prefix=".staging-",dir=releases))
        try:
            for source_file in source.rglob("*"):
                if source_file.is_symlink():
                    raise ValueError("Source bundle symlinks forbidden")
                if not source_file.is_file():
                    continue
                relative=source_file.relative_to(source)
                output=staging/relative
                output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                shutil.copyfile(source_file,output)
                output.chmod(0o600)
            installed=verify_bundle(staging)
            if installed["index_sha256"]!=proven["index_sha256"]:
                raise ValueError("Original and installed index checksum mismatch")
            # A completed release is immutable to accidental service writes.
            # Administrators can install a NEW release or roll back the pointer.
            for installed_file in staging.rglob("*"):
                if installed_file.is_file():
                    installed_file.chmod(0o400)
            for installed_dir in sorted(
                    [p for p in staging.rglob("*") if p.is_dir()],
                    key=lambda p:len(p.parts),reverse=True):
                installed_dir.chmod(0o500)
            staging.chmod(0o500)
            staging.rename(target)
            result={"installation":"PRIVATE_RELEASE_INSTALLED_READ_ONLY_NOT_APP_DEPLOYED",
                    "release_id":release_id,**installed}
        except BaseException:
            shutil.rmtree(staging,ignore_errors=True)
            raise
    previous=_active(root)
    _write_active(root,{
        "release_id":release_id,
        "index_sha256":proven["index_sha256"],
        "installed_at":datetime.now(timezone.utc).isoformat(),
        "previous_release_id":previous["release_id"] if previous else None,
        "state":"PRIVATE_SOURCE_INDEX_READY_APP_NOT_DEPLOYED"
    })
    result["active_release_id"]=release_id
    result["previous_release_id"]=previous["release_id"] if previous else None
    result["installed_to_private_path"]=True
    result["durable_production_indexed"]=0  # CI/test mount is not a verified production service
    result["authenticated_service_connected"]=False
    result["app_deployed_records"]=0
    return result

def active_status(store_root,*,repo_root=None):
    root=_store_root(store_root,repo_root or Path(__file__).resolve().parents[1])
    active=_active(root)
    if active is None:
        raise ValueError("No active Lane C release installed")
    bundle=root/"releases"/active["release_id"]
    checked=verify_bundle(bundle)
    if checked["index_sha256"]!=active["index_sha256"]:
        raise ValueError("Active release index SHA changed after installation")
    return {"state":"PRIVATE_SOURCE_INDEX_READY_APP_NOT_DEPLOYED",
            "active_release_id":active["release_id"],**checked,
            "authenticated_service_connected":False,
            "app_deployed_records":0}

def query(store_root,*,source,state=None,since=None,page=1,page_size=50,repo_root=None):
    # Every request uses the already verified immutable release pointed to by
    # an atomically installed pointer. Re-hashing all 17 original XLSX files
    # on *every* page request is not acceptable query performance; the full
    # original/normalized/index SHA audit is performed during install/status.
    root=_store_root(store_root,repo_root or Path(__file__).resolve().parents[1])
    active=_active(root)
    if not active:
        raise ValueError("No active Lane C release installed")
    if not re.fullmatch(r"(?:nrc_20[0-9]{2}|csb)",source or ""):
        raise ValueError("Unknown source namespace")
    source_counts=_read_json(
        _safe_file(root/"releases"/active["release_id"],"private-bundle-manifest.json")
    ).get("source_counts",{})
    if source not in source_counts:
        raise ValueError("Unknown source namespace; not present in active release")
    if (not isinstance(page,int) or page<1 or not isinstance(page_size,int)
        or not 1<=page_size<=200):
        raise ValueError("Unsupported source query paging")
    if since is not None and not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",since):
        raise ValueError("Query incident date must be ISO YYYY-MM-DD")
    if state is not None and (not isinstance(state,str) or len(state)>12):
        raise ValueError("Invalid source state filter")
    path=root/"releases"/active["release_id"]/"indexes"/"lane-c-source.sqlite"
    filters=["source=?" ]
    args=[source]
    if state is not None:
        filters.append("state=?");args.append(state)
    if since:
        filters.append("incident_date>=?");args.append(since)
    clause=" AND ".join(filters)
    with _readonly_db(path) as db:
        count=db.execute("SELECT COUNT(*) FROM source_incidents WHERE "+clause,args).fetchone()[0]
        records=db.execute("""SELECT source,source_id,publisher_native_id,source_vintage,
                            incident_date,city,state,latitude,longitude,
                            evidence_status,site_link_status,source_url
                            FROM source_incidents WHERE """+clause+
            " ORDER BY incident_date DESC,source_id LIMIT ? OFFSET ?",args+[page_size,(page-1)*page_size]).fetchall()
    fields=("source","source_id","publisher_native_id","source_vintage",
            "incident_date","city","state","latitude","longitude",
            "evidence_status","site_link_status","source_url")
    return {"source":source,"total":count,"page":page,"page_size":page_size,
            "items":[dict(zip(fields,row)) for row in records],
            "classification":"REVIEW_ONLY_UNVERIFIED_SOURCE_OBSERVATIONS",
            "source_release":active["release_id"],
            "authenticated_api_exposure":"NOT_IMPLEMENTED_LANE_E_OWNED"}

def rollback(store_root,release_id,*,repo_root=None):
    root=_store_root(store_root,repo_root or Path(__file__).resolve().parents[1])
    if not RELEASE_PATTERN.fullmatch(release_id):
        raise ValueError("Unsafe rollback release ID")
    prev=_active(root)
    if not prev:
        raise ValueError("No current release exists")
    checked=verify_bundle(root/"releases"/release_id)
    _write_active(root,{
        "release_id":release_id,"index_sha256":checked["index_sha256"],
        "installed_at":datetime.now(timezone.utc).isoformat(),
        "previous_release_id":prev["release_id"],
        "state":"PRIVATE_SOURCE_INDEX_READY_APP_NOT_DEPLOYED"
    })
    return {"state":"ROLLED_BACK_TO_PREVIOUS_VERIFIED_PRIVATE_SOURCE_RELEASE",
            "active_release_id":release_id,
            "total_indexed_source_observations":checked["total_indexed_source_observations"],
            "app_deployed_records":0}

def main():
    parser=argparse.ArgumentParser(description="Lane C private source-only install/query; not a public service")
    sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("install")
    p.add_argument("--bundle",required=True,type=Path)
    p.add_argument("--root",required=True,type=Path)
    p.add_argument("--release-id")
    p=sub.add_parser("status")
    p.add_argument("--root",required=True,type=Path)
    p=sub.add_parser("query")
    p.add_argument("--root",required=True,type=Path)
    p.add_argument("--source",required=True)
    p.add_argument("--state")
    p.add_argument("--since")
    p.add_argument("--page",type=int,default=1)
    p.add_argument("--page-size",type=int,default=50)
    p=sub.add_parser("rollback")
    p.add_argument("--root",required=True,type=Path)
    p.add_argument("--release-id",required=True)
    args=parser.parse_args()
    if args.command=="install":
        result=install(args.bundle,args.root,release_id=args.release_id)
    elif args.command=="status":
        result=active_status(args.root)
    elif args.command=="query":
        result=query(args.root,source=args.source,state=args.state,
                     since=args.since,page=args.page,page_size=args.page_size)
    else:
        result=rollback(args.root,args.release_id)
    print(json.dumps(result,indent=2,ensure_ascii=False))

if __name__=="__main__":
    main()
