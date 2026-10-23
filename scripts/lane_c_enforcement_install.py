"""PHMSA WMS enforcement: separate private case source bundle and read-only install.

This is a publication of PHMSA *enforcement cases*, not pipeline accident
reports. Keep index and release pointer separate from NRC/CSB observations.
Only Lane E may wire authenticated service routes or physical-site reviews.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile

try:
    from scripts.lane_c_install import (
        file_sha256,_safe_file,_readonly_db,_store_root,_write_active,_active
    )
    from scripts.build_phmsa_enforcement import validate as validate_source
except ModuleNotFoundError:
    from lane_c_install import (
        file_sha256,_safe_file,_readonly_db,_store_root,_write_active,_active
    )
    from build_phmsa_enforcement import validate as validate_source

BUNDLE_NAME="private-phmsa-enforcement-manifest.json"
SOURCE_FILES={
    "raw":"originals/phmsa-wms-enforcement.txt",
    "normalized":"normalized/phmsa-wms-enforcement.csv.gz",
    "manifest":"manifests/phmsa-wms-enforcement.json",
    "database":"indexes/phmsa-wms-enforcement.sqlite"
}
RELEASE=re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")

def _check_index(database,expected):
    with _readonly_db(database) as conn:
        if conn.execute("PRAGMA quick_check").fetchone()[0]!="ok":
            raise ValueError("PHMSA private SQLite integrity check failed")
        columns={item[1] for item in conn.execute("PRAGMA table_info(enforcement_cases)")}
        if not {"source_row_number","case_number","wms_activity_seq","operator_id",
                "report_type","report_number","site_link_status"}.issubset(columns):
            raise ValueError("Missing PHMSA WMS case index schema")
        count,unique,report_rows,refs=conn.execute("""SELECT COUNT(*),COUNT(DISTINCT case_number),
            COALESCE(SUM(CASE WHEN report_type<>'' AND report_number<>'' THEN 1 ELSE 0 END),0),
            COUNT(DISTINCT CASE WHEN report_type<>'' AND report_number<>''
                THEN report_type || '|' || report_number ELSE NULL END)
            FROM enforcement_cases""").fetchone()
        n_bad=conn.execute("""SELECT COUNT(*) FROM enforcement_cases
              WHERE site_link_status<>'candidate_only_not_matched'""").fetchone()[0]
        if (count!=expected["accepted_case_rows"] or
            unique!=expected["native_case_ids"] or
            report_rows!=expected["report_reference_rows"] or
            refs!=expected["distinct_typed_report_references"] or n_bad):
            raise ValueError("PHMSA WMS private case index identity/row/reference reconciliation failed")
        first=conn.execute("SELECT case_number FROM enforcement_cases LIMIT 1").fetchone()
        if count and not first:
            raise ValueError("PHMSA WMS read-only case query failed")
    return {"accepted_enforcement_case_rows":count,"distinct_native_case_numbers":unique,
            "case_rows_with_report_references":report_rows,
            "distinct_typed_report_references":refs,
            "sqlite_quick_check":"ok","first_party_census_incidents":"NOT_TESTED",
            "verified_facility_matches":0}

def package(raw,normalized,manifest_path,database,destination,*,repo_root=None):
    """Copy official enforcement source and SQLite into preapproved private mount."""
    repo=repo_root or Path(__file__).resolve().parents[1]
    dest=Path(destination).expanduser().resolve()
    if dest.is_relative_to(Path(repo).resolve()):
        raise ValueError("PHMSA private bundle must be outside checkout")
    if dest.exists() or not dest.parent.is_dir():
        raise ValueError("PHMSA private bundle must use a new directory under pre-created private mount")
    details=json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    validate_source(normalized,details)
    if details.get("incident_census_rows")!="NOT_TESTED":
        raise ValueError("PHMSA WMS must not be labeled the pipeline incident census")
    if (file_sha256(raw)!=details["raw_sha256"] or
        file_sha256(normalized)!=details["normalized_sha256"]):
        raise ValueError("Original or normalized PHMSA enforcement SHA mismatch")
    _check_index(database,details)
    dest.mkdir(mode=0o700)
    try:
        for name,src in [("raw",raw),("normalized",normalized),
                         ("manifest",manifest_path),("database",database)]:
            target=dest/SOURCE_FILES[name]
            target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            shutil.copyfile(src,target)
            target.chmod(0o600)
        checks={k:{"sha256":file_sha256(_safe_file(dest,p)),
                   "bytes":_safe_file(dest,p).stat().st_size}
                for k,p in SOURCE_FILES.items()}
        audit={"state":"PRIVATE_WMS_ENFORCEMENT_HANDOFF_NOT_DEPLOYED",
               "created_at":datetime.now(timezone.utc).isoformat(),
               "source_url":details["url"],"snapshot":details["source_snapshot"],
               "files":checks,"accepted_case_rows":details["accepted_case_rows"],
               "rejected_case_rows":details["rejected_case_rows"],
               "native_case_numbers":details["native_case_ids"],
               "case_rows_with_report_references":details["report_reference_rows"],
               "distinct_typed_report_references":details["distinct_typed_report_references"],
               "pipeline_incident_census":"NOT_TESTED",
               "durable_authenticated_production_indexed":0,"app_deployed":0}
        path=dest/BUNDLE_NAME
        path.write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
        path.chmod(0o600)
        verify(dest)
        return {"state":audit["state"],"packaged_case_rows":audit["accepted_case_rows"],
                "index_sha256":checks["database"]["sha256"],"verified":"PASS",
                "app_deployed":0}
    except BaseException:
        shutil.rmtree(dest,ignore_errors=True)
        raise

def verify(bundle):
    bundle=Path(bundle).resolve()
    manifest=json.loads(_safe_file(bundle,BUNDLE_NAME).read_text(encoding="utf-8"))
    if manifest.get("state")!="PRIVATE_WMS_ENFORCEMENT_HANDOFF_NOT_DEPLOYED":
        raise ValueError("Unknown PHMSA private enforcement bundle kind")
    if manifest.get("app_deployed")!=0:
        raise ValueError("Unverified PHMSA case deployment claim")
    for k,path in SOURCE_FILES.items():
        if file_sha256(_safe_file(bundle,path))!=manifest["files"][k]["sha256"]:
            raise ValueError("PHMSA WMS source/private SQLite file SHA mismatch: "+k)
    case_manifest=json.loads(_safe_file(bundle,SOURCE_FILES["manifest"]).read_text(encoding="utf-8"))
    if (case_manifest["accepted_case_rows"]!=manifest["accepted_case_rows"] or
        case_manifest["raw_sha256"]!=manifest["files"]["raw"]["sha256"] or
        case_manifest["normalized_sha256"]!=manifest["files"]["normalized"]["sha256"]):
        raise ValueError("PHMSA normalized and raw provenance do not agree")
    metrics=_check_index(_safe_file(bundle,SOURCE_FILES["database"]),case_manifest)
    return {"state":"VERIFIED_PRIVATE_WMS_CASE_BUNDLE",
            "index_sha256":manifest["files"]["database"]["sha256"],
            "snapshot":case_manifest["source_snapshot"],**metrics,
            "app_deployed":0}

def install(bundle,root,release_id=None,*,repo_root=None):
    root=_store_root(root,repo_root or Path(__file__).resolve().parents[1])
    src=Path(bundle).expanduser().resolve()
    if src.is_relative_to(root):
        raise ValueError("Do not install private WMS bundle from inside release root")
    checked=verify(src)
    release_id=release_id or ("wms-"+checked["index_sha256"][:12])
    if not RELEASE.fullmatch(release_id):
        raise ValueError("Unsafe PHMSA WMS release ID")
    releases=root/"releases"
    releases.mkdir(mode=0o700,exist_ok=True)
    target=releases/release_id
    if target.exists():
        old=verify(target)
        if old["index_sha256"]!=checked["index_sha256"]:
            raise ValueError("PHMSA WMS immutable release ID conflicts with different source")
        state="ALREADY_INSTALLED_CHECKSUM_VERIFIED"
    else:
        staging=Path(tempfile.mkdtemp(prefix=".wms-staging-",dir=releases))
        try:
            for item in src.rglob("*"):
                if item.is_symlink():
                    raise ValueError("Symlink in WMS source bundle")
                if not item.is_file():continue
                out=staging/item.relative_to(src)
                out.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                shutil.copyfile(item,out)
                out.chmod(0o600)
            if verify(staging)["index_sha256"]!=checked["index_sha256"]:
                raise ValueError("Installed PHMSA WMS checksum differs from source")
            for file in staging.rglob("*"):
                if file.is_file():file.chmod(0o400)
            for folder in sorted((p for p in staging.rglob("*") if p.is_dir()),
                                 key=lambda p:len(p.parts),reverse=True):
                folder.chmod(0o500)
            staging.chmod(0o500)
            staging.rename(target)
            state="VERIFIED_PRIVATE_WMS_RELEASE_INSTALLED_NOT_APP_DEPLOYED"
        except BaseException:
            shutil.rmtree(staging,ignore_errors=True)
            raise
    previous=_active(root)
    _write_active(root,{
        "release_id":release_id,"index_sha256":checked["index_sha256"],
        "installed_at":datetime.now(timezone.utc).isoformat(),
        "previous_release_id":previous["release_id"] if previous else None,
        "state":"PRIVATE_WMS_CASE_SOURCE_NOT_APP_DEPLOYED"
    })
    return {"state":state,"active_release_id":release_id,
            "index_sha256":checked["index_sha256"],
            "verified_case_rows":checked["accepted_enforcement_case_rows"],
            "live_app_deployed":0,"authenticated_API_deployed":False,
            "production_indexed_confirmed":0}

def query(root,*,operator_id=None,case_number=None,page=1,page_size=50,repo_root=None):
    root=_store_root(root,repo_root or Path(__file__).resolve().parents[1])
    active=_active(root)
    if not active:raise ValueError("No active PHMSA WMS case release")
    if not isinstance(page,int) or page<1 or not isinstance(page_size,int) or not 1<=page_size<=200:
        raise ValueError("Invalid PHMSA WMS query paging")
    where=["site_link_status='candidate_only_not_matched'"]
    args=[]
    if operator_id is not None:
        where.append("operator_id=?");args.append(operator_id)
    if case_number is not None:
        where.append("case_number=?");args.append(case_number)
    clause=" AND ".join(where)
    path=root/"releases"/active["release_id"]/SOURCE_FILES["database"]
    with _readonly_db(_safe_file(path.parents[1],path.relative_to(path.parents[1]))) as db:
        count=db.execute("SELECT COUNT(*) FROM enforcement_cases WHERE "+clause,args).fetchone()[0]
        rows=db.execute("""SELECT case_number,wms_activity_seq,operator_id,pipeline_type,
                     case_status,opened_date,report_type,report_number,site_link_status
                     FROM enforcement_cases WHERE """+clause+
                     " ORDER BY opened_date DESC,source_row_number LIMIT ? OFFSET ?",
                     args+[page_size,(page-1)*page_size]).fetchall()
    cols=("case_number","wms_activity_seq","operator_id","pipeline_type",
          "case_status","opened_date","report_type","report_number","site_link_status")
    return {"source":"phmsa_wms_enforcement_NOT_INCIDENT_CENSUS",
            "total":count,"page":page,"page_size":page_size,
            "items":[dict(zip(cols,row)) for row in rows],
            "release_id":active["release_id"],
            "app_deployed":0}

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    a=sub.add_parser("install")
    a.add_argument("--bundle",type=Path,required=True)
    a.add_argument("--root",type=Path,required=True)
    a.add_argument("--release-id")
    a=sub.add_parser("query")
    a.add_argument("--root",type=Path,required=True)
    a.add_argument("--operator-id")
    a.add_argument("--case-number")
    a.add_argument("--page",type=int,default=1)
    a.add_argument("--page-size",type=int,default=50)
    a=sub.add_parser("verify")
    a.add_argument("--bundle",type=Path,required=True)
    a=sub.add_parser("package")
    for flag in ("--raw","--normalized","--manifest","--db","--destination"):
        a.add_argument(flag,required=True,type=Path)
    args=p.parse_args()
    if args.cmd=="package":
        result=package(args.raw,args.normalized,args.manifest,args.db,args.destination)
    elif args.cmd=="verify":result=verify(args.bundle)
    elif args.cmd=="install":result=install(args.bundle,args.root,args.release_id)
    else:result=query(args.root,operator_id=args.operator_id,case_number=args.case_number,
                      page=args.page,page_size=args.page_size)
    print(json.dumps(result,indent=2))
if __name__=="__main__":
    main()
