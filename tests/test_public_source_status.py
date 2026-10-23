"""The public status feed must not fabricate successful dataset imports."""
import json
from pathlib import Path

import pytest

from facilityrisk.advanced_sources import SOURCE_META
from facilityrisk.registry_catalog import SOURCE_DEVICE, SOURCE_DRUG
from facilityrisk.source_extensions import SOURCES
from scripts.publish_source_status import build


def _reports(tmp_path, override=None):
    overrides = override or {}
    base = tmp_path / "primary.json"
    extra = tmp_path / "extended.json"
    base.write_text(json.dumps({"checks": [
        {"source": name, "state": overrides.get(name, "reachable"),
         "details": "HTTP 200; payload parsed", "url": endpoint or docs}
        for name, (docs, endpoint) in SOURCE_META.items()
    ]}), encoding="utf-8")
    extra.write_text(json.dumps({"checks": [
        {"source": source["name"], "state": "docs_reachable", "url": source["documentation"],
         "details": "Only documentation response fetched"}
        for source in SOURCES
    ]}), encoding="utf-8")
    return base, extra


def _catalog(path, rows, sources, generated_at="2026-10-22T19:00:00+00:00"):
    path.write_text(json.dumps({
        "schema_version": "1.0", "generated_at": generated_at,
        "fields": ["sector", "source"], "rows": rows, "sources": sources
    }), encoding="utf-8")


def test_status_exposes_real_probe_results_separate_from_imported_rows(tmp_path):
    primary, extended = _reports(tmp_path, {"FDA inspections": "requires_file",
                                             "NOAA storm events": "requires_file"})
    directory = tmp_path / "registry"
    directory.mkdir()
    _catalog(directory / "catalog.json",
             [["Medical device", SOURCE_DEVICE], ["Pharmaceutical", SOURCE_DRUG],
              ["Pharmaceutical", SOURCE_DRUG]],
             {"fda_device": {"status": "imported", "url": "https://api.fda.gov"},
              "fda_drug": {"status": "stale_preserved", "url": "https://www.fda.gov"}})
    _catalog(directory / "ireland-leap.json",
             [["Environmental licence", "Ireland EPA LEAP"]],
             {"ireland_leap": {"status": "imported", "url": "https://data.epa.ie"}})
    _catalog(directory / "canada-npri.json",
             [["Environmental reporting", "Canada NPRI"]],
             {"canada_npri": {"status": "imported", "url": "https://open.canada.ca"}})
    report = build(primary, extended, directory, "2026-10-23T12:00:00+00:00",
                   "https://github.com/example/FacilityTest/actions/runs/4")
    assert len(report["checks"]) == len(SOURCE_META)
    assert len(report["extended_checks"]) == len(SOURCES)
    checks = {row["source"]: row for row in report["checks"]}
    assert checks["EPA FRS"]["state"] == "reachable"
    assert checks["FDA inspections"]["state"] == "requires_file"
    assert checks["NOAA storm events"]["state"] == "requires_file"
    assert checks["EPA FRS"]["test_level"] == "documentation_or_connectivity_only"
    imported = {row["source"]: row for row in report["ingestions"]}
    assert imported["FDA device registrations"]["records"] == 1
    assert imported["FDA drug establishments"]["records"] == 2
    assert imported["FDA drug establishments"]["state"] == "stale_preserved"
    assert imported["EPA FRS national indexed registry"]["records"] is None
    assert imported["EPA FRS national indexed registry"]["state"] == "private_index_not_deployed"


def test_status_rejects_incomplete_probe_results(tmp_path):
    primary, extended = _reports(tmp_path)
    report = json.loads(primary.read_text(encoding="utf-8"))
    report["checks"].pop()
    primary.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="incomplete source checks"):
        build(primary, extended, tmp_path, "2026-10-23", "")


def test_unpublished_catalog_is_not_counted_as_ingested(tmp_path):
    primary, extended = _reports(tmp_path)
    report = build(primary, extended, tmp_path / "none", "2026-10-23", "")
    assert all(row["state"] == "not_published" and row["records"] is None
               for row in report["ingestions"] if row["source"] != "EPA FRS national indexed registry")


def test_status_rejects_unvalidated_import_count(tmp_path):
    primary, extended = _reports(tmp_path)
    directory = tmp_path / "registry"
    directory.mkdir()
    _catalog(directory / "catalog.json", [],
             {"fda_device": {"status": "imported"}})
    with pytest.raises(ValueError, match="claims import but has no cohort"):
        build(primary, extended, directory, "2026-10-23", "")



def test_aggregated_noaa_manifest_can_join_public_health_without_publishing_raw_events(tmp_path):
    from scripts.publish_source_status import (
        published_external_ingestions, merge_existing_public_status,
    )
    directory = tmp_path / "ingestion"
    directory.mkdir()
    manifest = {
        "schema_version": "1.0", "source": "NOAA Storm Events Details",
        "state": "staged_source_artifact", "records": 777,
        "checked_at": "2026-10-23T13:00:00+00:00", "scope": "NOAA regional events",
        "details": "National reported occurrence observations only",
        "documentation": "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/",
        "artifact_run_url": "https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/123",
        "private_raw_event_row": {"facility_address": "Never publish this"}
    }
    (directory / "noaa-storm-events.json").write_text(json.dumps(manifest))
    rows = published_external_ingestions(directory)
    assert rows[0]["records"] == 777
    assert "private_raw_event_row" not in rows[0]
    old = {"schema_version": "1.0", "generated_at": "2026-10-21",
           "checks": [{"source": "USGS", "state": "reachable"}],
           "ingestions": [{"source": "Some Registry", "records": 55}]}
    status = tmp_path / "status.json"
    status.write_text(json.dumps(old))
    merge_existing_public_status(status, directory)
    updated = json.loads(status.read_text())
    assert updated["generated_at"] == "2026-10-21"
    assert updated["checks"] == old["checks"]
    assert len(updated["ingestions"]) == 2


def test_public_ingest_metadata_fail_closed_on_unreviewed_sources_and_false_counts(tmp_path):
    from scripts.publish_source_status import published_external_ingestions
    folder = tmp_path / "ingestion"
    folder.mkdir()
    payload = {
        "schema_version": "1.0", "source": "Private Insured Locations",
        "state": "staged_source_artifact", "records": 3,
        "checked_at": "2026-10-23T13:00:00Z",
    }
    output = folder / "bad.json"
    output.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="Invalid or duplicate"):
        published_external_ingestions(folder)
    payload["source"] = "NOAA Storm Events Details"
    payload["records"] = -2
    output.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="Nonpositive"):
        published_external_ingestions(folder)
