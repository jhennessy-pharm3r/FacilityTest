"""Official PHMSA Pipeline Failure Investigation REPORT INDEX, distinct from incidents.

The PHMSA public investigation catalog selects a very small number of
pipeline failures. Each index row links a published report; it is neither a
census of reportable pipeline incidents nor proof of insured losses or facility
identity. Preserve source table row number, OpID, reported event date, report
posting date, text of cause, state, source URL, and report detail URL.
"""
from __future__ import annotations
from collections import Counter
import csv
from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import urljoin,urlsplit
from html.parser import HTMLParser

try:
    from scripts.build_industrial_incidents import digest
    from scripts.industrial_incident_io import gzip_csv_writer
except ModuleNotFoundError:
    from build_industrial_incidents import digest
    from industrial_incident_io import gzip_csv_writer

URL="https://www.phmsa.dot.gov/safety-reports/pipeline-failure-investigation-reports"
COLUMN_NAMES=("Operator Name","Operator Id","System Type","Apparent Cause",
              "State","Failure Date","Date Posted")
FIELDS=("source","source_snapshot","source_row_number","source_observation_key",
        "operator_name_as_reported","operator_id_as_reported","pipeline_system_type",
        "apparent_cause_as_reported","state_as_reported","failure_date","failure_date_raw",
        "posted_date","posted_date_raw","date_quality","detail_report_url",
        "detail_link_status","evidence_status","site_link_status","source_document")
EVIDENCE="PHMSA_published_failure_investigation_catalog_not_independent_insured_loss"

def agency_date(value):
    raw=" ".join(str(value or "").replace("\xa0"," ").split())
    raw=re.sub(r"\bSept\b","Sep",raw,flags=re.I)
    raw=re.sub(r"(\d{1,2})/(\d{4})",r"\1, \2",raw)
    raw=re.sub(r"\s*,\s*",", ",raw)
    for fmt in ("%b %d, %Y","%B %d, %Y","%b %d %Y","%B %d %Y","%Y-%m-%d"):
        try:
            return datetime.strptime(raw,fmt).date().isoformat()
        except ValueError:
            continue
    return ""

def official_detail_url(href):
    url=urljoin(URL,href or "")
    parsed=urlsplit(url)
    if parsed.scheme!="https" or parsed.hostname not in ("www.phmsa.dot.gov","phmsa.dot.gov"):
        return ""
    return url

class _CatalogHTMLParser(HTMLParser):
    """Small dependency-free parser that preserves exact publisher table rows."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables=[]
        self.table=None
        self.row=None
        self.cell=None

    def handle_starttag(self,tag,attrs):
        if tag=="table" and self.table is None:
            self.table=[]
        elif tag=="tr" and self.table is not None and self.row is None:
            self.row=[]
        elif tag in ("td","th") and self.row is not None and self.cell is None:
            self.cell={"tag":tag,"text":[],"href":""}
        elif tag=="a" and self.cell is not None and not self.cell["href"]:
            self.cell["href"]=dict(attrs).get("href","")

    def handle_data(self,data):
        if self.cell is not None:
            self.cell["text"].append(data)

    def handle_endtag(self,tag):
        if tag in ("td","th") and self.cell is not None:
            self.row.append({
                "tag":self.cell["tag"],
                "text":" ".join(" ".join(self.cell["text"]).replace("\xa0"," ").split()),
                "href":self.cell["href"]})
            self.cell=None
        elif tag=="tr" and self.row is not None:
            self.table.append(self.row)
            self.row=None
        elif tag=="table" and self.table is not None:
            self.tables.append(self.table)
            self.table=None

def extract_index(raw_html,snapshot,*,min_rows=20):
    parser=_CatalogHTMLParser()
    parser.feed(raw_html.decode("utf-8-sig",errors="strict"))
    parser.close()
    table=None
    for candidate in parser.tables:
        if candidate and tuple(c["text"] for c in candidate[0][:len(COLUMN_NAMES)])==COLUMN_NAMES:
            table=candidate
            break
    if table is None:
        raise ValueError("PHMSA official investigations table headings missing or changed")
    rows=[]
    totals=Counter()
    seen_composite=Counter()
    opids=Counter()
    states=Counter()
    system_types=Counter()
    cause_values=Counter()
    first_date=last_date=None
    for source_row,cells in enumerate(table[1:],2):
        cells=[c for c in cells if c["tag"]=="td"]
        if not cells:
            continue
        totals["source_table_nonempty_rows"]+=1
        if len(cells)!=len(COLUMN_NAMES):
            totals["rejected_invalid_column_count"]+=1
            continue
        values=[c["text"] for c in cells]
        operator,opid,system,cause,state,raw_failure,raw_posted=values
        href=cells[0]["href"]
        link=official_detail_url(href) if href else ""
        failure=agency_date(raw_failure)
        posted=agency_date(raw_posted)
        if not operator or not cause or not link or not failure:
            totals["rejected_missing_publisher_identity_or_date"]+=1
            continue
        if not opid:
            totals["missing_source_operator_id"]+=1
        if not posted:
            totals["missing_or_invalid_posted_date"]+=1
        if posted and posted<failure:
            totals["posted_date_earlier_than_failure_date"]+=1
        if state.upper() in ("OCS","OFFSHORE",""):
            totals["offshore_or_unresolved_state"]+=1
        date_quality="posted_precedes_failure" if posted and posted<failure else (
            "posted_date_missing" if not posted else "parsed_source_dates")
        # This is an index observation key, not a native PHMSA incident report
        # number. Keep row number and detail URL; do not dedup repeated pages.
        key=f"phmsa-investigation-index:{snapshot}:{source_row}"
        composite=(opid, failure, state,link)
        seen_composite[composite]+=1
        if opid:
            opids[opid]+=1
        states[state or "<missing>"]+=1
        system_types[system or "<missing>"]+=1
        cause_values[cause or "<missing>"]+=1
        first_date=min(first_date,failure) if first_date else failure
        last_date=max(last_date,failure) if last_date else failure
        rows.append(dict(zip(FIELDS,(
            "phmsa_failure_investigation_index",snapshot,source_row,key,
            operator,opid,system,cause,state,failure,raw_failure,
            posted,raw_posted,date_quality,link,
            "listed_official_phmsa_detail_page_unchecked",
            EVIDENCE,"candidate_only_not_matched",URL
        ))))
    if len(rows)<min_rows:
        raise ValueError(f"PHMSA published investigation index unexpectedly small: {len(rows)}")
    totals["accepted_publisher_index_rows"]=len(rows)
    totals["distinct_nonempty_operator_ids"]=len(opids)
    totals["source_composite_repeated_observations"]=sum(n-1 for n in seen_composite.values() if n>1)
    totals["first_failure_date"]=first_date
    totals["last_failure_date"]=last_date
    totals["distinct_state_strings"]=len(states)
    totals["distinct_system_type_strings"]=len(system_types)
    totals["distinct_apparent_cause_strings"]=len(cause_values)
    return rows,dict(totals),dict(sorted(states.items())),dict(sorted(system_types.items()))

def build(raw_path,output_path,manifest_path,*,snapshot,minimum_rows=20):
    raw,output,manifest=map(Path,(raw_path,output_path,manifest_path))
    output.parent.mkdir(parents=True,exist_ok=True)
    manifest.parent.mkdir(parents=True,exist_ok=True)
    part=Path(str(output)+".part")
    try:
        rows,counts,states,systems=extract_index(raw.read_bytes(),snapshot,min_rows=minimum_rows)
        with gzip_csv_writer(part) as file:
            writer=csv.DictWriter(file,fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        part.replace(output)
        audit={
            "source":"PHMSA public Pipeline Failure Investigation Reports INDEX",
            "source_url":URL,
            "source_snapshot":snapshot,
            "raw_html_bytes":raw.stat().st_size,
            "raw_html_sha256":digest(raw),
            "normalized_sha256":digest(output),
            "parsed_header_fields":list(COLUMN_NAMES),
            **counts,
            "rejected_index_rows":counts["source_table_nonempty_rows"]-len(rows),
            "state_values":states,"system_type_values":systems,
            "source_id_policy":"source_snapshot + publisher_index_row_number + detail_report_url; NOT incident report identity",
            "first_party_links_only":True,
            "verified_report_pdfs":0,
            "identical_incident_matches_to_other_agencies":0,
            "insured_facility_matches":0,
            "external_accident_census_coverage":"NOT_CENSUS_SELECTIVE_INVESTIGATIONS",
            "durable_production_indexed":0,"app_deployed":0,
            "validated_at":datetime.now(timezone.utc).isoformat()
        }
        manifest.write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
        validate(output,audit)
        return audit
    finally:
        part.unlink(missing_ok=True)

def validate(source_path,manifest):
    if digest(source_path)!=manifest["normalized_sha256"]:
        raise ValueError("PHMSA failure index normalized SHA mismatch")
    count=0
    ids=set()
    with gzip.open(source_path,"rt",encoding="utf-8",newline="") as stream:
        reader=csv.DictReader(stream)
        if tuple(reader.fieldnames or ())!=FIELDS:
            raise ValueError("PHMSA failure report normalized schema changed")
        for row in reader:
            key=row["source_observation_key"]
            if key in ids or not key.startswith("phmsa-investigation-index:"+manifest["source_snapshot"]+":"):
                raise ValueError("PHMSA duplicate index source row or vintage conflict")
            ids.add(key)
            if not row["detail_report_url"].startswith("https://www.phmsa.dot.gov/"):
                raise ValueError("Non-first-party PHMSA investigation detail URL")
            if row["site_link_status"]!="candidate_only_not_matched":
                raise ValueError("Unreviewed physical facility link in PHMSA investigation index")
            if not row["failure_date"] or not row["operator_name_as_reported"]:
                raise ValueError("Incomplete normalized publisher index record")
            count+=1
    if (count!=manifest["accepted_publisher_index_rows"]
        or count+manifest["rejected_index_rows"]!=manifest["source_table_nonempty_rows"]):
        raise ValueError("PHMSA failure index counts fail source reconciliation")
    return True

def index(source_path,manifest_path,db_path):
    report=json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    validate(source_path,report)
    db_path=Path(db_path)
    if db_path.exists():
        raise ValueError("PHMSA investigation SQLite already exists; refuse overwrite")
    try:
        conn=sqlite3.connect(db_path)
        with conn:
            conn.executescript("""
                CREATE TABLE investigation_catalog(
                  source_observation_key TEXT PRIMARY KEY,
                  source_snapshot TEXT NOT NULL,
                  source_row_number INTEGER NOT NULL,
                  operator_id TEXT,system_type TEXT,cause TEXT,state TEXT,
                  failure_date TEXT NOT NULL,posted_date TEXT,
                  date_quality TEXT NOT NULL,detail_report_url TEXT NOT NULL,
                  source_row_json TEXT NOT NULL,
                  site_link_status TEXT NOT NULL CHECK(site_link_status='candidate_only_not_matched')
                ) WITHOUT ROWID;
                CREATE INDEX investigation_operator_date ON investigation_catalog(operator_id,failure_date);
                CREATE INDEX investigation_state_date ON investigation_catalog(state,failure_date);
                CREATE INDEX investigation_detail_url ON investigation_catalog(detail_report_url);
            """)
            with gzip.open(source_path,"rt",encoding="utf-8",newline="") as stream:
                for row in csv.DictReader(stream):
                    conn.execute("""INSERT INTO investigation_catalog VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
                        row["source_observation_key"],row["source_snapshot"],int(row["source_row_number"]),
                        row["operator_id_as_reported"],row["pipeline_system_type"],row["apparent_cause_as_reported"],
                        row["state_as_reported"],row["failure_date"],row["posted_date"],row["date_quality"],
                        row["detail_report_url"],json.dumps(row,ensure_ascii=False,sort_keys=True),
                        row["site_link_status"]))
            quick=conn.execute("PRAGMA quick_check").fetchone()[0]
            total,opids=conn.execute("SELECT COUNT(*), COUNT(DISTINCT operator_id) FROM investigation_catalog").fetchone()
            n_candidates=conn.execute("SELECT COUNT(*) FROM investigation_catalog WHERE date_quality='posted_precedes_failure'").fetchone()[0]
            if quick!="ok" or total!=report["accepted_publisher_index_rows"] or opids!=report["distinct_nonempty_operator_ids"] or n_candidates!=report.get("posted_date_earlier_than_failure_date",0):
                raise ValueError("PHMSA investigation SQL integrity/count/date anomaly mismatch")
        conn.close()
        return {"state":"INDEXED_EPHEMERAL_NOT_DEPLOYED",
                "indexed_publisher_investigation_listings":total,
                "distinct_operator_ids":opids,
                "posted_before_failure_anomalies":n_candidates,
                "sqlite_quick_check":"ok","durable_production_indexed":0,
                "app_deployed":0,"physical_site_links":0}
    except BaseException:
        db_path.unlink(missing_ok=True)
        raise
