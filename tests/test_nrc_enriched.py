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

def test_missing_native_relationship_blocks_normalization(tmp_path):
    file = tmp_path / "CY25.xlsx"
    create_workbook(file, mismatch=True)
    with pytest.raises(ValueError, match="missing cross-sheet SEQNOS"):
        stage_nrc(file, tmp_path / "out.csv.gz", tmp_path / "manifest.json",
                  year=2025, minimum_rows=2)
