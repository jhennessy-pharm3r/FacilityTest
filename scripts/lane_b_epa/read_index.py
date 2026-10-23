"""Read-only, fail-closed source observation lookup for Lane B private integration.

Never returns a verified physical-site crosswalk or an insured loss.
The coordinator must provide authentication, tenant isolation and deployment.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import sqlite3

SOURCE_KINDS={
    "RCRA_FACILITIES.csv":("rcra_handler_identity",None,None),
    "RCRA_ENFORCEMENTS.csv":("rcra_enforcement","ENFORCEMENT_ACTION_DATE","ENFORCEMENT_IDENTIFIER"),
    "RCRA_EVALUATIONS.csv":("rcra_evaluation","EVALUATION_START_DATE","EVALUATION_IDENTIFIER"),
    "RCRA_VIOLATIONS.csv":("rcra_violation","DATE_VIOLATION_DETERMINED",None),
    "RCRA_VIOSNC_HISTORY.csv":("rcra_violation_snc_history","YRMONTH",None),
    "RCRA_NAICS.csv":("rcra_industry_code",None,None),
    "ECHO_EXPORTER.csv":("echo_facility_compliance_summary",None,None),
}
PRIVATE_TABLES=frozenset(("facilities","evidence","sec_findings","raw_snapshots","audit_events",
                          "insurance_policies","insurance_terms","facility_assets","review_approvals"))
ALLOWED_TABLES=frozenset(("observation","rejected","sqlite_stat1","sqlite_sequence"))
class InvalidSourceIndex(ValueError):pass

def _hashfile(path):
    digest=hashlib.sha256()
    with path.open("rb") as file:
        for part in iter(lambda:file.read(1048576),b""):digest.update(part)
    return digest.hexdigest()

@lru_cache(maxsize=8)
def _validated(dbpath,dbsize,dbmtime,manifestpath,mmtime,source):
    db=Path(dbpath);p=Path(manifestpath)
    manifest=json.loads(p.read_text(encoding="utf-8"))
    if (manifest.get("source")!=source or manifest.get("schema_version")!=2 or
        manifest.get("state")!="INDEXED" or manifest.get("deployment_state")!="NOT_DEPLOYED" or
        not re.fullmatch(r"[a-fA-F0-9]{64}",str(manifest.get("archive_sha256",""))) or
        not re.fullmatch(r"[a-fA-F0-9]{64}",str(manifest.get("index_sha256",""))) or
        manifest.get("index_bytes")!=dbsize or _hashfile(db)!=manifest["index_sha256"]):
        raise InvalidSourceIndex("Source database/provenance manifest mismatch; refuse service")
    uri=db.resolve().as_uri()+"?mode=ro&immutable=1"
    with sqlite3.connect(uri,uri=True) as conn:
        tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"observation","rejected"}.issubset(tables) or tables & PRIVATE_TABLES:
            raise InvalidSourceIndex("Unexpected source index tables or private data contamination")
        if conn.execute("PRAGMA quick_check").fetchone()[0]!="ok":
            raise InvalidSourceIndex("SQLite integrity validation failed")
        obs=conn.execute("SELECT COUNT(*) FROM observation WHERE source=?",(source,)).fetchone()[0]
        rej=conn.execute("SELECT COUNT(*) FROM rejected").fetchone()[0]
        if obs!=manifest.get("indexed_rows") or rej!=manifest.get("rejected_rows") or (
           obs+rej!=manifest.get("scanned_rows")):
            raise InvalidSourceIndex("Source rows not reconciled to manifest")
    return {"source":source,"indexed_rows":obs,"rejected_rows":rej,
            "source_archive_sha256":manifest["archive_sha256"],
            "index_sha256":manifest["index_sha256"],"source_url":manifest.get("source_url"),
            "retrieved_utc":manifest.get("retrieved_utc"),
            "source_state":"INDEXED_NOT_DEPLOYED",
            "notice":"Source observations only; program identity and coordinates are not verified insured properties or losses"}

def source_status(index_path,manifest_path,source):
    if source not in ("echo","tri","rcra"):raise InvalidSourceIndex("Unsupported source")
    db=Path(index_path).expanduser().resolve();p=Path(manifest_path).expanduser().resolve()
    if not db.is_file() or not p.is_file():raise InvalidSourceIndex("Source index and manifest must both exist")
    wal=Path(str(db)+"-wal")
    if wal.is_file() and wal.stat().st_size:raise InvalidSourceIndex("Uncheckpointed source WAL")
    stat=db.stat()
    return _validated(str(db),stat.st_size,stat.st_mtime_ns,str(p),p.stat().st_mtime_ns,source)

@contextmanager
def open_source(index_path,manifest_path,source):
    facts=source_status(index_path,manifest_path,source)
    db=Path(index_path).resolve()
    conn=sqlite3.connect(db.as_uri()+"?mode=ro&immutable=1",uri=True,timeout=15)
    try:
        conn.row_factory=sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        yield conn,facts
    finally:conn.close()

def _date(value):
    if not value:return None,None
    text=str(value).strip()
    for fmt,prec in (("%m/%d/%Y","day"),("%Y-%m-%d","day"),
                     ("%Y%m","month"),("%Y","year")):
        try:
            dt=datetime.strptime(text,fmt)
            return dt.strftime("%Y-%m-%d") if prec=="day" else (
                dt.strftime("%Y-%m") if prec=="month" else dt.strftime("%Y")),prec
        except ValueError:pass
    return None,"unparsed_source_text"

def _classify(source,row):
    d=json.loads(row["payload"])
    member=row["member"]
    if source=="rcra":
        kind,dayfield,eventkey=SOURCE_KINDS.get(member,("rcra_other",None,None))
    elif source=="tri":
        kind,dayfield,eventkey=("tri_chemical_report","1_YEAR","36_DOC_CTRL_NUM")
    else:
        kind,dayfield,eventkey=("echo_facility_compliance_summary","FAC_DATE_LAST_INSPECTION",None)
    dt,precision=_date(d.get(dayfield)) if dayfield else (None,None)
    native_event=(d.get(eventkey) or "").strip() if eventkey else ""
    if source=="rcra":
        fields={
            "reported_handler_name":d.get("FACILITY_NAME"),
            "reported_enforcement_type":d.get("ENFORCEMENT_TYPE"),
            "reported_enforcement_agency":d.get("ENFORCEMENT_AGENCY"),
            "reported_evaluation_type":d.get("EVALUATION_TYPE"),
            "reported_evaluation_agency":d.get("EVALUATION_AGENCY"),
            "reported_violation_type":d.get("VIOLATION_TYPE"),
            "reported_return_to_compliance_date":d.get("ACTUAL_RTC_DATE"),
            "reported_generator_class":d.get("HREPORT_UNIVERSE_RECORD"),
            "reported_enforcement_amounts_raw":{k:d[k] for k in ("PMP_AMOUNT","FMP_AMOUNT","FSC_AMOUNT","SCR_AMOUNT") if d.get(k)},
        }
    elif source=="tri":
        fields={
            "reporting_year":d.get("1_YEAR"),
            "reported_chemical":d.get("37_CHEMICAL"),
            "reported_chemical_identifier":d.get("39_TRI_CHEMICAL_COMPOUND_ID"),
            "reported_cas":d.get("40_CAS"),
            "reported_form_type":d.get("49_FORM_TYPE"),
            "reported_unit":d.get("50_UNIT_OF_MEASURE"),
            "total_releases_raw":d.get("107_TOTAL_RELEASES"),
            "on_site_release_total_raw":d.get("65_ON_SITE_RELEASE_TOTAL"),
            "off_site_release_total_raw":d.get("88_OFF_SITE_RELEASE_TOTAL"),
            "reported_frs_identifier":d.get("3_FRS_ID"),
        }
    else:
        fields={
            "reported_facility_name":d.get("FAC_NAME"),
            "reported_compliance_status":d.get("FAC_COMPLIANCE_STATUS"),
            "reported_inspection_count":d.get("FAC_INSPECTION_COUNT"),
            "reported_formal_action_count":d.get("FAC_FORMAL_ACTION_COUNT"),
            "reported_total_penalties_raw":d.get("FAC_TOTAL_PENALTIES"),
            "reported_program_flags":{k:d.get(k) for k in ("AIR_FLAG","NPDES_FLAG","RCRA_FLAG","TRI_FLAG")},
        }
    return {"source":source,"source_identifier":row["source_id"],
            "activity_location":row["activity_location"] or None,
            "regulatory_observation_kind":kind,
            "native_event_identifier":native_event or None,
            "native_event_id_quality":"reported" if native_event else "row_fingerprint_only",
            "date":dt,"date_precision":precision,"date_role":dayfield,
            "original_date_text":d.get(dayfield) if dayfield else None,
            "source_table":member,"source_row_number":row["row_number"],
            "source_record_sha256":row["row_sha256"],
            "reported_latitude":row["latitude"],"reported_longitude":row["longitude"],
            "source_reported_findings":fields,
            "raw_attributes":d,
            "interpretation":"Regulatory source observation; not physical-site match, verified damage, or insured claim"}

def lookup(index_path,manifest_path,source,source_id,*,activity_location=None,limit=50,offset=0):
    if not isinstance(source_id,str) or not 1<=len(source_id.strip())<=160:
        raise ValueError("Exact native source ID required")
    if type(limit)!=int or not 1<=limit<=100 or type(offset)!=int or not 0<=offset<=100000:
        raise ValueError("Invalid bounded query pagination")
    if activity_location is not None and (source!="rcra" or
         not re.fullmatch(r"[A-Za-z]{2}",activity_location)):
        raise ValueError("RCRA activity_location must be a two-letter regulator code")
    with open_source(index_path,manifest_path,source) as (db,facts):
        clauses=["source=?","source_id=?"];values=[source,source_id.strip()]
        if activity_location is not None:
            clauses.append("activity_location=?");values.append(activity_location.upper())
        where=" AND ".join(clauses)
        total=db.execute("SELECT COUNT(*) FROM observation WHERE "+where,values).fetchone()[0]
        result=list(db.execute("SELECT * FROM observation WHERE "+where+
            " ORDER BY member,row_number LIMIT ? OFFSET ?",[*values,limit,offset]))
    return {"source":source,"native_source_id":source_id,"activity_location_filter":activity_location,
            "observations_available":total,"returned":len(result),
            "rows":[_classify(source,r) for r in result],
            "source_provenance":facts,"physical_site_linkage":"NOT_REVIEWED"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",choices=["echo","tri","rcra"],required=True)
    p.add_argument("--index",required=True)
    p.add_argument("--manifest",required=True)
    p.add_argument("--source-id",required=True)
    p.add_argument("--activity-location")
    p.add_argument("--limit",type=int,default=10)
    a=p.parse_args()
    print(json.dumps(lookup(a.index,a.manifest,a.source,a.source_id,
        activity_location=a.activity_location,limit=a.limit),indent=2))
if __name__=="__main__":main()
