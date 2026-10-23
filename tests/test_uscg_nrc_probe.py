"""Official NRC FOIA workbook readiness is not evidence of incident linkage."""
import io
from pathlib import Path
import zipfile
import pytest
from openpyxl import Workbook

from scripts.probe_uscg_nrc import download,official_url,probe


def workbook(with_headers=True):
    wb=Workbook()
    report=wb.active
    report.title="INCIDENTS"
    report.append(["SEQNOS","REPORTED_DATE","STATE","COUNTY"] if with_headers else
                  ["one","two","three","four"])
    report.append([101,"2025-06-01","ME","Cumberland"])
    material=wb.create_sheet("MATERIAL")
    material.append(["SEQNOS","MATERIAL_TYPE","QUANTITY"])
    material.append([101,"Diesel","5"])
    stream=io.BytesIO()
    wb.save(stream)
    return stream.getvalue()


class Reply:
    def __init__(self,payload,url):
        self.data=payload
        self.url=url
    def raise_for_status(self):pass
    def iter_content(self,chunk_size=1024*1024):yield self.data
    def __enter__(self):return self
    def __exit__(self,*args):return False


class Session:
    def __init__(self,payload):self.payload=payload
    def get(self,url,**kw):return Reply(self.payload,url)


def test_public_uscg_annual_workbook_schema_and_provenance(tmp_path):
    year=2025
    assert official_url(year)=="https://nrc.uscg.mil/FOIAFiles/CY25.xlsx"
    target=tmp_path/"CY25.xlsx"
    download(Session(workbook()),official_url(year),target)
    result=probe(target,year)
    assert result["year"]==2025
    assert result["state"]=="schema_probe_only_not_imported"
    assert result["recognizable_headers"]==2
    assert "SEQNOS" in result["worksheets"][0]["header_names"]
    assert "incident counts" in result["data_caveat"].lower()
    assert len(result["sha256"])==64
    assert result["archive_bytes"]>100


def test_bad_source_and_missing_schema_fail_closed(tmp_path):
    with pytest.raises(ValueError,match="known range"):
        official_url(1989)
    with pytest.raises(ValueError,match="official NRC"):
        download(Session(workbook()),"https://other.example/CY25.xlsx",
                 tmp_path/"unsafe.xlsx")
    invalid=tmp_path/"bad.xlsx"
    invalid.write_bytes(workbook(with_headers=False))
    # Second table has valid names but lacks a recognizable complete
    # incident-level primary worksheet. Scanner still reports no
    # facility/incident linkage from mere sheet names.
    result=probe(invalid,2025)
    assert result["state"]=="schema_probe_only_not_imported"
    assert result["worksheets"][0]["header_recognized"] is False
    corrupt=tmp_path/"not-excel.xlsx"
    corrupt.write_bytes(b"not a spreadsheet")
    with pytest.raises(zipfile.BadZipFile):
        probe(corrupt,2025)
