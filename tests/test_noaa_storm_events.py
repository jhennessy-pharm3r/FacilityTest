"""NOAA regional event ingestion is complete-source and property-attribution safe."""
from __future__ import annotations

import csv
import gzip
import io
import json

import pytest

from facilityrisk.db import connect, initialize
from facilityrisk.intelligence import review_location
from facilityrisk.storm_events import (
    import_noaa_storm_events, nearby_reviewed_facility, search, status,
)
from scripts.build_noaa_storm_events import (
    COLUMNS, INDEX, choose_files, public_summary, stage, validate_normalized,
)


class Reply:
    def __init__(self, data: bytes, url: str):
        self.payload, self.url = data, url
        self.text = data.decode("utf-8", errors="replace")
    def raise_for_status(self):
        return None
    def iter_content(self, chunk_size=1024 * 1024):
        yield self.payload
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False


class FakeNOAA:
    def __init__(self, raw: bytes, year: int = 2024, edition: str = "20261001"):
        self.filename = f"StormEvents_details-ftp_v1.0_d{year}_c{edition}.csv.gz"
        self.raw = raw
    def get(self, url, **_):
        if url == INDEX:
            return Reply(f'<a href="{self.filename}">{self.filename}</a>'.encode(), INDEX)
        if url == INDEX + self.filename:
            return Reply(self.raw, url)
        raise AssertionError("Unexpected NOAA URL " + url)


def _source_csv(year=2024):
    fields = [
        "EVENT_ID", "EPISODE_ID", "YEAR", "BEGIN_YEARMONTH", "BEGIN_DAY",
        "STATE", "EVENT_TYPE", "CZ_NAME", "BEGIN_LAT", "BEGIN_LON",
        "END_LAT", "END_LON", "DAMAGE_PROPERTY", "INJURIES_DIRECT", "DEATHS_DIRECT",
    ]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields)
    w.writeheader()
    base = dict(EPISODE_ID="567", YEAR=year, BEGIN_YEARMONTH=f"{year}09",
                BEGIN_DAY="22", STATE="MAINE", EVENT_TYPE="Flood",
                CZ_NAME="CUMBERLAND", DAMAGE_PROPERTY="50K",
                INJURIES_DIRECT="0", DEATHS_DIRECT="0",
                END_LAT="", END_LON="")
    w.writerow(dict(base, EVENT_ID=201001, BEGIN_LAT="43.650", BEGIN_LON="-70.250"))
    w.writerow(dict(base, EVENT_ID=201002, BEGIN_LAT="", BEGIN_LON=""))
    return gzip.compress(buf.getvalue().encode("utf-8"))


def _stage(tmp_path):
    out = tmp_path / "noaa.csv.gz"
    mpath = tmp_path / "manifest.json"
    summary = tmp_path / "status.json"
    result = stage([2024], out, mpath, tmp_path / "raw", summary,
                   FakeNOAA(_source_csv()), minimum_rows=2,
                   run_url="https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/55")
    return out, mpath, summary, result


def test_noaa_chooses_latest_publisher_edition_without_guessing():
    listing = ("StormEvents_details-ftp_v1.0_d2024_c20260819.csv.gz\n"
               "StormEvents_details-ftp_v1.0_d2024_c20261001.csv.gz\n"
               "StormEvents_details-ftp_v1.0_d2025_c20261001.csv.gz\n")
    assert choose_files(listing, [2024])[2024].endswith("c20261001.csv.gz")
    with pytest.raises(ValueError, match="omitted"):
        choose_files(listing, [2026])
    with pytest.raises(ValueError, match="distinct"):
        choose_files(listing, [2024, 2024])


def test_noaa_downloaded_complete_cohort_and_manifest(tmp_path):
    out, mpath, summary_path, m = _stage(tmp_path)
    assert m["complete_requested_years"] is True
    assert m["total_events"] == 2
    assert m["partitions"][0]["point_coordinates_reported"] == 1
    assert len(m["normalized_sha256"]) == 64
    assert validate_normalized(out, m)
    with gzip.open(out, "rt") as f:
        rows = list(csv.DictReader(f))
    assert tuple(rows[0]) == COLUMNS
    assert rows[0]["begin_date"] == "2024-09-22"
    assert rows[1]["begin_latitude"] == ""
    assert rows[0]["coordinate_semantics"].endswith("property loss")
    summary = json.loads(summary_path.read_text())
    assert summary["records"] == 2
    assert summary["state"] == "staged_source_artifact"
    assert summary["point_coordinates_reported"] == 1
    assert summary == public_summary(m, summary["artifact_run_url"])


def test_noaa_private_import_search_and_gated_proximity(tmp_path):
    out, manifest_path, _, _ = _stage(tmp_path)
    with connect(tmp_path / "site.sqlite") as conn:
        initialize(conn)
        result = import_noaa_storm_events(conn, out, manifest_path)
        assert result["rows_imported_for_requested_years"] == 2
        assert status(conn)["records"] == 2
        assert search(conn, year=2024, state="MAINE")["total"] == 2
        assert search(conn, year=2023)["total"] == 0
        conn.execute("""
            INSERT INTO facilities(id,name,country,latitude,longitude,origin,last_imported)
            VALUES('plant-x','Plant X','US',43.651,-70.251,'test','2026-10-23')
        """)
        conn.commit()
        gated = nearby_reviewed_facility(conn, "plant-x", radius_km=10)
        assert gated["status"] == "unassessed_location"
        assert gated["total_nearby"] is None
        review_location(conn, "plant-x", "site_verified",
                        "https://www.openstreetmap.org/", "qa-reviewer", "Reviewed point")
        around = nearby_reviewed_facility(conn, "plant-x", radius_km=10, year=2024)
        assert around["status"] == "proximity_candidates_only"
        assert around["total_nearby"] == 1
        assert around["items"][0]["event_id"] == "201001"
        assert "no facility damage" in around["caveat"]
        # An edited facility coordinate cannot reuse the prior approval.
        conn.execute("UPDATE facilities SET latitude=45 WHERE id='plant-x'")
        conn.commit()
        stale = nearby_reviewed_facility(conn, "plant-x")
        assert stale["status"] == "unassessed_location"


def test_noaa_import_rejects_bad_checksum_without_deleting_existing_year(tmp_path):
    out, manifest_path, _, _ = _stage(tmp_path)
    with connect(tmp_path / "site.sqlite") as conn:
        initialize(conn)
        import_noaa_storm_events(conn, out, manifest_path)
        out.write_bytes(out.read_bytes() + b"tampered")
        with pytest.raises(ValueError, match="checksum"):
            import_noaa_storm_events(conn, out, manifest_path)
        assert search(conn, year=2024)["total"] == 2


def test_noaa_import_rejects_incomplete_cohort_without_dropping_old_rows(tmp_path):
    out, manifest_path, _, _ = _stage(tmp_path)
    with connect(tmp_path / "site.sqlite") as conn:
        initialize(conn)
        import_noaa_storm_events(conn, out, manifest_path)
        manifest = json.loads(manifest_path.read_text())
        manifest["complete_requested_years"] = False
        manifest_path.write_text(json.dumps(manifest))
        with pytest.raises(ValueError, match="Partial NOAA"):
            import_noaa_storm_events(conn, out, manifest_path)
        assert search(conn)["total"] == 2


def test_noaa_schema_or_date_mismatch_fails_closed(tmp_path):
    data = _source_csv().replace(b"NEVER_THIS", b"")
    with pytest.raises(ValueError, match="omitted"):
        stage([2023], tmp_path / "bad.csv.gz", tmp_path / "bad.json",
              tmp_path / "raw", None, FakeNOAA(data), minimum_rows=1)



def test_noaa_transient_connection_resets_retry_and_clean_partial_files(tmp_path, monkeypatch):
    import requests
    import scripts.build_noaa_storm_events as builder
    monkeypatch.setattr(builder.time, "sleep", lambda _: None)

    class FlakyNOAA(FakeNOAA):
        attempts = 0
        def get(self, url, **kwargs):
            if url != INDEX:
                self.attempts += 1
                if self.attempts < 3:
                    raise requests.ConnectionError("Remote end closed connection without response")
            return super().get(url, **kwargs)

    client = FlakyNOAA(_source_csv())
    outcome = stage([2024], tmp_path / "new.csv.gz", tmp_path / "manifest.json",
                    tmp_path / "raw", tmp_path / "summary.json",
                    session=client, minimum_rows=2)
    assert outcome["total_events"] == 2
    assert client.attempts == 3
    assert not list(tmp_path.rglob("*.part"))


def test_noaa_rejects_permanent_http_error_without_retry(tmp_path, monkeypatch):
    import requests
    import scripts.build_noaa_storm_events as builder
    monkeypatch.setattr(builder.time, "sleep", lambda _: None)

    class DeniedNOAA(FakeNOAA):
        attempts = 0
        def get(self, url, **kwargs):
            if url != INDEX:
                self.attempts += 1
                raise requests.HTTPError("403 access denied",
                                         response=type("Resp", (), {"status_code": 403})())
            return super().get(url, **kwargs)

    client = DeniedNOAA(_source_csv())
    with pytest.raises(requests.HTTPError, match="403"):
        stage([2024], tmp_path / "new.csv.gz", tmp_path / "manifest.json",
              tmp_path / "raw", None, session=client, minimum_rows=2)
    assert client.attempts == 1
