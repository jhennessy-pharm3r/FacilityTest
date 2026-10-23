"""Synthetic parser/rollback fixtures only. Real publisher raster QA runs in Actions."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import zipfile

import pytest

rasterio = pytest.importorskip("rasterio")
np = pytest.importorskip("numpy")
from rasterio.transform import from_origin

from scripts import lane_a_whp_full_raster as r


def original_six_tiff_fixture(base, *, omitted=None, additional=None):
    base.mkdir(parents=True, exist_ok=True)
    zip_path=base/"original-mocked.zip"
    with zipfile.ZipFile(zip_path,"w",compression=zipfile.ZIP_DEFLATED) as archive:
        for name in r.PRODUCTS:
            if name==omitted:
                continue
            file=base/name
            kind=name.split("_")[1]
            dtype="uint8" if kind=="cls" else "int32"
            pixel_value=4 if kind=="cls" else 253
            data=np.full((400,400),pixel_value,dtype=dtype)
            data[0,0]=0
            domain=Path(name).stem.split("_")[-1]
            origin={"conus":(-123,42),"ak":(-152,63),"hi":(-157,21)}[domain]
            with rasterio.open(file,"w",driver="GTiff",height=400,width=400,
                               count=1,dtype=dtype,nodata=0,
                               crs="EPSG:4326",transform=from_origin(origin[0],origin[1],0.005,0.005)) as out:
                out.write(data,1)
            assert file.stat().st_size>=100000
            archive.write(file,arcname="nested/original/"+name)
        if additional:
            archive.writestr(additional,b"untrusted")
    return zip_path


def test_installs_all_six_source_rasters_atomic_and_audits_full_original_grid(tmp_path,monkeypatch):
    monkeypatch.setattr(r,"MIN_ARCHIVE_BYTES",1)
    source=original_six_tiff_fixture(tmp_path/"original")
    path=tmp_path/"immutable"
    manifest=r.run(path,source_zip=source,full_audit=True)
    assert manifest["all_six_original_tiffs_verified"] is True
    assert manifest["all_original_grid_pixels_counted"] is True
    assert set(manifest["original_geoTIFF_source"])==set(r.PRODUCTS)
    assert manifest["zip_original_source"]["sha256"]==hashlib.sha256(source.read_bytes()).hexdigest()
    for name in r.PRODUCTS:
        profile=manifest["tiff_independent_grid_qa"][name]
        assert profile["valid_raster_pixels"]==159999
        assert profile["masked_nodata_pixels"]==1
        assert profile["grid_cell_count"]==160000
        if "_cls_" in name:
            assert profile["observed_original_class_codes"]=={"4":159999}
    pointer=json.loads((path/"current.json").read_text())
    assert pointer["release_id"]==manifest["release_id"]
    original_pointer=(path/"current.json").read_bytes()
    assert len(list((path/"releases").iterdir()))==1
    again=r.run(path,source_zip=source,full_audit=True,
                expected_sha256=manifest["zip_original_source"]["sha256"])
    assert again["release_id"]==manifest["release_id"]
    assert (path/"current.json").read_bytes()==original_pointer
    assert len(list((path/"releases").iterdir()))==1
    existing=path/"releases"/manifest["release_id"]/"source-tiffs"/r.PRODUCTS[0]
    existing.chmod(0o600)
    existing.write_bytes(b"tampered")
    with pytest.raises(ValueError,match="Existing release differs"):
        r.run(path,source_zip=source,full_audit=False)
    assert (path/"current.json").read_bytes()==original_pointer


def test_rejects_incomplete_malicious_and_unapproved_source_before_pointer(tmp_path,monkeypatch):
    monkeypatch.setattr(r,"MIN_ARCHIVE_BYTES",1)
    incomplete=original_six_tiff_fixture(tmp_path/"partial",omitted=r.PRODUCTS[-1])
    with pytest.raises(ValueError,match="exactly 6"):
        r.run(tmp_path/"output",source_zip=incomplete)
    assert not (tmp_path/"output/current.json").exists()
    bad=original_six_tiff_fixture(tmp_path/"traversal",additional="../../credentials.dat")
    with pytest.raises(ValueError,match="Unsafe source ZIP"):
        r.run(tmp_path/"output",source_zip=bad)
    assert not (tmp_path/"output/current.json").exists()
    real=original_six_tiff_fixture(tmp_path/"other")
    with pytest.raises(ValueError,match="differs from pinned release"):
        r.run(tmp_path/"output",source_zip=real,
              expected_sha256="0"*64)
    assert not (tmp_path/"output/current.json").exists()


def test_duplicate_original_raster_name_is_rejected(tmp_path):
    archive=tmp_path/"duplicate.zip"
    with zipfile.ZipFile(archive,"w") as packed:
        for name in r.PRODUCTS:
            packed.writestr("first/"+name,b"x"*110000)
        packed.writestr("second/"+r.PRODUCTS[0],b"x"*110000)
    with pytest.raises(ValueError,match="Duplicate original"):
        r._safe_members(archive)
