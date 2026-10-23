"""NRC native SEQNOS multi-sheet reconciliation and source DMS precision."""
import csv
import gzip
from openpyxl import Workbook
import pytest
from scripts.build_nrc_enriched import dms, stage_nrc, validate

def create_workbook(path, *, mismatch=False):
    workbook = Workbook()
    workbook.remove(workbook.active)
    tables = {
      "CALLS": [
        ["SEQNOS", "RESPONSIBLE_COMPANY"],
        ["00001", "Reported Manufacturer"],
        ["00002", "Reported Operator"]],
      "INCIDENT_COMMONS": [
        ["SEQNOS", "INCIDENT_DATE_TIME", "INCIDENT_LOCATION", "LOCATION_NEAREST_CITY", "LOCATION_STATE",
         "LAT_DEG","LAT_MIN","LAT_SEC","LAT_QUAD","LONG_DEG","LONG_MIN","LONG_SEC","LONG_QUAD"],
        ["00001", "2025-04-01 12:00:00", "Near a coastal terminal", "Houston", "TX",29,45,0,"N",95,20,0,"W"],
        ["00002", "2025-04-02 09:10:00", "Offshore location", "N/A", "TX",None,None,None,None,None,None,None,None]],
      "INCIDENT_DETAILS": [
        ["SEQNOS","NUMBER_FATALITIES","NUMBER_INJURED","NUMBER_EVACUATED","DAMAGE_AMOUNT","FIRE_INVOLVED"],
        ["00001",0,2,15,25000,"Y"],
        ["99999" if mismatch else "00002",0,0,0,None,"N"]]
    }
    for name, rows in tables.items():
        ws = workbook.create_sheet(name)
        for row in rows:
            ws.append(row)
    workbook.save(path)

def test_nrc_dms_rejects_bad_publisher_coordinates():
    assert dms(29, 45, 0, "N", latitude=True) == "29.75"
    assert dms(95, 20, 0, "W", latitude=False) == str(round(-95-20/60, 7))
    assert dms(95, 60, 0, "W", latitude=False) == ""
    assert dms(101, 0, 0, "N", latitude=True) == ""
    assert dms(95, 0, 0, "", latitude=False) == ""

def test_real_joins_use_native_identifiers_and_no_facility_merges(tmp_path):
    file = tmp_path / "CY25.xlsx"
    create_workbook(file)
    export = tmp_path / "nrc.csv.gz"
    manifest = tmp_path / "manifest.json"
    result = stage_nrc(file, export, manifest, year=2025, minimum_rows=2)
    assert result["accepted_rows"] == 2
    assert result["coordinate_records"] == 1
    assert result["missing_coordinates"] == 1
    assert result["missing_cross_table_links"] == 0
    assert result["physical_facility_matches"] == 0
    assert validate(export, result)
    with gzip.open(export, "rt") as handle:
        rows = list(csv.DictReader(handle))
    assert [r["source_id"] for r in rows] == ["00001", "00002"]
    assert rows[0]["reported_injuries"] == "2.0"
    assert rows[0]["latitude"] == "29.75"
    assert rows[1]["coordinate_semantics"] == "missing_or_invalid_publisher_DMS"
    assert all(r["report_status"] == "NRC_initial_notification_unverified" for r in rows)
    export.write_bytes(export.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="SHA"):
        validate(export, result)

def test_missing_child_report_keeps_master_but_forbids_unknown_severity(tmp_path):
    file = tmp_path / "CY25.xlsx"
    create_workbook(file, mismatch=True)
    exported = tmp_path / "out.csv.gz"
    result = stage_nrc(file, exported, tmp_path / "manifest.json",
                       year=2025, minimum_rows=2)
    assert result["accepted_rows"] == 2
    assert result["missing_details_child_enrichment"] == 1
    assert result["orphan_details_native_ids"] == 1
    assert result["missing_cross_table_links"] == 1
    with gzip.open(exported, "rt") as source:
        rows = {row["source_id"]:row for row in csv.DictReader(source)}
    assert rows["00002"]["reported_fatalities"] == ""
    assert rows["00002"]["reported_injuries"] == ""
    assert rows["00002"]["details_link_quality"] == "missing_or_ambiguous_child"
    assert rows["00001"]["details_link_quality"] == "matched_unique"
    assert rows["00001"]["reported_injuries"] == "2.0"
    assert validate(exported, result)

def test_duplicate_child_severity_dropped_without_discarding_master(tmp_path):
    from openpyxl import load_workbook
    file = tmp_path / "CY25.xlsx"
    create_workbook(file)
    book = load_workbook(file)
    book["INCIDENT_DETAILS"].append(["00001", 4, 9, 100, 999999, "Y"])
    book.save(file)
    out = tmp_path / "output.csv.gz"
    result = stage_nrc(file, out, tmp_path / "manifest.json",
                       year=2025, minimum_rows=2)
    assert result["accepted_rows"] == 2
    assert result["observed_sheet_rows"]["INCIDENT_DETAILS"]["duplicate_native_key_rows"] == 1
    assert result["missing_details_child_enrichment"] == 1
    with gzip.open(out,"rt") as stream:
        rows={row["source_id"]:row for row in csv.DictReader(stream)}
    assert rows["00001"]["reported_injuries"] == ""
    assert rows["00001"]["reported_damage_usd"] == ""
    assert rows["00001"]["details_link_quality"] == "missing_or_ambiguous_child"
    assert rows["00002"]["reported_injuries"] == "0.0"

def test_duplicate_master_source_id_still_fails_closed(tmp_path):
    from openpyxl import load_workbook
    file=tmp_path/"CY25.xlsx"
    create_workbook(file)
    book=load_workbook(file)
    book["INCIDENT_COMMONS"].append(list(next(book["INCIDENT_COMMONS"].iter_rows(min_row=2,max_row=2,values_only=True))))
    book.save(file)
    with pytest.raises(ValueError,match="master report identity invalid"):
        stage_nrc(file,tmp_path/"out.gz",tmp_path/"manifest.json",year=2025,minimum_rows=2)
