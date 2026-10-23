"""Read-only national source indices and local insured workspace stay separate."""
import json
from pathlib import Path
import sqlite3

import pytest
from fastapi.testclient import TestClient

from facilityrisk.app import app
from facilityrisk.db import connect, initialize
from facilityrisk.intelligence import review_location
from facilityrisk.source_sidecars import frs_status, noaa_index_status
from facilityrisk.universal_registry import import_records
from facilityrisk.storm_events import initialize_storm_events


def _frs_index(tmp_path):
    db=tmp_path/"national-source.sqlite"
    with connect(db) as conn:
        initialize(conn)
        result=import_records(conn, "EPA_FRS", [
            {"source_identifier":"110000001234","name":"Mountain Warehouse",
             "country":"US","industry":"493110","latitude":43.65,
             "longitude":-70.25,"state":"ME","company":"Storage Inc"},
            {"source_identifier":"110000001235","name":"Municipal Hospital",
             "country":"US","industry":"622110","state":"ME"},
        ],"https://www.epa.gov/frs",vintage="2026-10-23")
        assert result["valid"]==2
        chosen=conn.execute("SELECT id FROM universal_sites WHERE name='Mountain Warehouse'").fetchone()[0]
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    qa=tmp_path/"national-source-qa.json"
    qa.write_text(json.dumps({
       "source":"EPA FRS public reporting identities",
       "sqlite_quick_check":"ok",
       "source_archive_sha256":"a"*64,
       "normalized_source_sha256":"b"*64,
       "source_vintage":"2026-10-23",
       "database_bytes":db.stat().st_size,
       "unique_source_identifiers":2,
       "site_candidates":2,
    }))
    return db,qa,chosen


def _noaa_index(tmp_path):
    db=tmp_path/"noaa-source.sqlite"
    with connect(db) as conn:
        initialize_storm_events(conn)
        conn.execute("""INSERT INTO noaa_storm_events VALUES
          ('201001','123',2024,'2024-09-22','MAINE','CUMBERLAND','Flood',
          43.650,-70.250,NULL,NULL,'50K',0,0,
          'https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/',
          'Source reference point only, not building exposure')""")
        conn.execute("""INSERT INTO noaa_storm_imports VALUES
          (2024,1,1,'https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/',
           'StormEvents_details-ftp_v1.0_d2024_c20261001.csv.gz',?,?,
           '2026-10-23','2026-10-23')""",("a"*64,"b"*64))
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    manifest=tmp_path/"noaa-manifest.json"
    manifest.write_text(json.dumps({
        "publisher":"NOAA NCEI Storm Events Details",
        "complete_requested_years":True,
        "normalized_sha256":"b"*64,
        "requested_years":[2024],"total_events":1,
        "generated_at":"2026-10-23T13:00:00Z",
        "partitions":[{"year":2024,"event_records":1,
            "point_coordinates_reported":1,"original_archive_sha256":"a"*64}],
    }))
    return db,manifest


def _set_source_env(monkeypatch, db, evidence, source):
    if source=="frs":
        names=("FACILITY_RISK_FRS_INDEX_PATH","FACILITY_RISK_FRS_INDEX_QA")
    else:
        names=("FACILITY_RISK_NOAA_INDEX_PATH","FACILITY_RISK_NOAA_INDEX_MANIFEST")
    monkeypatch.setenv(names[0],str(db))
    monkeypatch.setenv(names[1],str(evidence))


def _authenticated(monkeypatch, tmp_path):
    monkeypatch.setenv("FACILITY_RISK_DB",str(tmp_path/"insured-workspace.sqlite"))
    monkeypatch.setenv("FACILITY_RISK_REQUIRE_AUTH","1")
    monkeypatch.setenv("FACILITY_RISK_AUTH_TOKEN","Z"*40)
    return TestClient(app,headers={"Authorization":"Bearer "+"Z"*40})


def test_missing_indices_return_unassessed_without_phantom_national_coverage(monkeypatch,tmp_path):
    for name in ("FACILITY_RISK_FRS_INDEX_PATH","FACILITY_RISK_FRS_INDEX_QA",
                 "FACILITY_RISK_NOAA_INDEX_PATH","FACILITY_RISK_NOAA_INDEX_MANIFEST"):
        monkeypatch.delenv(name,raising=False)
    with _authenticated(monkeypatch,tmp_path) as client:
        assert client.get("/api/source-indices/status").json()["frs"]["state"]=="not_configured"
        stats=client.get("/api/universal-facilities/stats").json()
        assert stats["national_index"]["state"]=="not_configured"
        assert not any(s["source_key"]=="EPA_FRS" for s in stats["sources"])
        assert client.get("/api/universal-facilities?source=EPA_FRS&q=warehouse").json()["total"]==0
        assert client.get("/api/noaa/storm-events/status").json()["state"]=="not_imported"


def test_frs_source_search_is_readonly_and_keeps_workspace_independent(monkeypatch,tmp_path):
    db,qa,site_id=_frs_index(tmp_path)
    _set_source_env(monkeypatch,db,qa,"frs")
    assert frs_status()["state"]=="ready_partial"
    with _authenticated(monkeypatch,tmp_path) as client:
        assert client.get("/api/source-indices/status").json()["frs"]["source_identities"]==2
        stats=client.get("/api/universal-facilities/stats").json()
        assert stats["site_candidates"]==0
        assert stats["national_index"]["source_identities"]==2
        assert any(row["source_key"]=="EPA_FRS" and row["records"]==2 for row in stats["sources"])
        result=client.get("/api/universal-facilities?source=EPA_FRS&q=Warehouse").json()
        assert result["index"]=="EPA_FRS"
        assert result["total"]==1
        assert result["items"][0]["id"]==site_id
        assert result["items"][0]["coordinate_quality"]=="source_point_unverified"
        detail=client.get("/api/universal-facilities/"+site_id).json()
        assert detail["risk_status"]=="unassessed"
        assert detail["insured_coverage_status"]=="unknown"
        assert detail["source_identities"][0]["source_identifier"]=="110000001234"
        assert client.post("/api/universal-facilities/"+site_id+"/track").status_code==403
        assert client.get("/api/universal-facilities?source=EPA_FRS&q=notarealfacility").json()["total"]==0
        assert client.get("/api/universal-facilities?q=Warehouse").json()["total"]==0
    with sqlite3.connect("file:"+db.resolve().as_posix()+"?mode=ro",uri=True) as original:
        assert original.execute("SELECT COUNT(*) FROM universal_sites").fetchone()[0]==2
        assert original.execute("SELECT COUNT(*) FROM facilities").fetchone()[0]==0


def test_explicit_tracking_copies_one_observed_identity_only(monkeypatch,tmp_path):
    db,qa,site_id=_frs_index(tmp_path)
    _set_source_env(monkeypatch,db,qa,"frs")
    monkeypatch.setenv("FACILITY_RISK_ENABLE_WRITES","1")
    with _authenticated(monkeypatch,tmp_path) as client:
        result=client.post("/api/universal-facilities/"+site_id+"/track")
        assert result.status_code==200,result.text
        assert result.json()["facility_id"]
        records=client.get("/api/universal-facilities?q=Warehouse").json()
        assert records["total"]==1
        assert records["items"][0]["coordinate_quality"]=="source_point_unverified"
        assert client.post("/api/universal-facilities/"+site_id+"/track").json()["already_tracked"] is True
    with sqlite3.connect(str(tmp_path/"insured-workspace.sqlite")) as private:
        assert private.execute("SELECT COUNT(*) FROM universal_source_records").fetchone()[0]==1
        assert private.execute("SELECT COUNT(*) FROM universal_sites").fetchone()[0]==1
    with sqlite3.connect("file:"+db.resolve().as_posix()+"?mode=ro",uri=True) as readonly:
        assert readonly.execute("SELECT COUNT(*) FROM universal_sites").fetchone()[0]==2


def test_frs_tampered_manifest_private_rows_and_same_db_fail_closed(monkeypatch,tmp_path):
    db,qa,_=_frs_index(tmp_path)
    _set_source_env(monkeypatch,db,qa,"frs")
    info=json.loads(qa.read_text())
    info["source_archive_sha256"]="not-a-sha"
    qa.write_text(json.dumps(info))
    assert frs_status()["state"]=="unavailable"
    with _authenticated(monkeypatch,tmp_path) as client:
        assert client.get("/api/universal-facilities?source=EPA_FRS&q=warehouse").status_code==503
        assert client.get("/api/source-indices/status").json()["frs"]["state"]=="unavailable"
    info["source_archive_sha256"]="a"*64
    with sqlite3.connect(str(db)) as conn:
        conn.execute("""INSERT INTO facilities(id,name,origin,last_imported)
              VALUES('private-insured','Private Insured','fixture','2026-10-23')""")
        conn.commit()
    info["database_bytes"]=db.stat().st_size
    qa.write_text(json.dumps(info))
    assert frs_status()["state"]=="unavailable"
    monkeypatch.setenv("FACILITY_RISK_DB",str(db))
    assert frs_status()["state"]=="unavailable"


def test_noaa_external_index_and_review_gate(monkeypatch,tmp_path):
    db,manifest=_noaa_index(tmp_path)
    _set_source_env(monkeypatch,db,manifest,"noaa")
    with _authenticated(monkeypatch,tmp_path) as client:
        index=client.get("/api/source-indices/status").json()
        assert index["noaa"]["state"]=="ready_partial"
        assert client.get("/api/noaa/storm-events/status").json()["records"]==1
        assert client.get("/api/noaa/storm-events?year=2024&state=MAINE").json()["total"]==1
        with connect(tmp_path/"insured-workspace.sqlite") as local:
            initialize(local)
            local.execute("""INSERT INTO facilities(id,name,country,latitude,longitude,origin,last_imported)
                VALUES('research-site','Research Site','US',43.651,-70.251,'fixture','2026-10-23')""")
            local.commit()
        pending=client.get("/api/facilities/research-site/noaa-storm-events?year=2024")
        assert pending.json()["status"]=="unassessed_location"
        with connect(tmp_path/"insured-workspace.sqlite") as local:
            review_location(local,"research-site","site_verified",
                            "https://www.openstreetmap.org/","independent-reviewer",
                            "Reviewed current source point")
        result=client.get("/api/facilities/research-site/noaa-storm-events?year=2024")
        assert result.status_code==200,result.text
        assert result.json()["total_nearby"]==1
        assert result.json()["items"][0]["event_id"]=="201001"
        assert "no facility damage" in result.json()["caveat"]
        with connect(tmp_path/"insured-workspace.sqlite") as local:
            local.execute("UPDATE facilities SET latitude=45 WHERE id='research-site'")
            local.commit()
        assert client.get("/api/facilities/research-site/noaa-storm-events").json()["status"]=="unassessed_location"


def test_noaa_corrupt_manifest_refuses_silent_fallback(monkeypatch,tmp_path):
    db,manifest=_noaa_index(tmp_path)
    _set_source_env(monkeypatch,db,manifest,"noaa")
    info=json.loads(manifest.read_text())
    info["total_events"]=12
    manifest.write_text(json.dumps(info))
    assert noaa_index_status()["state"]=="unavailable"
    with _authenticated(monkeypatch,tmp_path) as client:
        assert client.get("/api/noaa/storm-events").status_code==503
        assert client.get("/api/noaa/storm-events/status").json()["state"]=="unavailable"
