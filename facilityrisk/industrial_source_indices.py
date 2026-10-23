"""Authenticated PRIVATE reads of Lane C's installed source-only SQLite releases.

Never load data from GitHub Pages, a public Actions artifact, or an unverified
canonical facility crosswalk. The upstream Lane C installer validates *all*
original/normalized SHA-256 files before atomically publishing a read-only
release. At runtime recheck the active pointer, pinned index SHA, schema,
counts and status without opening any writable research DB.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time

INCIDENT_ROOT_ENV="FACILITY_RISK_LANE_C_ROOT"
ENFORCEMENT_ROOT_ENV="FACILITY_RISK_PHMSA_WMS_ROOT"
RELEASE_RE=re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z")
SOURCE_RE=re.compile(r"(?:nrc_20[0-9]{2}|csb)\Z")
HEX_SHA=re.compile(r"[0-9a-f]{64}\Z")
QUERY_BUDGET_SECONDS=8.0
MISSING_MESSAGE="Index not configured on this private server; absence is not a zero-incidents finding"
CAUTION="Regulator source observations are not confirmed distinct accidents, insured premises, paid losses or policy coverage"

class IndustrialSourceUnavailable(ValueError):
    """Read-only regulator source release missing, stale, corrupt or not verified."""

def _file_hash(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda:f.read(1024*1024),b""):
            h.update(part)
    return h.hexdigest()

def _load_json(path):
    with path.open("r",encoding="utf-8") as f:
        value=json.load(f)
    if not isinstance(value,dict):
        raise IndustrialSourceUnavailable("Invalid release metadata")
    return value

def _safe_path(root,rel,*,directory=False):
    root=Path(root)
    target=root / rel
    if (Path(rel).is_absolute() or ".." in Path(rel).parts or
        target.is_symlink() or any(x.is_symlink() for x in [root,*target.parents]
                if x==root or x.is_relative_to(root))):
        raise IndustrialSourceUnavailable("Source release path is not trusted")
    if not target.resolve().is_relative_to(root.resolve()):
        raise IndustrialSourceUnavailable("Source release escapes private mount")
    if directory:
        if not target.is_dir():
            raise IndustrialSourceUnavailable("Source release directory absent")
    elif not target.is_file() or target.stat().st_size<=0:
        raise IndustrialSourceUnavailable("Source release file missing or empty")
    return target

def _read_config(kind):
    env=INCIDENT_ROOT_ENV if kind=="observations" else ENFORCEMENT_ROOT_ENV
    setting=os.environ.get(env,"").strip()
    if not setting:
        raise IndustrialSourceUnavailable("NOT_CONFIGURED")
    root=Path(setting).expanduser()
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise IndustrialSourceUnavailable("Private source root missing or not absolute")
    root=root.resolve()
    pointer=_load_json(_safe_path(root,"active-release.json"))
    release=pointer.get("release_id","")
    if not isinstance(release,str) or not RELEASE_RE.fullmatch(release):
        raise IndustrialSourceUnavailable("Private source release identifier invalid")
    folder=_safe_path(root,"releases/"+release,directory=True)
    filename=("private-bundle-manifest.json" if kind=="observations"
              else "private-phmsa-enforcement-manifest.json")
    meta_path=_safe_path(folder,filename)
    meta=_load_json(meta_path)
    if kind=="observations":
        if meta.get("state")!="PRIVATE_LOCAL_HANDOFF_READY_NOT_AUTHENTICATED_OR_DEPLOYED":
            raise IndustrialSourceUnavailable("Unexpected incident source bundle identity")
        original_counts=meta.get("source_counts")
        if not isinstance(original_counts,dict) or not original_counts:
            raise IndustrialSourceUnavailable("Missing source-namespace inventory")
        if (set(original_counts)!=set(meta.get("source_namespaces",[])) or
            any(not SOURCE_RE.fullmatch(k) for k in original_counts)):
            raise IndustrialSourceUnavailable("Invalid incident source namespaces")
        rel="indexes/lane-c-source.sqlite"
        expected=meta.get("index_sha256")
        expected_counts=original_counts
        exp_total=meta.get("total_source_rows")
    else:
        if meta.get("state")!="PRIVATE_WMS_ENFORCEMENT_HANDOFF_NOT_DEPLOYED" or meta.get("pipeline_incident_census")!="NOT_TESTED":
            raise IndustrialSourceUnavailable("Unrecognized PHMSA enforcement case source")
        rel="indexes/phmsa-wms-enforcement.sqlite"
        expected=meta.get("files",{}).get("database",{}).get("sha256")
        expected_counts=None
        exp_total=meta.get("accepted_case_rows")
    if not isinstance(expected,str) or not HEX_SHA.fullmatch(expected):
        raise IndustrialSourceUnavailable("Pinned index SHA absent or invalid")
    if pointer.get("index_sha256")!=expected:
        raise IndustrialSourceUnavailable("Active pointer differs from pinned original source index")
    db=_safe_path(folder,rel)
    wal=Path(str(db)+"-wal")
    if wal.is_file() and wal.stat().st_size:
        raise IndustrialSourceUnavailable("Uncheckpointed WAL on read-only source")
    if exp_total is None or not isinstance(exp_total,int) or exp_total<=0:
        raise IndustrialSourceUnavailable("Expected source index count missing")
    return {
        "kind":kind,"root":root,"release":release,"index":db,
        "manifest":meta,"pointer":pointer,
        "expected_sha":expected,"expected_counts":expected_counts,
        "expected_total":exp_total,
    }

@contextmanager
def _db(path):
    uri=path.resolve().as_uri()+"?mode=ro&immutable=1"
    conn=sqlite3.connect(uri,uri=True,timeout=5)
    conn.row_factory=sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    started=time.monotonic()
    conn.set_progress_handler(lambda: 1 if time.monotonic()-started>QUERY_BUDGET_SECONDS else 0,10000)
    try:
        yield conn
    except sqlite3.Error as exc:
        raise IndustrialSourceUnavailable("Read-only source index query failed") from exc
    finally:
        conn.close()

@lru_cache(maxsize=24)
def _validate_index(kind,path,size,mtime_ns,manifest_sha,expected_total,count_json):
    """Each immutable byte-snapshot validated once per process/cache key."""
    db_path=Path(path)
    if _file_hash(db_path)!=manifest_sha:
        raise IndustrialSourceUnavailable("Private source SQLite SHA-256 mismatch")
    with _db(db_path) as conn:
        if conn.execute("PRAGMA quick_check").fetchone()[0]!="ok":
            raise IndustrialSourceUnavailable("Source-only SQLite quick_check failed")
        tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables.intersection({"facilities","raw_snapshots","insurance_policies","review_approvals"}):
            raise IndustrialSourceUnavailable("Private insured-research tables mixed into source-only SQLite")
        if kind=="observations":
            if not {"source_incidents","lane_c_review_candidates"}.issubset(tables):
                raise IndustrialSourceUnavailable("Source observation/review tables missing")
            cols={r[1] for r in conn.execute("PRAGMA table_info(source_incidents)")}
            mandatory={"source","source_id","publisher_native_id","source_vintage",
                "incident_date","city","state","latitude","longitude","source_url",
                "evidence_status","site_link_status","source_json"}
            if not mandatory.issubset(cols):
                raise IndustrialSourceUnavailable("Source incident table schema changed")
            counts=dict(conn.execute("SELECT source,COUNT(*) FROM source_incidents GROUP BY source").fetchall())
            if counts!=json.loads(count_json):
                raise IndustrialSourceUnavailable("Per-source real index rows disagree with publisher manifests")
            total=sum(counts.values())
            pairs=conn.execute("SELECT COUNT(*) FROM lane_c_review_candidates").fetchone()[0]
            unsafe=conn.execute("""SELECT COUNT(*) FROM source_incidents
                                   WHERE site_link_status!='candidate_only_not_matched'""").fetchone()[0]
            unsafe+=conn.execute("""SELECT COUNT(*) FROM lane_c_review_candidates
                                     WHERE status!='review_candidate_not_corrob'""").fetchone()[0]
            if unsafe:
                raise IndustrialSourceUnavailable("Unreviewed source records were promoted to verified")
            result={"source_counts":counts,"review_candidates":pairs}
        else:
            if "enforcement_cases" not in tables:
                raise IndustrialSourceUnavailable("PHMSA case-only source index missing")
            cols={r[1] for r in conn.execute("PRAGMA table_info(enforcement_cases)")}
            if not {"source_row_number","case_number","wms_activity_seq","operator_id",
                     "report_type","report_number","site_link_status"}.issubset(cols):
                raise IndustrialSourceUnavailable("PHMSA WMS source schema changed")
            total=conn.execute("SELECT COUNT(*) FROM enforcement_cases").fetchone()[0]
            unsafe=conn.execute("""SELECT COUNT(*) FROM enforcement_cases
                                WHERE site_link_status!='candidate_only_not_matched'""").fetchone()[0]
            if unsafe:
                raise IndustrialSourceUnavailable("PHMSA case-to-facility link not approved")
            result={"source_counts":{"phmsa_wms_enforcement_cases":total},
                    "review_candidates":0}
    if total!=expected_total:
        raise IndustrialSourceUnavailable("Indexed source count differs from pinned source manifest")
    result["rows"]=total
    return result

def _verified(kind):
    found=_read_config(kind)
    db=found["index"]
    stat=db.stat()
    count_json=json.dumps(found["expected_counts"],sort_keys=True)
    facts=_validate_index(kind,str(db),stat.st_size,stat.st_mtime_ns,
                          found["expected_sha"],found["expected_total"],count_json)
    if kind=="observations" and facts["review_candidates"]!=found["manifest"].get("review_candidate_pairs"):
        raise IndustrialSourceUnavailable("Cross-agency reviewer candidate manifest mismatch")
    return found,facts

def status(kind):
    if kind not in ("observations","enforcement"):
        raise ValueError("Unknown source index type")
    env=INCIDENT_ROOT_ENV if kind=="observations" else ENFORCEMENT_ROOT_ENV
    if not os.environ.get(env,"").strip():
        return {"state":"not_configured","source":kind,"indexed_source_records":None,
                "notice":MISSING_MESSAGE,"production_deployment_verified":False}
    try:
        found,facts=_verified(kind)
    except (IndustrialSourceUnavailable,OSError,ValueError,KeyError,sqlite3.Error,TypeError):
        return {"state":"unavailable","source":kind,"indexed_source_records":None,
                "notice":"Configured private source index unavailable or inconsistent; no zero-incident inference",
                "production_deployment_verified":False}
    manifest=found["manifest"]
    result={"state":"ready_private","source":kind,"release_id":found["release"],
       "indexed_source_records":facts["rows"],
       "source_counts":facts["source_counts"],
       "index_sha256":found["expected_sha"],
       "sqlite_quick_check":"ok",
       "private_api_mounted":True,
       "production_deployment_verified":False,
       "verified_insured_sites":0,
       "verified_insured_losses":0,
       "notice":CAUTION}
    if kind=="observations":
        result["review_only_pairs"]=facts["review_candidates"]
        result["raw_publisher_rows"]=facts["rows"]+1 if "csb" in facts["source_counts"] else None
        result["separate_phmsa_census_status"]="NOT_TESTED_OFFICIAL_403"
    else:
        result["distinct_typed_report_references"]=manifest.get("distinct_typed_report_references")
        result["incident_census_status"]="NOT_TESTED_ACCESS_BLOCKED"
    return result

def _require(kind):
    found,facts=_verified(kind)
    return found,facts

def _validate_day(value):
    if value is None or value=="":
        return None
    if not isinstance(value,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",value):
        raise ValueError("Date must be ISO YYYY-MM-DD")
    try: date.fromisoformat(value)
    except ValueError as e:raise ValueError("Invalid calendar date") from e
    return value

def _validate_page(limit,offset):
    if (not isinstance(limit,int) or not 1<=limit<=100
        or not isinstance(offset,int) or not 0<=offset<=100000):
        raise ValueError("Requested source-query page outside safety bounds")

def observations(*,source,state=None,since=None,limit=50,offset=0):
    found,facts=_require("observations")
    if not isinstance(source,str) or not SOURCE_RE.fullmatch(source) or source not in facts["source_counts"]:
        raise ValueError("Source namespace must be one of the verified active release namespaces")
    _validate_page(limit,offset)
    since=_validate_day(since)
    if state is not None and (not isinstance(state,str) or len(state)>80):
        raise ValueError("Invalid source-reported state")
    clauses=["source=?" ];args=[source]
    if state:
        clauses.append("state=?");args.append(state)
    if since:
        clauses.append("incident_date>=?");args.append(since)
    where=" AND ".join(clauses)
    selected=("source","source_id","publisher_native_id","source_vintage","incident_date",
              "city","state","latitude","longitude","evidence_status","site_link_status","source_url")
    with _db(found["index"]) as conn:
        total=conn.execute("SELECT COUNT(*) FROM source_incidents WHERE "+where,args).fetchone()[0]
        rows=conn.execute("SELECT "+",".join(selected)+" FROM source_incidents WHERE "+
            where+" ORDER BY incident_date DESC,source_id LIMIT ? OFFSET ?",
            (*args,limit,offset)).fetchall()
    return {"source_namespace":source,"total":total,"limit":limit,"offset":offset,
       "items":[dict(zip(selected,row)) for row in rows],
       "release_id":found["release"],
       "status":"UNVERIFIED_REGULATORY_SOURCE_REPORTS_NOT_INSURED_LOSSES"}

def observation_detail(*,source,source_id):
    found,facts=_require("observations")
    if not SOURCE_RE.fullmatch(source or "") or source not in facts["source_counts"]:
        raise ValueError("Invalid source namespace")
    if not source_id or len(source_id)>110:
        raise ValueError("Invalid source native ID")
    keys=("source","source_id","publisher_native_id","source_vintage","incident_date",
          "city","state","latitude","longitude","evidence_status","site_link_status","source_url")
    with _db(found["index"]) as conn:
        row=conn.execute("SELECT "+",".join(keys)+" FROM source_incidents WHERE source=? AND source_id=?",
                         (source,source_id)).fetchone()
    return dict(zip(keys,row)) if row else None

def enforcement(*,operator_id=None,case_number=None,limit=50,offset=0):
    found,facts=_require("enforcement")
    _validate_page(limit,offset)
    if operator_id is not None and (not isinstance(operator_id,str) or len(operator_id)>30):
        raise ValueError("Invalid PHMSA operator identifier")
    if case_number is not None and (not isinstance(case_number,str) or len(case_number)>70):
        raise ValueError("Invalid PHMSA native enforcement case number")
    clauses=["site_link_status='candidate_only_not_matched'"];args=[]
    if operator_id:
        clauses.append("operator_id=?");args.append(operator_id)
    if case_number:
        clauses.append("case_number=?");args.append(case_number)
    where=" AND ".join(clauses)
    keys=("case_number","wms_activity_seq","operator_id","pipeline_type","case_status",
          "opened_date","report_type","report_number","site_link_status")
    with _db(found["index"]) as conn:
        total=conn.execute("SELECT COUNT(*) FROM enforcement_cases WHERE "+where,args).fetchone()[0]
        rows=conn.execute("SELECT "+",".join(keys)+" FROM enforcement_cases WHERE "+
            where+" ORDER BY opened_date DESC, source_row_number LIMIT ? OFFSET ?",
            (*args,limit,offset)).fetchall()
    return {"source":"PHMSA_WMS_ENFORCEMENT_CASES_NOT_INCIDENT_REPORT_CENSUS",
        "total":total,"limit":limit,"offset":offset,
        "items":[dict(zip(keys,row)) for row in rows],
        "release_id":found["release"],
        "confirmed_incidents":None,"confirmed_insured_losses":None}

def review_candidates(*,limit=50,offset=0):
    found,_facts=_require("observations")
    _validate_page(limit,offset)
    keys=("nrc_source","nrc_source_id","csb_source","csb_source_id","match_rule","status")
    with _db(found["index"]) as conn:
        total=conn.execute("SELECT COUNT(*) FROM lane_c_review_candidates").fetchone()[0]
        rows=conn.execute("SELECT "+",".join(keys)+
             " FROM lane_c_review_candidates ORDER BY nrc_source,nrc_source_id LIMIT ? OFFSET ?",
             (limit,offset)).fetchall()
    return {"total":total,"limit":limit,"offset":offset,
        "items":[dict(zip(keys,row)) for row in rows],
        "classification":"REVIEW_ONLY_NOT_INDEPENDENT_CORROBORATION_OR_PHYSICAL_SITE"}
