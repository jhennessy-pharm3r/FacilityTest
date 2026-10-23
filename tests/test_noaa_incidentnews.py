"""Official NOAA OR&R selected spill-response events remain source scoped."""
import csv
from datetime import date
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from facilityrisk.app import app
from facilityrisk.db import connect,initialize
from facilityrisk.incident_news import import_incidentnews, search, nearby_reviewed_site
from facilityrisk.intelligence import review_location
from facilityrisk.source_sidecars import incidentnews_index_status
from scripts.build_noaa_incidentnews import (URL,COLUMNS,stage,summary,validate)


FIELDS=["id","open_date","name","location","lat","lon","threat","tags","commodity",
        "is_measure_skim","is_measure_shore","is_measure_bio","is_measure_disperse",
        "is_measure_burn","max_ptl_release_gallons","posts","description"]


def fixture_csv(duplicate=False,wrong_schema=False,actual_headers=False):
    handle=io.StringIO()
    fields=FIELDS[:-1] if wrong_schema else FIELDS
    if actual_headers:
        fields=[v.removeprefix("is_") for v in fields]
    writer=csv.DictWriter(handle,fieldnames=fields,extrasaction="ignore")
    writer.writeheader()
    examples=[
        {"id":101,"open_date":"2025-02-12","name":"Channel Oil Spill",
         "location":"Portland, Maine","lat":"43.65","lon":"-70.25",
         "threat":"Oil","tags":"Pipeline|Collision","commodity":"Diesel",
         "is_measure_skim":"1","is_measure_shore":"0","is_measure_bio":"",
         "is_measure_disperse":"0","is_measure_burn":"0",
         "max_ptl_release_gallons":"2000","posts":"1","description":"Response assistance"},
        {"id":101 if duplicate else 102,"open_date":"2023-01-02",
         "name":"Industrial Chemical Response","location":"Coastal Maine",
         "lat":"","lon":"","threat":"Chemical","tags":"Railcar",
         "commodity":"Unknown","is_measure_skim":"0","is_measure_shore":"1",
         "is_measure_bio":"0","is_measure_disperse":"0","is_measure_burn":"0",
         "max_ptl_release_gallons":"","posts":"0",
         "description":"Selected assistance case"},
        {"id":103,"open_date":"","name":"Old Unknown", "location":"Offshore",
         "lat":"43.60","lon":"","threat":"Other","tags":"",
         "commodity":"","is_measure_skim":"","is_measure_shore":"",
         "is_measure_bio":"","is_measure_disperse":"","is_measure_burn":"",
         "max_ptl_release_gallons":"","posts":"","description":"Site not known"}
    ]
    for row in examples:
        if actual_headers:
            row={k.removeprefix("is_"):v for k,v in row.items()}
        writer.writerow(row)
    return handle.getvalue().encode()


class Response:
    def __init__(self,content):
        self.content=content
        self.url=URL
    def raise_for_status(self):
        return None
    def iter_content(self,chunk_size=512*1024):
        yield self.content
    def __enter__(self):return self
    def __exit__(self,*args):return False


class Session:
    def __init__(self,content):
        self.content=content
    def get(self,url,**kwargs):
        assert url==URL
        return Response(self.content)


def source(tmp_path,**kwargs):
    raw=tmp_path/"incidents.csv"
    normalized=tmp_path/"normalized.csv.gz"
    manifest=tmp_path/"manifest.json"
    published=tmp_path/"public.json"
    details=stage(raw,normalized,manifest,published,
                  session=Session(fixture_csv(**kwargs)),minimum_rows=3,
                  run_url="https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/12")
    return raw,normalized,manifest,published,details


def test_official_source_staged_and_publisher_limited(tmp_path):
    raw,normalized,manifest,published,data=source(tmp_path)
    assert data["records"]==3
    assert data["coordinate_records"]==1
    assert data["missing_notification_dates"]==1
    assert data["threat_counts"]=={"Chemical":1,"Oil":1,"Other":1}
    assert data["earliest_notification_date"]=="2023-01-02"
    assert validate(normalized,data)
    import gzip
    with gzip.open(normalized,"rt",encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    assert tuple(rows[0])==COLUMNS
    assert rows[0]["potential_release_gallons_max"]=="2000.0"
    assert rows[1]["latitude"]==""
    assert rows[2]["longitude"]==""
    assert "not a property boundary" in rows[0]["coordinate_semantics"]
    p=json.loads(published.read_text())
    assert p["source"]=="NOAA IncidentNews Selected Spills"
    assert p["records"]==3
    assert p["state"]=="staged_source_artifact"
    assert "not all reported spills" in p["scope"]
    assert "Actual" not in p.get("scope","")
    assert p==summary(data,p["artifact_run_url"])


def test_rejects_corrupt_id_changed_schema_and_checksum(tmp_path):
    with pytest.raises(ValueError,match="duplicate"):
        source(tmp_path/"dup",duplicate=True)
    with pytest.raises(ValueError,match="columns changed"):
        source(tmp_path/"fields",wrong_schema=True)
    raw,normalized,manifest,_,data=source(tmp_path/"valid")
    normalized.write_bytes(normalized.read_bytes()+b"tampered")
    with pytest.raises(ValueError,match="checksum"):
        validate(normalized,data)


def test_verified_noaa_incidentnews_sqlite_and_approved_site_proximity(tmp_path):
    _,normalized,manifest,_,data=source(tmp_path)
    with connect(tmp_path/"spill-source.sqlite") as src:
        initialize(src)
        outcome=import_incidentnews(src,normalized,manifest)
        assert outcome["state"]=="ready_partial"
        assert outcome["records"]==3
        assert search(src,threat="Oil")["total"]==1
        assert search(src,q="Chemical")["total"]==1
        assert search(src,from_date="2025-01-01")["total"]==1
        assert search(src,threat="Unspecified")["total"]==0
        assert search(src,q="still_not_a_spill")["total"]==0
        assert search(src,q="O_l")["total"]==0
        with pytest.raises(ValueError,match="Unknown"):
            search(src,threat="Unknown Type")
        with connect(tmp_path/"private-insured.sqlite") as workspace:
            initialize(workspace)
            workspace.execute("""INSERT INTO facilities
              (id,name,country,latitude,longitude,origin,last_imported)
              VALUES('siteA','Unverified Warehouse','US',43.651,-70.251,
              'fixture','2026-10-23')""")
            workspace.commit()
            pending=nearby_reviewed_site(workspace,src,"siteA")
            assert pending["status"]=="unassessed_location"
            assert pending["total_nearby"] is None
            review_location(workspace,"siteA","site_verified",
                            "https://www.openstreetmap.org/","independent-reviewer",
                            "Confirmed current coordinates")
            nearby=nearby_reviewed_site(workspace,src,"siteA",radius_km=5)
            assert nearby["status"]=="proximity_candidates_only"
            assert nearby["total_nearby"]==1
            assert nearby["items"][0]["incident_id"]=="101"
            assert "not verified site damage" in nearby["caveat"]
            workspace.execute("UPDATE facilities SET longitude=-71 WHERE id='siteA'")
            workspace.commit()
            assert nearby_reviewed_site(workspace,src,"siteA")["status"]=="unassessed_location"


def test_explicit_incident_source_sidecar_auth_and_no_private_rows(monkeypatch,tmp_path):
    _,normalized,manifest,_,data=source(tmp_path)
    database=tmp_path/"public-incidents.sqlite"
    with connect(database) as c:
        initialize(c)
        import_incidentnews(c,normalized,manifest)
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    monkeypatch.setenv("FACILITY_RISK_DB",str(tmp_path/"independent-insured.sqlite"))
    monkeypatch.setenv("FACILITY_RISK_INCIDENTNEWS_INDEX_PATH",str(database))
    monkeypatch.setenv("FACILITY_RISK_INCIDENTNEWS_INDEX_MANIFEST",str(manifest))
    monkeypatch.setenv("FACILITY_RISK_REQUIRE_AUTH","1")
    monkeypatch.setenv("FACILITY_RISK_AUTH_TOKEN","K"*40)
    assert incidentnews_index_status()["state"]=="ready_partial"
    with TestClient(app) as unauthenticated:
        assert unauthenticated.get("/api/noaa/incidentnews").status_code==401
    with TestClient(app,headers={"Authorization":"Bearer "+"K"*40}) as c:
        status=c.get("/api/source-indices/status").json()
        assert status["incidentnews"]["records"]==3
        found=c.get("/api/noaa/incidentnews?threat=Oil")
        assert found.status_code==200
        assert found.json()["total"]==1
        assert "not verified property loss" not in str(found.json()["items"][0]["threat"])
        assert c.get("/api/noaa/incidentnews/status").json()["state"]=="ready_partial"
        assert c.get("/api/facilities/no-such-site/noaa-incidentnews").status_code==422
    payload=json.loads(manifest.read_text())
    payload["records"]=99
    manifest.write_text(json.dumps(payload))
    assert incidentnews_index_status()["state"]=="unavailable"
    with TestClient(app,headers={"Authorization":"Bearer "+"K"*40}) as c:
        assert c.get("/api/noaa/incidentnews").status_code==503


def test_public_ledger_keeps_only_aggregate_for_selected_response_cases(tmp_path):
    from scripts.publish_source_status import published_external_ingestions
    directory=tmp_path/"public"
    directory.mkdir()
    data={"schema_version":"1.0","source":"NOAA IncidentNews Selected Spills",
          "state":"staged_source_artifact","records":314,
          "checked_at":"2026-10-23T13:00:00+00:00",
          "scope":"Selected NOAA scientific response cases",
          "details":"Not all spills","documentation":"https://incidentnews.noaa.gov/raw/index",
          "private_notes":"DO NOT PUBLISH","insured_claims":[{"secret":"danger"}]}
    (directory/"noaa-incidentnews.json").write_text(json.dumps(data))
    rows=published_external_ingestions(directory)
    assert len(rows)==1 and rows[0]["records"]==314
    assert "insured_claims" not in rows[0]
    assert "private_notes" not in rows[0]



def test_live_2026_publisher_measure_column_variant(tmp_path):
    # Verified actual NOAA export headers: measure_*; documentation says
    # is_measure_*. Preserve all five reported flags without guessing.
    _,normalized,manifest,_,data=source(tmp_path,actual_headers=True)
    assert data["records"]==3
    import gzip
    with gzip.open(normalized,"rt",encoding="utf-8") as stream:
        rows=list(csv.DictReader(stream))
    assert rows[0]["measure_skim"]=="1"
    assert rows[0]["measure_shore"]=="0"
    assert rows[1]["measure_shore"]=="1"
    assert validate(normalized,data)
