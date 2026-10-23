"""PHMSA WMS case-only release: positive packaging plus tamper/role guards."""
from __future__ import annotations
import csv
import sqlite3
import pytest

from scripts.build_phmsa_enforcement import REQUIRED,build,index_cases
from scripts.lane_c_enforcement_install import package,verify,install,query,rollback

def example_source(tmp_path):
    repo=tmp_path/"repo"
    repo.mkdir()
    raw=tmp_path/"source.txt"
    cases=[]
    for seq,opid,report in ((1,"123","202601"),(2,"123","202601"),(3,"456","")):
        cases.append({
            "CPF_Number":f"42026{seq}CAO",
            "WMS_Activity_Seq":str(100+seq),
            "Operator_ID":opid,
            "Operator_Name":"Test Operator",
            "Pipeline_Type":"Hazardous Liquid" if opid=="123" else "Gas",
            "Case_Type":"CAO","Case_Status":"Open",
            "Opened_Date":f"01/{seq+1:02d}/2026",
            "Report_Type":"Incident" if report else "",
            "Report_Number":report,
            "Data_as_of":"10/02/2026"
        })
    with raw.open("w",encoding="cp1252",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=REQUIRED,dialect="excel-tab")
        writer.writeheader()
        writer.writerows(cases)
    normalized=tmp_path/"rows.csv.gz"
    manifest=tmp_path/"manifest.json"
    audit=build(raw,normalized,manifest,minimum_rows=3)
    assert audit["accepted_case_rows"]==3
    database=tmp_path/"cases.sqlite"
    index_cases(normalized,manifest,database)
    return repo,raw,normalized,manifest,database

def test_private_package_installed_separately_and_read_only_query(tmp_path):
    repo,raw,normalized,manifest,db=example_source(tmp_path)
    bundle=tmp_path/"private-wms-bundle"
    packaged=package(raw,normalized,manifest,db,bundle,repo_root=repo)
    assert packaged["packaged_case_rows"]==3
    assert packaged["app_deployed"]==0
    assert verify(bundle)["case_rows_with_report_references"]==2
    root=tmp_path/"private-case-service"
    root.mkdir(mode=0o700)
    state=install(bundle,root,"enforcement-test",repo_root=repo)
    assert state["verified_case_rows"]==3
    assert state["live_app_deployed"]==0
    all_rows=query(root,page_size=2,repo_root=repo)
    assert all_rows["total"]==3
    assert len(all_rows["items"])==2
    assert all_rows["source"]=="phmsa_wms_enforcement_NOT_INCIDENT_CENSUS"
    assert "source_row_json" not in all_rows["items"][0]
    assert query(root,operator_id="123",repo_root=repo)["total"]==2
    assert query(root,case_number="420263CAO",repo_root=repo)["total"]==1
    index=root/"releases/enforcement-test/indexes/phmsa-wms-enforcement.sqlite"
    with sqlite3.connect("file:"+str(index)+"?mode=ro",uri=True) as conn:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM enforcement_cases")
    again=install(bundle,root,"enforcement-test",repo_root=repo)
    assert again["state"]=="ALREADY_INSTALLED_CHECKSUM_VERIFIED"
    install(bundle,root,"enforcement-replacement",repo_root=repo)
    assert query(root,page_size=2,repo_root=repo)["release_id"]=="enforcement-replacement"
    assert rollback(root,"enforcement-test",repo_root=repo)["active_release_id"]=="enforcement-test"
    assert query(root,page_size=2,repo_root=repo)["release_id"]=="enforcement-test"

def test_private_phmsa_bundle_rejects_tampering_before_activation(tmp_path):
    repo,raw,normalized,manifest,db=example_source(tmp_path)
    bundle=tmp_path/"private-wms-bundle"
    package(raw,normalized,manifest,db,bundle,repo_root=repo)
    file=bundle/"normalized/phmsa-wms-enforcement.csv.gz"
    file.write_bytes(file.read_bytes()+b"corrupt")
    with pytest.raises(ValueError,match="SHA mismatch"):
        verify(bundle)
    root=tmp_path/"secure-root"
    root.mkdir(mode=0o700)
    with pytest.raises(ValueError,match="SHA mismatch"):
        install(bundle,root,repo_root=repo)
    assert not (root/"active-release.json").exists()
