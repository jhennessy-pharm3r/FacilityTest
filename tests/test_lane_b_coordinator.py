"""Coordinator EPA read-only integration into actual authenticated FacilityRisk app.

All test rows are fixtures, NEVER represented as production EPA source coverage.
Official publisher/full-source dataflow is verified separately by Lane B Actions.
"""
import json
from pathlib import Path
from zipfile import ZipFile
from fastapi.testclient import TestClient

from facilityrisk.app import app
from scripts.lane_b_epa.ingest import ingest
from scripts.lane_b_epa.rmp_public import import_public

TOKEN="LaneB-private-coordinator-regression-token-123456789"

def _source_test_bundles(tmp_path):
    echo_raw=tmp_path/"echo.csv"
    echo_raw.write_text("REGISTRY_ID,FAC_NAME,FAC_LAT,FAC_LONG\nFRS100,Medical Clinic,45,-64\n,No key,45,-64\n")
    echo=tmp_path/"echo";ingest("echo",echo_raw,echo)
    raw_rcra=tmp_path/"rcra.zip"
    with ZipFile(raw_rcra,"w") as f:
        f.writestr("RCRA_FACILITIES.csv",
            "ID_NUMBER,ACTIVITY_LOCATION,FACILITY_NAME,LATITUDE83,LONGITUDE83\n" +
            "MEX0001,ME,Warehouse,45,-64\n" +
            "MEX0001,MA,Factory,40,-71\n")
        f.writestr("RCRA_ENFORCEMENTS.csv",
            "ID_NUMBER,ACTIVITY_LOCATION,ENFORCEMENT_IDENTIFIER,ENFORCEMENT_ACTION_DATE\n" +
            "MEX0001,ME,ENV100,10/20/2024\n")
    rcra=tmp_path/"rcra";ingest("rcra",raw_rcra,rcra)
    tri_csv=tmp_path/"tri.csv"
    tri_csv.write_text("1. YEAR,2. TRIFD,3. FRS ID,37. CHEMICAL,50. UNIT OF MEASURE\n"+
                       "2024,TRI100,FRS100,Listed Chemical,Grams\n")
    tri_root=tmp_path/"tri"
    ingest("tri",tri_csv,tri_root/"tri_2024",year=2024)
    def mocked_publisher(params):
        if "returnCountOnly" in params:return {"count":1}
        if "returnIdsOnly" in params:return {"objectIds":[1]}
        return {"features":[{"attributes":{
            "OBJECTID":1,"REGISTRY_ID":"FRS100","PGM_SYS_ID":"RMP100",
            "STATE_CODE":"ME","LATITUDE83":45.1,"LONGITUDE83":-64.1}}]}
    rmp=tmp_path/"rmp";import_public(rmp,fetch=mocked_publisher)
    return echo,rcra,tri_root,rmp

def _setup(monkeypatch,tmp_path):
    echo,rcra,tri,rmp=_source_test_bundles(tmp_path)
    monkeypatch.setenv("FACILITY_RISK_DB",str(tmp_path/"workspace.sqlite"))
    monkeypatch.setenv("FACILITY_RISK_AUTH_TOKEN",TOKEN)
    monkeypatch.setenv("FACILITY_RISK_REQUIRE_AUTH","1")
    monkeypatch.setenv("FACILITY_RISK_LANE_B_ROUTES_ENABLED","1")
    monkeypatch.setenv("FACILITY_RISK_LANE_B_ECHO_DIRECTORY",str(echo))
    monkeypatch.setenv("FACILITY_RISK_LANE_B_RCRA_DIRECTORY",str(rcra))
    monkeypatch.setenv("FACILITY_RISK_LANE_B_TRI_ROOT",str(tri))
    monkeypatch.setenv("FACILITY_RISK_LANE_B_TRI_YEARS","2024")
    monkeypatch.setenv("FACILITY_RISK_LANE_B_RMP_DIRECTORY",str(rmp))
    return {"Authorization":"Bearer "+TOKEN}

def test_real_app_new_epa_source_routes_guarded_and_status_aggregated(monkeypatch,tmp_path):
    headers=_setup(monkeypatch,tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/epa/lane-b/status").status_code==401
        status=client.get("/api/source-indices/status",headers=headers)
        assert status.status_code==200
        sources=status.json()["lane_b_epa"]["sources"]
        assert {k:v["state"] for k,v in sources.items()}=={
            "echo":"mounted_source_only","rcra":"mounted_source_only",
            "tri":"mounted_source_only","rmp_public":"mounted_source_only"}
        assert sources["echo"]["indexed_source_rows"]==1
        assert sources["echo"]["rejected_source_rows"]==1
        assert sources["rcra"]["indexed_source_rows"]==3
        assert sources["tri"]["indexed_source_rows"]==1
        assert sources["rmp_public"]["indexed_source_rows"]==1
        assert all(x["production_deployed_records"] is None for x in sources.values())
        assert status.json()["lane_b_epa"]["production_deployment"]=="UNASSESSED_BY_ADAPTER"
        for source,params in [
            ("echo",{"native_id":"FRS100"}),
            ("rcra",{"native_id":"MEX0001","activity_location":"ME"}),
            ("tri",{"native_id":"TRI100","year":2024}),
            ("rmp_public",{"native_id":"RMP100"})]:
            r=client.get(f"/api/epa/lane-b/{source}/identity",params=params,headers=headers)
            assert r.status_code==200,(source,r.text)
            obj=r.json()
            assert obj["observations_available"]>=1
            assert obj["site_and_insured_loss_status"]=="UNASSESSED"
        assert client.get("/api/epa/lane-b/rcra/identity",
                          params={"native_id":"MEX0001"},headers=headers).status_code==422
        assert client.get("/api/epa/lane-b/rcra/identity",
                          params={"native_id":"MEX0001","activity_location":"NZ"},
                          headers=headers).json()["observations_available"]==0
        assert client.get("/api/epa/lane-b/tri/identity",
                          params={"native_id":"TRI100","year":2023},headers=headers).status_code==422
        assert client.get("/api/epa/lane-b/echo/identity",
                          params={"native_id":"FRS100","include_raw":"true"},
                          headers=headers).status_code==403

def test_missing_or_corrupted_mount_fails_closed_without_zero_risk(monkeypatch,tmp_path):
    headers=_setup(monkeypatch,tmp_path)
    with TestClient(app) as client:
        monkeypatch.setenv("FACILITY_RISK_LANE_B_ECHO_DIRECTORY",str(tmp_path/"missing"))
        r=client.get("/api/epa/lane-b/status",headers=headers)
        assert r.status_code==200
        assert r.json()["sources"]["echo"]["state"]=="unavailable"
        assert client.get("/api/epa/lane-b/echo/identity",
            params={"native_id":"FRS100"},headers=headers).status_code==503
        monkeypatch.setenv("FACILITY_RISK_LANE_B_ROUTES_ENABLED","0")
        assert client.get("/api/epa/lane-b/status",headers=headers).status_code==503
        assert client.get("/api/epa/lane-b/tri/identity",
            params={"native_id":"TRI100","year":2024},headers=headers).status_code==503
