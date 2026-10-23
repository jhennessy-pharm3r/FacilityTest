"""Official PHMSA enforcement is an incident-reference subset, not accident census."""
import csv
import gzip
import json
import sqlite3
from scripts.build_phmsa_enforcement import build, validate, index_cases, REQUIRED
import pytest

def source_file(tmp_path):
    path=tmp_path/"official-enforcement.txt"
    rows=[
        {"CPF_Number":"42026005CAO","WMS_Activity_Seq":"41322",
         "Operator_ID":"000122","Operator_Name":"Example Company",
         "Pipeline_Type":"Hazardous Liquid","Case_Type":"CAO","Case_Status":"Open",
         "Opened_Date":"02/05/2026","Report_Type":"Incident",
         "Report_Number":"20250058","Data_as_of":"10/02/2026"},
        {"CPF_Number":"42026006CAO","WMS_Activity_Seq":"41323",
         "Operator_ID":"000122","Operator_Name":"Example Company",
         "Pipeline_Type":"Hazardous Liquid","Case_Type":"CAO","Case_Status":"Open",
         "Opened_Date":"02/06/2026","Report_Type":"Incident",
         "Report_Number":"20250058","Data_as_of":"10/02/2026"},
        {"CPF_Number":"42026007CAO","WMS_Activity_Seq":"41324",
         "Operator_ID":"000123","Operator_Name":"Second Company",
         "Pipeline_Type":"Gas","Case_Type":"CAO","Case_Status":"Closed",
         "Opened_Date":"02/07/2026","Report_Type":"",
         "Report_Number":"","Data_as_of":"10/02/2026"}
    ]
    with path.open("w",encoding="cp1252",newline="") as fh:
        writer=csv.DictWriter(fh,fieldnames=REQUIRED,dialect="excel-tab")
        writer.writeheader()
        writer.writerows(rows)
    return path

def test_phmsa_enforcement_case_grain_and_repeated_report_refs(tmp_path):
    raw=source_file(tmp_path)
    out=tmp_path/"enforcement.csv.gz"
    manifest=tmp_path/"source.json"
    m=build(raw,out,manifest,minimum_rows=3)
    assert m["raw_nonempty_rows"]==3
    assert m["accepted_case_rows"]==3
    assert m["rejected_case_rows"]==0
    assert m["native_case_ids"]==3
    assert m["report_reference_rows"]==2
    assert m["distinct_typed_report_references"]==1
    assert m["incident_census_rows"]=="NOT_TESTED"
    assert validate(out,m)
    with gzip.open(out,"rt",newline="") as stream:
        rows=list(csv.DictReader(stream))
    assert rows[0]["operator_id"]=="000122"
    assert rows[0]["report_linkage_quality"]=="native_report_reference_unverified_crosswalk"
    assert all(x["site_link_status"]=="candidate_only_not_matched" for x in rows)
    other=build(raw,tmp_path/"repeat.csv.gz",tmp_path/"repeat.json",minimum_rows=3)
    assert m["normalized_sha256"]==other["normalized_sha256"]
    db=tmp_path/"case-index.sqlite"
    q=index_cases(out,manifest,db)
    assert q["source_case_rows"]==3
    assert q["incident_report_reference_rows"]==2
    assert q["distinct_typed_report_references"]==1
    assert q["deployed"]==0
    with sqlite3.connect(db) as con:
        assert con.execute("SELECT COUNT(*) FROM enforcement_cases WHERE report_number='20250058'").fetchone()[0]==2
        assert con.execute("SELECT COUNT(*) FROM enforcement_cases WHERE operator_id='000122'").fetchone()[0]==2
    with pytest.raises(ValueError,match="exists"):
        index_cases(out,manifest,db)

def test_phmsa_enforcement_invalid_schema_and_sha_fail(tmp_path):
    raw=source_file(tmp_path)
    out=tmp_path/"out.csv.gz"
    mfile=tmp_path/"m.json"
    m=build(raw,out,mfile,minimum_rows=3)
    out.write_bytes(out.read_bytes()+b"TAMPER")
    with pytest.raises(ValueError,match="checksum"):
        validate(out,m)
    source=raw.read_text(encoding="cp1252").replace("CPF_Number","random_wrong_key")
    raw.write_text(source,encoding="cp1252")
    with pytest.raises(ValueError,match="schema changed"):
        build(raw,tmp_path/"other.gz",tmp_path/"other.json",minimum_rows=3)

def test_missing_native_case_rejected_but_does_not_drop_valid_rows(tmp_path):
    raw=source_file(tmp_path)
    data=raw.read_text(encoding="cp1252")
    data+="\t".join(["","33444","30123","Unknown","Gas","CAO","Open","02/08/2026","","","10/02/2026"])+"\n"
    raw.write_text(data,encoding="cp1252")
    m=build(raw,tmp_path/"good.gz",tmp_path/"qa.json",minimum_rows=3)
    assert m["accepted_case_rows"]==3
    assert m["rejected_case_rows"]==1
    assert m["rejected_missing_case_key"]==1
