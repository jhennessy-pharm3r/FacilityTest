"""PHMSA WMS enforcement case export: source-specific normalized review context.

This published enforcement *case/action* table is NOT the PHMSA pipeline
incident census. A Report_Number is a candidate evidence cross-reference, not
an independent accident, a physical insured site, or a confirmed finding.
"""
from __future__ import annotations
from collections import Counter
import csv
import io
import gzip
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
try:
    from scripts.industrial_incident_io import gzip_csv_writer
    from scripts.build_industrial_incidents import digest, as_date
except ModuleNotFoundError:
    from industrial_incident_io import gzip_csv_writer
    from build_industrial_incidents import digest, as_date

REQUIRED = ("CPF_Number","WMS_Activity_Seq","Operator_ID","Operator_Name",
            "Pipeline_Type","Case_Type","Case_Status","Opened_Date",
            "Report_Type","Report_Number","Data_as_of")
COLUMNS = ("source_row_number","source_snapshot","case_number","wms_activity_seq",
           "operator_id","operator_name","pipeline_type","case_type","case_status",
           "opened_date","opened_date_precision","original_opened_date",
           "report_type","report_number","report_linkage_quality",
           "data_as_of","location_semantics","evidence_status","site_link_status")
SOURCE = "https://primis.phmsa.dot.gov/enforcement-documents/PHMSA%20Pipeline%20Enforcement%20Raw%20Data.txt"
SOURCE_NAME = "PHMSA Work Management System pipeline enforcement cases"

def parse_date(value):
    try:
        return as_date(value)
    except (TypeError,ValueError):
        return "", "unparseable_or_absent"

def build(raw,normalized,manifest,*,snapshot="2026-10-02",minimum_rows=1000):
    raw,normalized,manifest=map(Path,(raw,normalized,manifest))
    normalized.parent.mkdir(parents=True,exist_ok=True)
    manifest.parent.mkdir(parents=True,exist_ok=True)
    tmp=Path(str(normalized)+".part")
    count=accepted=rejected=linked=partial_ref=invalid_dates=0
    missing_cases=0
    case_counts=Counter()
    activity_counts=Counter()
    report_refs=set()
    stages=Counter()
    pipeline_types=Counter()
    min_date=max_date=None
    try:
        with raw.open("r",encoding="cp1252",errors="strict",newline="") as source, gzip_csv_writer(tmp) as target:
            reader=csv.DictReader(source,dialect="excel-tab")
            if len(reader.fieldnames or []) != len(set(reader.fieldnames or [])):
                raise ValueError("PHMSA enforcement source contains duplicate column headers")
            if not set(REQUIRED).issubset(reader.fieldnames or []):
                raise ValueError("PHMSA WMS enforcement source schema changed")
            writer=csv.DictWriter(target,fieldnames=COLUMNS)
            writer.writeheader()
            for rowno,row in enumerate(reader,2):
                if not any(str(x or "").strip() for x in row.values()):
                    continue
                count+=1
                if None in row:
                    rejected+=1
                    continue
                cid=str(row["CPF_Number"] or "").strip()
                activity=str(row["WMS_Activity_Seq"] or "").strip()
                if not cid or not activity:
                    rejected+=1
                    missing_cases+=1
                    continue
                case_counts[cid]+=1
                activity_counts[(cid,activity)]+=1
                rpt_type=str(row["Report_Type"] or "").strip()
                rpt_number=str(row["Report_Number"] or "").strip()
                if rpt_type and rpt_number:
                    linked+=1
                    report_refs.add((rpt_type,rpt_number))
                    link_status="native_report_reference_unverified_crosswalk"
                elif rpt_type or rpt_number:
                    partial_ref+=1
                    link_status="partial_report_reference_no_link"
                else:
                    link_status="not_report_linked"
                opened,precision=parse_date(row.get("Opened_Date"))
                if not opened:
                    invalid_dates+=1
                else:
                    min_date=min(min_date,opened) if min_date else opened
                    max_date=max(max_date,opened) if max_date else opened
                stages[str(row["Case_Status"] or "").strip() or "<missing>"]+=1
                pipeline_types[str(row["Pipeline_Type"] or "").strip() or "<missing>"]+=1
                writer.writerow(dict(zip(COLUMNS,(
                    rowno,snapshot,cid,activity,
                    str(row["Operator_ID"] or "").strip(),
                    str(row["Operator_Name"] or "").strip(),
                    str(row["Pipeline_Type"] or "").strip(),
                    str(row["Case_Type"] or "").strip(),
                    str(row["Case_Status"] or "").strip(),
                    opened,precision,str(row["Opened_Date"] or "").strip(),
                    rpt_type,rpt_number,link_status,
                    str(row["Data_as_of"] or "").strip(),
                    "PHMSA_region_not_incident_site",
                    "PHMSA_public_enforcement_case_not_incident_census",
                    "candidate_only_not_matched"
                ))))
                accepted+=1
        if accepted<minimum_rows:raise ValueError("PHMSA source below expected minimum rows")
        tmp.replace(normalized)
        report={
            "source":SOURCE_NAME,"url":SOURCE,"source_snapshot":snapshot,
            "obtained_at":datetime.now(timezone.utc).isoformat(),
            "text_encoding":"cp1252_verified","delimiter":"tab",
            "raw_bytes":raw.stat().st_size,"raw_sha256":digest(raw),
            "normalized_sha256":digest(normalized),
            "raw_nonempty_rows":count,"accepted_case_rows":accepted,
            "rejected_case_rows":rejected,"rejected_missing_case_key":missing_cases,
            "native_case_ids":len(case_counts),
            "duplicate_case_numbers":sum(v-1 for v in case_counts.values() if v>1),
            "duplicate_case_activity_composites":sum(v-1 for v in activity_counts.values() if v>1),
            "report_reference_rows":linked,
            "distinct_typed_report_references":len(report_refs),
            "partial_report_reference_rows":partial_ref,
            "unparseable_or_missing_opened_dates":invalid_dates,
            "opened_date_min":min_date,"opened_date_max":max_date,
            "case_status_counts":dict(sorted(stages.items())),
            "pipeline_type_counts":dict(sorted(pipeline_types.items())),
            "report_grain":"enforcement_case_row_NOT_incident_report",
            "incident_census_rows":"NOT_TESTED",
            "incident_site_coordinates":"NOT_PRESENT",
            "verified_insured_sites":0,"durable_production_index":0,"app_deployed":0,
            "note":"This is an enforcement case cohort, NOT complete PHMSA pipeline/hazmat incident source. Report references may repeat across cases."
        }
        manifest.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        validate(normalized,report)
        return report
    finally:
        tmp.unlink(missing_ok=True)

def validate(path,report):
    if digest(path)!=report["normalized_sha256"]:
        raise ValueError("PHMSA enforcement normalized checksum mismatch")
    counts=Counter()
    case_numbers=set()
    reports=set()
    n=0
    with gzip.open(path,"rt",encoding="utf-8",newline="") as source:
        reader=csv.DictReader(source)
        if tuple(reader.fieldnames or ())!=COLUMNS:raise ValueError("PHMSA enforcement normalization schema changed")
        for row in reader:
            if not row["case_number"] or not row["wms_activity_seq"] or not row["source_row_number"]:
                raise ValueError("PHMSA enforcement missing native case/activity identifier")
            if row["site_link_status"]!="candidate_only_not_matched":
                raise ValueError("PHMSA case illegally auto-matched to physical site")
            counts[row["source_row_number"]]+=1
            case_numbers.add(row["case_number"])
            if row["report_linkage_quality"]=="native_report_reference_unverified_crosswalk":
                reports.add((row["report_type"],row["report_number"]))
            n+=1
    if any(v!=1 for v in counts.values()) or n!=report["accepted_case_rows"] or len(case_numbers)!=report["native_case_ids"] or len(reports)!=report["distinct_typed_report_references"]:
        raise ValueError("PHMSA enforcement output native identity/count audit mismatch")
    if n+report["rejected_case_rows"]!=report["raw_nonempty_rows"]:
        raise ValueError("PHMSA enforcement input/output totals disagree")
    return True

def index_cases(normalized,manifest,db_path):
    """Disposable source-only source-identity index; no facility/company rollups."""
    db_path=Path(db_path)
    if db_path.exists():raise ValueError("PHMSA case index exists; refusing overwrite")
    report=json.loads(Path(manifest).read_text(encoding="utf-8"))
    validate(normalized,report)
    conn=sqlite3.connect(db_path)
    try:
        with conn:
            conn.executescript("""CREATE TABLE enforcement_cases (
               source_row_number INTEGER PRIMARY KEY, case_number TEXT NOT NULL,
               wms_activity_seq TEXT NOT NULL, operator_id TEXT, pipeline_type TEXT,
               case_status TEXT, opened_date TEXT, report_type TEXT, report_number TEXT,
               source_row_json TEXT NOT NULL, site_link_status TEXT NOT NULL
                  CHECK(site_link_status='candidate_only_not_matched')
            );
            CREATE INDEX enforcement_cases_native ON enforcement_cases(case_number,wms_activity_seq);
            CREATE INDEX enforcement_cases_report ON enforcement_cases(report_type,report_number);
            CREATE INDEX enforcement_cases_operator ON enforcement_cases(operator_id);
            """)
            with gzip.open(normalized,"rt",encoding="utf-8",newline="") as stream:
                for row in csv.DictReader(stream):
                    conn.execute("INSERT INTO enforcement_cases VALUES (?,?,?,?,?,?,?,?,?,?,?)",(
                        int(row["source_row_number"]),row["case_number"],row["wms_activity_seq"],
                        row["operator_id"],row["pipeline_type"],row["case_status"],
                        row["opened_date"],row["report_type"],row["report_number"],
                        json.dumps(row,ensure_ascii=False,sort_keys=True),row["site_link_status"]))
            quick=conn.execute("PRAGMA quick_check").fetchone()[0]
            n,unique_case,linked,distinct_link=conn.execute("""SELECT COUNT(*),
                  COUNT(DISTINCT case_number),
                  SUM(CASE WHEN report_type<>'' AND report_number<>'' THEN 1 ELSE 0 END),
                  COUNT(DISTINCT CASE WHEN report_type<>'' AND report_number<>''
                   THEN report_type || '|' || report_number ELSE NULL END)
                  FROM enforcement_cases""").fetchone()
            if quick!="ok" or n!=report["accepted_case_rows"] or unique_case!=report["native_case_ids"] or linked!=report["report_reference_rows"] or distinct_link!=report["distinct_typed_report_references"]:
                raise ValueError("PHMSA enforcement ephemeral SQL case index does not reconcile")
        return {"state":"SOURCE_ENFORCEMENT_CASE_INDEXED_EPHEMERAL_NOT_DEPLOYED",
                "source_case_rows":n,"unique_case_numbers":unique_case,
                "incident_report_reference_rows":linked,
                "distinct_typed_report_references":distinct_link,
                "sqlite_quick_check":quick,"durable_production_index":0,
                "deployed":0,"verified_incident_census":False}
    finally:
        conn.close()
