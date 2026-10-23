"""Lane C fixture gates: source IDs, uncertainty, rejected rows and tampering."""
import csv
import gzip
import json
from pathlib import Path
import zipfile
import pytest

from scripts.build_industrial_incidents import stage, validate, rows_from_file

URLS = {
    "nrc": "https://nrc.uscg.mil/FOIAFiles/CY25.xlsx",
    "csb": "https://www.csb.gov/news/incident-report-rule-form-/",
    "phmsa_pipeline": "https://www.phmsa.dot.gov/data-and-statistics/pipeline/source-data",
    "phmsa_hazmat": "https://www.phmsa.dot.gov/hazmat-program-management-data-and-statistics/data-operations/incident-statistics",
}
HEADERS = {
    "nrc": ("SEQNOS", "INCIDENT_DATE", "RESPONSIBLE_COMPANY"),
    "csb": ("Incident ID", "Incident Date", "Facility Name"),
    "phmsa_pipeline": ("REPORT_NUMBER", "INCIDENT_DATE", "OPERATOR_NAME"),
    "phmsa_hazmat": ("Report Number", "Date Of Incident", "Carrier Reporter Name"),
}
@pytest.mark.parametrize("source", list(URLS))
def test_stage_distinct_source_ids_without_site_attribution(tmp_path, source):
    keys = HEADERS[source]
    sourcefile = tmp_path / "official.csv"
    with sourcefile.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[*keys, "city", "state", "latitude", "longitude", "fatalities"])
        writer.writeheader()
        writer.writerows([
            dict(zip(keys, ("001", "2025-01-12", "Industrial Operator")), city="Houston", state="TX", latitude="29.77", longitude="-95.36", fatalities="2"),
            dict(zip(keys, ("002", "2025-01-13", "Warehouse")), city="Dallas", state="TX", latitude="999", longitude="0", fatalities="0"),
            dict(zip(keys, ("001", "2025-01-12", "duplicate"))),
            dict(zip(keys, ("003", "nonsense-date", "invalid"))),
            dict(zip(keys, ("", "2025-01-14", "no ID"))),
        ])
    out = tmp_path / "stage.csv.gz"
    manifest = tmp_path / "manifest.json"
    data = stage(source, sourcefile, out, manifest, source_url=URLS[source], minimum_rows=2)
    assert data["raw_rows"] == 5
    assert data["accepted_rows"] == 2
    assert data["rejected_rows"] == 3
    assert data["duplicate_source_ids"] == 1
    assert data["missing_coordinates"] == 1
    assert data["deployment"] == "NOT_DEPLOYED"
    assert validate(out, data)
    with gzip.open(out, "rt") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["source_id"] for r in rows] == ["001", "002"]
    assert all(r["site_link_state"] == "candidate_only_not_matched" for r in rows)
    assert rows[1]["coordinate_precision"] == "missing"
    if source == "nrc":
        assert rows[0]["evidence_state"] == "reported_unverified"
    out.write_bytes(out.read_bytes() + b"altered")
    with pytest.raises(ValueError, match="checksum"):
        validate(out, data)

def test_zip_requires_single_member_selection(tmp_path):
    archive = tmp_path / "reports.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("reports.csv", "report_number,incident_date\n001,2025-01-01\n")
        z.writestr("dictionary.csv", "field,description\nreport_number,identifier\n")
    with pytest.raises(ValueError, match="single"):
        list(rows_from_file(archive))
    result = list(rows_from_file(archive, member="reports.csv"))
    assert len(result) == 1 and result[0][1]["report_number"] == "001"

def test_missing_id_or_date_schema_is_hard_error(tmp_path):
    source = tmp_path / "changed.csv"
    source.write_text("location,city\nnot an id,Portland\n")
    with pytest.raises(ValueError, match="Source ID/date columns"):
        stage("csb", source, tmp_path / "out.gz", tmp_path / "manifest.json",
              source_url=URLS["csb"])

def test_official_zip_stream_utf8_fail_closed_and_explicit_publisher_encoding(tmp_path):
    import zipfile
    archive = tmp_path/"phmsa-export.zip"
    with zipfile.ZipFile(archive,"w") as z:
        z.writestr("report.txt", b"report_number\tincident_date\tcompany_name\nA001\t2025-05-03\tJos\xe9 pipeline\n")
        z.writestr("data_dictionary.txt",b"field\tdescription\nreport_number\treport key\n")
    with pytest.raises(UnicodeDecodeError):
        list(rows_from_file(archive,member="report.txt"))
    source=list(rows_from_file(archive,member="report.txt",encoding="cp1252"))
    assert len(source)==1
    assert source[0][1]["company_name"]=="Jos\u00e9 pipeline"
    with pytest.raises(ValueError, match="encoding"):
        list(rows_from_file(archive,member="report.txt",encoding="not-a-publisher-encoding"))

def test_zip_requires_explicit_member_even_when_two_txt_tables(tmp_path):
    import zipfile
    p=tmp_path/"tables.zip"
    with zipfile.ZipFile(p,"w") as z:
        z.writestr("incidents.txt","report_number\tincident_date\nQ1\t2024-01-01\n")
        z.writestr("data_dictionary.txt","field\tdescription\nkey\tdictionary\n")
    with pytest.raises(ValueError,match="single"):
        list(rows_from_file(p))
    assert list(rows_from_file(p,member="incidents.txt"))[0][1]["report_number"]=="Q1"
