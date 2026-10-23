"""Original USDA WHP2023 national 270m continuous/classified GeoTIFF ingestion.

Source publication: Dillon 2023, 4th ed., corrected 2024-07-17.
Original agency archive, six native TIFF rasters (CONUS, Alaska, Hawaii).
Records represent modeled raster grid cells, NOT physical facilities/losses.

Install with:
  python -m scripts.lane_a_whp_full_raster --root /secure/lane-a-whp
Optional --source-zip points to an independently downloaded ORIGINAL USDA archive.
Requires rasterio and numpy in the ingestion environment, not the web preview.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import urllib.request
import zipfile

ARCHIVE = "https://www.fs.usda.gov/rds/archive/products/RDS-2015-0047-4/RDS-2015-0047-4_Data.zip"
ORIGINAL_PUBLISHER = "USDA Forest Service Research Data Archive"
CITATION = "Dillon, Gregory K. 2023. Wildfire Hazard Potential for the United States (270-m), version 2023, 4th ed. Updated 17 July 2024. doi:10.2737/RDS-2015-0047-4"
PRODUCTS = tuple("whp2023_" + variant + "_" + domain + ".tif"
                 for variant in ("cls", "cnt") for domain in ("conus", "ak", "hi"))
MAX_ARCHIVE_BYTES = 650_000_000
MAX_TIFF_BYTES = 3_000_000_000
MAX_TOTAL_EXTRACTED = 9_000_000_000
MIN_ARCHIVE_BYTES = 100_000_000
SCHEMA = "facility_risk_usda_whp2023_full_six_raster_release_v1"
REGIONS = {
    "pnw": (-121.3,46.3), "norcal": (-122,39.5), "socal": (-118.1,34.2),
    "rockies": (-106.8,40.2), "southwest": (-111.4,33.8),
    "plains": (-99.5,39.2), "texas": (-97.3,31.2),
    "gulf": (-89.2,30.4), "southeast": (-83.2,34.1),
    "great_lakes": (-88.2,43.2), "mid_atlantic": (-78.1,37.6),
    "northeast": (-72,42), "alaska": (-150.1,61.4),
    "hawaii": (-155.8,19.6),
}
MAX_SAMPLE_CELLS = 50

def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def _write_json(path, value):
    p = Path(path)
    p.write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")

def retrieve(target, url=ARCHIVE):
    """Bound original first-party ZIP download; never follow user-supplied URLs."""
    if url != ARCHIVE:
        raise ValueError("Only the official version-pinned WHP Research Data Archive URL is allowed")
    target=Path(target)
    request=urllib.request.Request(url,headers={
        "User-Agent": "FacilityRisk-USDA-WHP2023-Original-Archive/1.0",
        "Accept": "application/zip,application/octet-stream,*/*",
    })
    digest=hashlib.sha256()
    size=0
    try:
        with urllib.request.urlopen(request,timeout=90) as response:
            final=response.geturl()
            if final != url:
                raise ValueError("Original archive redirected away from pinned official publisher URL")
            declared=response.headers.get("Content-Length")
            if declared is not None and int(declared)>MAX_ARCHIVE_BYTES:
                raise ValueError("Publisher original exceeds bounded source-archive cap")
            with target.open("wb") as file:
                while True:
                    block=response.read(4 * 1024 * 1024)
                    if not block:
                        break
                    size+=len(block)
                    if size>MAX_ARCHIVE_BYTES:
                        raise ValueError("Original ZIP exceeds max permitted transfer bytes")
                    file.write(block)
                    digest.update(block)
        if size < MIN_ARCHIVE_BYTES:
            raise ValueError("Publisher response too small for six complete 270m GeoTIFF products")
        with target.open("rb") as file:
            if file.read(4) != b"PK\x03\x04":
                raise ValueError("Publisher soft-200 returned non-ZIP data")
        return {"url":url,"bytes":size,"sha256":digest.hexdigest(),
                "retrieved_at_utc":datetime.now(timezone.utc).isoformat(),
                "actual_transfer":"full_original_official_usda_archive"}
    except Exception:
        target.unlink(missing_ok=True)
        raise

def _safe_members(archive):
    found={}
    total=0
    with zipfile.ZipFile(archive) as zipped:
        for member in zipped.infolist():
            parts=PurePosixPath(member.filename)
            if (parts.is_absolute() or ".." in parts.parts or
                    "\\" in member.filename or "\x00" in member.filename):
                raise ValueError("Unsafe source ZIP member path")
            kind=(member.external_attr>>16)&0o170000
            if kind not in (0,stat.S_IFREG,stat.S_IFDIR):
                raise ValueError("Source ZIP contains unsupported symlink/special file")
            if member.file_size>MAX_TIFF_BYTES:
                raise ValueError("Source ZIP member exceeds allowed extraction size")
            name=parts.name.lower()
            if name in PRODUCTS:
                if name in found:
                    raise ValueError("Duplicate original WHP source raster basename")
                if member.is_dir():
                    raise ValueError("Raster member cannot be directory")
                if not member.CRC or member.file_size < 100_000:
                    raise ValueError("Original raster member has invalid size/CRC")
                found[name]=member
                total+=member.file_size
        if set(found)!=set(PRODUCTS):
            raise ValueError("Expected exactly 6 original 2023 CONUS/AK/HI continuous/classified rasters; missing "
                             +repr(sorted(set(PRODUCTS)-set(found))))
        if total>MAX_TOTAL_EXTRACTED:
            raise ValueError("Original GeoTIFF extraction exceeds source cap")
    return found

def _extract_only_tiffs(archive, target):
    found=_safe_members(archive)
    target=Path(target)
    target.mkdir(parents=True,exist_ok=True)
    receipts={}
    with zipfile.ZipFile(archive) as zipped:
        for name in PRODUCTS:
            entry=found[name]
            dest=target/name
            digest=hashlib.sha256()
            written=0
            with zipped.open(entry) as source, dest.open("xb") as out:
                while block:=source.read(4*1024*1024):
                    written+=len(block)
                    if written>MAX_TIFF_BYTES:
                        raise ValueError("GeoTIFF exceeded entry maximum during extraction")
                    out.write(block)
                    digest.update(block)
            if written!=entry.file_size:
                raise ValueError("GeoTIFF decompressed bytes != publisher ZIP original length")
            receipts[name]={"archive_member":entry.filename,"bytes":written,
                            "sha256":digest.hexdigest(),"zip_crc32":entry.CRC}
    return receipts

def _raster_metadata(path, source_name, full_audit=False):
    import numpy as np
    import rasterio
    from rasterio.warp import transform

    kind,domain=source_name.split("_")[1:3]
    with rasterio.open(path) as ds:
        if (ds.driver!="GTiff" or ds.count!=1 or ds.crs is None or
                ds.width<20 or ds.height<20 or
                ds.transform.a==0 or ds.transform.e==0 or
                not ds.transform.is_rectilinear):
            raise ValueError("Original product not a georeferenced single-band 270m GeoTIFF")
        bounds=tuple(float(v) for v in ds.bounds)
        record={"original_product_name":source_name,"source_format":ds.driver,
                "source_crs_wkt":ds.crs.to_wkt(),"source_crs":str(ds.crs),
                "source_nodata":float(ds.nodata) if ds.nodata is not None else None,
                "dtype":ds.dtypes[0], "width":ds.width,"height":ds.height,
                "grid_cell_count":ds.width*ds.height,
                "cell_size_native_crs":[abs(ds.transform.a),abs(ds.transform.e)],
                "native_bounds":bounds,
                "raster_band_count":1,
                "product": "classified" if kind=="cls" else "continuous",
                "domain":domain,"pixel_observations_are_not_sites":True,
                "sampled_public_geographic_points":[],
                "exact_full_grid_audit":bool(full_audit)}
        for region,(lon,lat) in REGIONS.items():
            x,y=transform("EPSG:4326",ds.crs,[lon],[lat])
            column,row=ds.index(x[0],y[0])
            if not 0<=column<ds.width or not 0<=row<ds.height:
                continue
            value=next(ds.sample([(x[0],y[0])],masked=True))[0]
            valid=not np.ma.is_masked(value)
            numeric=float(value) if valid else None
            record["sampled_public_geographic_points"].append({
                "region":region,"longitude_wgs84":lon,"latitude_wgs84":lat,
                "pixel_column":column,"pixel_row":row,
                "source_cell_value":numeric,"pixel_masked":not valid})
        if full_audit:
            valid_pixels=0
            masked_pixels=0
            codes=Counter()
            lo=hi=None
            for _,window in ds.block_windows(1):
                values=ds.read(1,window=window,masked=True)
                filled=values.compressed()
                valid_pixels+=len(filled)
                masked_pixels+=values.size-len(filled)
                if filled.size:
                    vmin=float(np.min(filled))
                    vmax=float(np.max(filled))
                    lo=vmin if lo is None else min(lo,vmin)
                    hi=vmax if hi is None else max(hi,vmax)
                    if kind=="cls":
                        count, freq=np.unique(filled,return_counts=True)
                        for code,n in zip(count,freq):
                            if float(code)!=int(code):
                                raise ValueError("Original classified raster contains nonintegral class")
                            codes[str(int(code))]+=int(n)
            if valid_pixels+masked_pixels!=record["grid_cell_count"]:
                raise ValueError("Source raster cell count did not reconcile with masks")
            record["valid_raster_pixels"]=valid_pixels
            record["masked_nodata_pixels"]=masked_pixels
            record["source_value_min"]=lo
            record["source_value_max"]=hi
            if kind=="cls":
                record["observed_original_class_codes"]=dict(sorted(codes.items(),key=lambda x:int(x[0])))
                if not codes or any(int(key) not in range(1,8) for key in codes):
                    raise ValueError("Unexpected WHP2023 original classified product class codes: "+repr(codes))
    return record

def run(root, *, source_zip=None, expected_sha256=None, full_audit=False,
        archive_url=ARCHIVE):
    """Atomic, reproducible full TIFF release; never replace active data on failed QA."""
    root=Path(root).expanduser()
    if root.is_symlink():
        raise ValueError("Refusing symlinked source release directory")
    root.mkdir(parents=True,exist_ok=True)
    root=root.resolve()
    releases=root/"releases"
    if releases.is_symlink():
        raise ValueError("Refusing symlinked release storage")
    releases.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".stage-",dir=str(root)) as scratch:
        staging=Path(scratch)
        archive=staging/"RDS-2015-0047-4_Data.zip"
        if source_zip is None:
            original=retrieve(archive,url=archive_url)
        else:
            external=Path(source_zip).expanduser().resolve(strict=True)
            if not external.is_file() or external.is_symlink():
                raise ValueError("Source archive is not a regular file")
            archive_size=external.stat().st_size
            if not MIN_ARCHIVE_BYTES<=archive_size<=MAX_ARCHIVE_BYTES:
                raise ValueError("Original ZIP is not within independently bounded size")
            original={"url":archive_url,"bytes":archive_size,"sha256":sha256(external),
                      "retrieved_at_utc":None,"actual_transfer":"operator_original_official_archive"}
            shutil.copyfile(external,archive)
        if expected_sha256 is not None and original["sha256"].lower()!=expected_sha256.lower():
            raise ValueError("Original official USDA WHP2023 archive SHA256 differs from pinned release")
        tiffs=staging/"source-tiffs"
        receipts=_extract_only_tiffs(archive,tiffs)
        inspections={}
        for source_name in PRODUCTS:
            inspections[source_name]=_raster_metadata(
                tiffs/source_name,source_name,full_audit=full_audit)
        release_id=hashlib.sha256(("USDA-WHP2023-ORIGINAL-"+original["sha256"]).encode()).hexdigest()[:24]
        manifest={"schema_version":SCHEMA,"publisher":ORIGINAL_PUBLISHER,
                  "citation":CITATION,"publication_vintage":"2023, corrected 2024-07-17",
                  "product_model_inputs":"LANDFIRE 2020 and historical FSim",
                  "zip_original_source":original,
                  "original_geoTIFF_source":receipts,"tiff_independent_grid_qa":inspections,
                  "all_six_original_tiffs_verified":True,
                  "all_original_grid_pixels_counted":bool(full_audit),
                  "source_only":True,"verified_site_matches":0,
                  "insured_loss_or_property_damage_records":0,
                  "release_id":release_id,"source_coverage":"publisher-CONUS-Alaska-Hawaii-masked-raster-domains",
                  "raw_archive_retained":True,"no_synthetic_source_values":True,
                  "prepared_at_utc":datetime.now(timezone.utc).isoformat()}
        # Preserve original entire publisher ZIP for SHA-based reproducible refresh
        # and chain of custody; only six TIF files are extracted.
        _write_json(staging/"manifest.json",manifest)
        for file in [archive, staging/"manifest.json", *tiffs.iterdir()]:
            file.chmod(0o444)
        target=releases/release_id
        if target.is_symlink():
            raise ValueError("Existing release path cannot be a symlink")
        if target.exists():
            other=json.loads((target/"manifest.json").read_text())
            if (other.get("zip_original_source",{}).get("sha256")!=original["sha256"] or
                    any(sha256(target/"source-tiffs"/p)!=receipts[p]["sha256"] for p in PRODUCTS)):
                raise ValueError("Existing release differs; refusing replacement")
        else:
            shutil.move(str(staging),str(target))
        pointer={"schema_version":SCHEMA,"release_id":release_id,
                 "relative_root":"releases/"+release_id,
                 "source_has_entire_official_six_raster_archive":True,
                 "physical_site_matches":0,"production_deployment":False}
        tmp=root/(".current-"+release_id+".json")
        _write_json(tmp,pointer)
        os.replace(tmp,root/"current.json")
        return manifest

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",required=True,
                        help="Absolute persistent private directory for content-addressed verified TIFF release")
    parser.add_argument("--source-zip",default=None)
    parser.add_argument("--expected-sha256",default=None)
    parser.add_argument("--full-audit",action="store_true")
    args=parser.parse_args(argv)
    manifest=run(args.root,source_zip=args.source_zip,
                 expected_sha256=args.expected_sha256,
                 full_audit=args.full_audit)
    counts={name:{"width":x["width"],"height":x["height"],
                  "valid_raster_pixels":x.get("valid_raster_pixels"),
                  "masked_nodata_pixels":x.get("masked_nodata_pixels"),
                  "original_codes":x.get("observed_original_class_codes")}
            for name,x in manifest["tiff_independent_grid_qa"].items()}
    print("LANE_A_FULL_WHP2023_ORIGINAL_RASTERS_VALIDATED="+json.dumps({
        "release":manifest["release_id"],
        "original_archive_bytes":manifest["zip_original_source"]["bytes"],
        "original_archive_sha256":manifest["zip_original_source"]["sha256"],
        "six_products":counts,
        "source_only":True,"durable_private_host_deployed":False},sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
