"""Optional coordinator-mounted read-only EPA Lane B private API adapter.

Importing this module does NOT mount routes. The existing FastAPI security middleware
must authenticate every request BEFORE build_router() routes are exposed. No insured
property joins, write endpoints, national scans, or deployment claims.
"""
import os
from pathlib import Path
import re
import sqlite3

from .read_index import InvalidSourceIndex,lookup as regulatory_lookup,source_status
from .rmp_lookup import InvalidRMPIndex,lookup as rmp_lookup,status as rmp_status
from .tri_history import lookup_history

ENV={
    "echo":"FACILITY_RISK_LANE_B_ECHO_DIRECTORY",
    "rcra":"FACILITY_RISK_LANE_B_RCRA_DIRECTORY",
    "tri":"FACILITY_RISK_LANE_B_TRI_ROOT",
    "rmp_public":"FACILITY_RISK_LANE_B_RMP_DIRECTORY",
}
TRI_YEARS_ENV="FACILITY_RISK_LANE_B_TRI_YEARS"
ERRORS=(InvalidSourceIndex,InvalidRMPIndex,ValueError,OSError,TypeError,KeyError,sqlite3.Error)

def reporting_years(spec):
    """Require explicit mounted annual vintages (ranges or comma-separated years)."""
    if not isinstance(spec,str) or not spec.strip():
        raise ValueError("Explicit TRI coverage years required")
    years=[]
    for part in spec.split(","):
        p=part.strip()
        if re.fullmatch(r"[0-9]{4}-[0-9]{4}",p):
            lo,hi=map(int,p.split("-"))
            if lo>hi:raise ValueError("Invalid TRI year range")
            years.extend(range(lo,hi+1))
        elif re.fullmatch(r"[0-9]{4}",p):
            years.append(int(p))
        else:raise ValueError("Invalid TRI year list")
    if not years or len(years)>38 or len(set(years))!=len(years) or any(y<1987 or y>2024 for y in years):
        raise ValueError("TRI coverage years duplicate, missing or unsupported")
    return sorted(years)

def _directory(source,environ):
    env=ENV[source]
    text=environ.get(env,"").strip()
    if not text:return None
    directory=Path(text).expanduser()
    if not directory.is_absolute():raise ValueError("Absolute source-index mount path required")
    directory=directory.resolve()
    if not directory.is_dir():raise InvalidSourceIndex("Private source directory not mounted")
    return directory

def _tri_index(directory,year):
    if type(year)!=int or not 1987<=year<=2024:
        raise ValueError("Explicit TRI reporting year required")
    path=directory/("tri_"+str(year))
    return path/"tri.sqlite",path/"tri.manifest.json"

def _mounted_status(source,environ):
    directory=_directory(source,environ)
    if directory is None:
        return {"source":source,"state":"not_configured","production_deployed_records":None,
                "notice":"No verified source-only private snapshot mounted"}
    if source in ("echo","rcra"):
        facts=source_status(directory/(source+".sqlite"),
                            directory/(source+".manifest.json"),source)
        return {"source":source,"state":"mounted_source_only","indexed_source_rows":facts["indexed_rows"],
                "rejected_source_rows":facts["rejected_rows"],
                "source_sha256":facts["source_archive_sha256"],"index_sha256":facts["index_sha256"],
                "source_retrieved_utc":facts["retrieved_utc"],
                "insured_site_matches_verified":0,"production_deployed_records":None,
                "notice":"Private index mounted here; no proof of live production deploy or insured property match"}
    if source=="rmp_public":
        facts=rmp_status(directory)
        return {"source":source,"state":"mounted_source_only",
                "indexed_source_rows":facts["records"],
                "distinct_public_program_ids":facts["distinct_program_ids"],
                "source_sha256":facts["raw_jsonl_sha256"],"index_sha256":facts["database_sha256"],
                "insured_site_matches_verified":0,"production_deployed_records":None,
                "notice":"Public RMP interest records only; no RMP plans, OCA, accidents or insured properties"}
    years=reporting_years(environ.get(TRI_YEARS_ENV,""))
    total=0;partitions=[]
    for year in years:
        db,manifest=_tri_index(directory,year)
        facts=source_status(db,manifest,"tri")
        import json
        vint=json.loads(manifest.read_text())
        if vint.get("year")!=year:
            raise InvalidSourceIndex("TRI manifest source reporting year differs from configured year")
        total+=facts["indexed_rows"]
        partitions.append({"year":year,"indexed_source_rows":facts["indexed_rows"],
                           "source_sha256":facts["source_archive_sha256"],
                           "index_sha256":facts["index_sha256"]})
    return {"source":source,"state":"mounted_source_only",
            "indexed_source_rows":total,"loaded_source_reporting_years":years,
            "annual_source_partitions":partitions,
            "insured_site_matches_verified":0,"production_deployed_records":None,
            "notice":"Source chemical filing rows; each year validated, not additive as unique facilities"}

def status(environ=None):
    env=os.environ if environ is None else environ
    result={}
    for source in ENV:
        try:
            result[source]=_mounted_status(source,env)
        except ERRORS:
            result[source]={"source":source,"state":"unavailable",
                "production_deployed_records":None,
                "notice":"Configured source-only index missing, corrupt, wrong vintage or invalid; no coverage conclusion"}
    return {"sources":result,"physical_site_linkage":"REVIEW_ONLY",
            "insurance_loss_evidence":"NONE_VERIFIED_BY_LANE_B",
            "production_deployment":"UNASSESSED_BY_ADAPTER",
            "notice":"Private index mount readiness is NOT deployed public-app data or verified insured risk"}

def _sanitize(result,include_raw=False):
    if include_raw:return result
    if isinstance(result,dict):
        return {key:_sanitize(value,include_raw) for key,value in result.items()
                if key not in ("raw_attributes","reported_attributes")}
    if isinstance(result,list):
        return [_sanitize(value,include_raw) for value in result]
    return result

def query_exact(source,native_id,*,year=None,activity_location=None,limit=25,offset=0,
                include_raw=False,environ=None):
    """Call only after the existing private service authenticates and authorizes user."""
    env=os.environ if environ is None else environ
    if source not in ENV:raise ValueError("Unknown EPA Lane B source")
    if not isinstance(native_id,str) or not 1<=len(native_id.strip())<=160:
        raise ValueError("Exact source-reported identifier required")
    if type(limit)!=int or not 1<=limit<=50 or type(offset)!=int or not 0<=offset<=100000:
        raise ValueError("Bounded query limit/offset required")
    if type(include_raw)!=bool:raise ValueError("Unexpected raw disclosure option")
    directory=_directory(source,env)
    if directory is None:raise InvalidSourceIndex("Private source-only index not mounted")
    if source=="rmp_public":
        if year is not None or activity_location is not None or offset:
            raise ValueError("RMP public key lookup has no reporting-year, state or offset filters")
        result=rmp_lookup(directory,native_id,limit=limit)
    elif source=="tri":
        allowed=reporting_years(env.get(TRI_YEARS_ENV,""))
        if type(year)!=int or year not in allowed or activity_location is not None:
            raise ValueError("Query one configured TRI year by native reporting ID")
        db,manifest=_tri_index(directory,year)
        result=regulatory_lookup(db,manifest,"tri",native_id,limit=limit,offset=offset)
        result["reporting_year"]=year
    else:
        if year is not None or (source=="echo" and activity_location is not None):
            raise ValueError("Source has no TRI reporting-year filter")
        if source=="rcra" and (not isinstance(activity_location,str) or
            re.fullmatch(r"[A-Za-z]{2}",activity_location) is None):
            raise ValueError("RCRA exact native ID and two-character ACTIVITY_LOCATION required")
        result=regulatory_lookup(directory/(source+".sqlite"),
            directory/(source+".manifest.json"),source,native_id,
            activity_location=activity_location,limit=limit,offset=offset)
    result["source_identity_association"]="NATIVE_SOURCE_KEY_ONLY_NOT_VERIFIED_PHYSICAL_SITE"
    result["site_and_insured_loss_status"]="UNASSESSED"
    return _sanitize(result,include_raw=include_raw)

def build_router():
    """Coordinator may app.include_router(build_router()) *after* add_security(app).

    No endpoint exists until explicitly imported and mounted by Lane E.
    This router inherits the already configured app-wide security middleware;
    production tenant authorization must be added by the coordinator.
    """
    from fastapi import APIRouter,HTTPException,Query,Request
    router=APIRouter(prefix="/api/epa/lane-b",tags=["EPA regulatory source identities"])
    def authenticated(request):
        if not getattr(request.state,"actor",None):
            raise HTTPException(status_code=401,detail="Authenticated private user required")
        if os.environ.get("FACILITY_RISK_LANE_B_ROUTES_ENABLED")!="1":
            raise HTTPException(status_code=503,detail="EPA source-only private routes not enabled")
    @router.get("/status")
    def source_mounts(request:Request):
        authenticated(request)
        return status()
    @router.get("/{source}/identity")
    def exact_source_identity(request:Request,source:str,
                              native_id:str=Query(...,min_length=1,max_length=160),
                              year:int|None=Query(None,ge=1987,le=2024),
                              activity_location:str|None=None,
                              limit:int=Query(25,ge=1,le=50),
                              offset:int=Query(0,ge=0,le=100000),
                              include_raw:bool=False):
        authenticated(request)
        if include_raw and getattr(request.state,"role","") not in ("researcher","reviewer","admin"):
            raise HTTPException(status_code=403,detail="Raw authority fields require reviewed research permission")
        try:
            return query_exact(source,native_id,year=year,activity_location=activity_location,
                limit=limit,offset=offset,include_raw=include_raw)
        except ERRORS as exc:
            if isinstance(exc,ValueError) and not isinstance(exc,(InvalidSourceIndex,InvalidRMPIndex)):
                raise HTTPException(status_code=422,detail=str(exc)) from exc
            raise HTTPException(status_code=503,detail="EPA source index unavailable; no low-risk conclusion") from exc
    return router
