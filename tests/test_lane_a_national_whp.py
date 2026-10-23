"""Original full raster read-only service and verified current-coordinate guards.

Small synthetic TIFFs only in these unit tests. Real 368MB six-GeoTIFF source
is separately ingested, all-pixel-audited and queried in GitHub Actions.
"""
import hashlib
import sqlite3
from pathlib import Path

import pytest

rasterio = pytest.importorskip("rasterio")
from facilityrisk import lane_a_national_whp as service
from scripts import lane_a_whp_full_raster as importer
from test_lane_a_full_whp_rasters import original_six_tiff_fixture


@pytest.fixture
def mounted(monkeypatch,tmp_path):
    monkeypatch.setattr(importer,"MIN_ARCHIVE_BYTES",1)
    original=original_six_tiff_fixture(tmp_path/"official")
    fingerprint=hashlib.sha256(original.read_bytes()).hexdigest()
    monkeypatch.setattr(service,"PINNED_SOURCE_ARCHIVE_SHA256",fingerprint)
    root=tmp_path/"private-index"
    installed=importer.run(root,source_zip=original,full_audit=True,
                           expected_sha256=fingerprint)
    monkeypatch.setenv(service.ROOT_ENV,str(root))
    service._verify.cache_clear()
    yield root,installed
    service._verify.cache_clear()


@pytest.fixture
def private_sites():
    c=sqlite3.connect(":memory:")
    c.row_factory=sqlite3.Row
    c.executescript("""CREATE TABLE facilities (
        id TEXT PRIMARY KEY, latitude REAL, longitude REAL);
        CREATE TABLE location_reviews (
        facility_id TEXT PRIMARY KEY, precision TEXT,
        evidence_url TEXT, reviewed_latitude REAL,reviewed_longitude REAL);
    """)
    c.execute("INSERT INTO facilities VALUES('test-facility',41.5,-122.1)")
    yield c
    c.close()


def test_full_original_raster_is_source_only_and_includes_six_publishers(mounted):
    root,manifest=mounted
    state=service.status()
    assert state["state"]=="ready_publisher_rasters"
    assert state["original_raster_files"]==6
    assert state["raster_grid_cells"]==960000
    assert state["raster_valid_cells"]==6*159999
    assert state["raster_nodata_cells"]==6
    assert state["release_id"]==manifest["release_id"]
    assert state["source_not_client_loss_model"] is True
    assert state["insured_property_matches"]==0


def test_only_current_independently_verified_point_is_intersected(mounted,private_sites):
    c=private_sites
    blocked=service.reviewed_facility_whp(c,"test-facility")
    assert blocked["state"]=="UNKNOWN_UNVERIFIED_SITE_COORDINATE"
    c.execute("""INSERT INTO location_reviews VALUES
        ('test-facility','site_verified','https://agency.gov/site-geometry',
         41.5,-122.1)""")
    result=service.reviewed_facility_whp(c,"test-facility")
    assert result["state"]=="PUBLISHER_RELATIVE_LANDSCAPE_HAZARD_AT_REVIEWED_POINT"
    assert result["original_domain"]=="conus"
    assert result["classified_value"]==4
    assert result["continuous_value"]==253
    assert result["current_site_point_reviewed"] is True
    assert result["source_original_zip_sha256"]
    assert result["hazard_is_insured_loss"] is False
    c.execute("UPDATE facilities SET longitude=-122.12 WHERE id='test-facility'")
    again=service.reviewed_facility_whp(c,"test-facility")
    assert again["state"]=="UNKNOWN_UNVERIFIED_SITE_COORDINATE"
    assert again["continuous_value"] is None


def test_missing_raster_or_tampered_source_fails_closed(mounted,private_sites,monkeypatch):
    root,manifest=mounted
    assert service.status()["state"]=="ready_publisher_rasters"
    tiff=root/"releases"/manifest["release_id"]/"source-tiffs"/"whp2023_cls_conus.tif"
    original=tiff.read_bytes()
    tiff.chmod(0o600)
    tiff.write_bytes(b"bad-data")
    assert service.status()["state"]=="unavailable"
    with pytest.raises(service.RasterSourceUnavailable):
        service.reviewed_facility_whp(private_sites,"test-facility")
    tiff.write_bytes(original)
    assert service.status()["state"]=="ready_publisher_rasters"
    monkeypatch.delenv(service.ROOT_ENV)
    assert service.status()["state"]=="not_configured"
