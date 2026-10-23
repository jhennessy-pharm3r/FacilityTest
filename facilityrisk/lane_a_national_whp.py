"""Read-only full original USDA WHP2023 six-raster release — private app only.

No arbitrary geography query or site matching. A property coordinate must
already have an independently corroborated CURRENT location-review record.
WHP classes are landscape hazard, NOT insured loss or wildfire probability.
"""
from __future__ import annotations
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import re

from .db import get_db_path
from .intelligence import is_reviewed_site_coordinate

SCHEMA = "facility_risk_usda_whp2023_full_six_raster_release_v1"
ROOT_ENV = "FACILITY_RISK_WHP2023_RASTER_ROOT"
# Updated exclusively after a full verified original public USDA archive run.
PINNED_SOURCE_ARCHIVE_SHA256 = "__PENDING_INDEPENDENT_WHP2023_FULL_ARCHIVE_AUDIT__"
PRODUCTS = tuple("whp2023_" + kind + "_" + region + ".tif"
                 for kind in ("cls","cnt") for region in ("conus","ak","hi"))
CLASS_CODES = {1:"Very low",2:"Low",3:"Moderate",4:"High",5:"Very high",
               6:"Non-burnable",7:"Water"}
SHA = re.compile(r"^[0-9a-f]{64}$")


class RasterSourceUnavailable(ValueError):
    """Missing or invalid original USDA 270m raster — never classify as safe."""


def _hash(path):
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b""):
            digest.update(block)
    return digest.hexdigest()


def _source_root():
    raw=os.environ.get(ROOT_ENV,"").strip()
    if not raw:
        raise RasterSourceUnavailable("Original publisher rasters not installed")
    root=Path(raw).expanduser()
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise RasterSourceUnavailable("Raster release needs an absolute existing private path")
    path=root.resolve()
    if path==get_db_path().resolve():
        raise RasterSourceUnavailable("Original national raster may not share the insured workspace database")
    return path


def _fingerprint(root):
    pointer=root/"current.json"
    if pointer.is_symlink() or not pointer.is_file():
        raise RasterSourceUnavailable("No activated publisher raster release")
    manifest_pointer=json.loads(pointer.read_text(encoding="utf-8"))
    release=manifest_pointer.get("release_id","")
    if (manifest_pointer.get("schema_version")!=SCHEMA or
            not isinstance(release,str) or
            re.fullmatch(r"[0-9a-f]{24}",release) is None or
            manifest_pointer.get("relative_root")!="releases/"+release):
        raise RasterSourceUnavailable("Malformed original raster release pointer")
    base=root/"releases"/release
    if base.is_symlink() or not base.is_dir() or not base.resolve().is_relative_to(root):
        raise RasterSourceUnavailable("Original raster release path escapes storage root")
    paths=[pointer,base/"manifest.json",base/"RDS-2015-0047-4_Data.zip"]
    paths.extend(base/"source-tiffs"/name for name in PRODUCTS)
    fingerprint=[]
    for path in paths:
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise RasterSourceUnavailable("Original six-raster release file missing/unsafe")
        st=path.stat()
        fingerprint.append((str(path.resolve()),st.st_size,st.st_mtime_ns,st.st_ctime_ns,st.st_ino))
    return base,manifest_pointer,tuple(fingerprint)


@lru_cache(maxsize=4)
def _verify(release_root,release_id,fingerprint):
    if not SHA.fullmatch(PINNED_SOURCE_ARCHIVE_SHA256):
        raise RasterSourceUnavailable("Original USDA 2023 full archive SHA has not passed independent pinning")
    base=Path(release_root)
    manifest=json.loads((base/"manifest.json").read_text(encoding="utf-8"))
    source=manifest.get("zip_original_source",{})
    tiffs=manifest.get("original_geoTIFF_source",{})
    grid=manifest.get("tiff_independent_grid_qa",{})
    if (manifest.get("schema_version")!=SCHEMA or
            manifest.get("release_id")!=release_id or
            manifest.get("all_six_original_tiffs_verified") is not True or
            manifest.get("all_original_grid_pixels_counted") is not True or
            manifest.get("source_only") is not True or
            manifest.get("verified_site_matches")!=0 or
            manifest.get("insured_loss_or_property_damage_records")!=0 or
            source.get("url")!="https://www.fs.usda.gov/rds/archive/products/RDS-2015-0047-4/RDS-2015-0047-4_Data.zip" or
            source.get("sha256")!=PINNED_SOURCE_ARCHIVE_SHA256 or
            set(tiffs)!=set(PRODUCTS) or set(grid)!=set(PRODUCTS)):
        raise RasterSourceUnavailable("Original full national source version, rights or count checks failed")
    if _hash(base/"RDS-2015-0047-4_Data.zip")!=PINNED_SOURCE_ARCHIVE_SHA256:
        raise RasterSourceUnavailable("Original government archive SHA-256 invalid")
    for name in PRODUCTS:
        path=base/"source-tiffs"/name
        receipt=tiffs[name]
        item=grid[name]
        if (receipt.get("sha256")!=_hash(path) or
                receipt.get("bytes")!=path.stat().st_size or
                item.get("original_product_name")!=name or
                item.get("product")!=("classified" if "_cls_" in name else "continuous") or
                item.get("exact_full_grid_audit") is not True or
                item.get("valid_raster_pixels",0)+item.get("masked_nodata_pixels",0)!=item.get("grid_cell_count") or
                not item.get("source_crs_wkt")):
            raise RasterSourceUnavailable("Original source TIFF/provenance/pixel audit changed")
        if "_cls_" in name:
            counts=item.get("observed_original_class_codes",{})
            if (not isinstance(counts,dict) or
                    any(int(code) not in CLASS_CODES for code in counts) or
                    sum(counts.values())!=item.get("valid_raster_pixels")):
                raise RasterSourceUnavailable("Original WHP category mask or census changed")
    try:
        import rasterio
        if not hasattr(rasterio,"open"):
            raise ImportError("Rasterio lacks geospatial TIFF reader")
    except ImportError as exc:
        raise RasterSourceUnavailable("Install rasterio in the private geospatial API runtime") from exc
    return manifest


def _ready():
    try:
        root=_source_root()
        base,pointer,fingerprint=_fingerprint(root)
        return base,_verify(str(base),pointer["release_id"],fingerprint)
    except (OSError,ValueError,TypeError,KeyError,ImportError,
            json.JSONDecodeError) as exc:
        raise RasterSourceUnavailable("Verified full official WHP2023 raster release missing or invalid") from exc


def status():
    if not os.environ.get(ROOT_ENV,"").strip():
        return {"state":"not_configured",
                "source":"USFS_WHP2023_270M_SIX_ORIGINAL_TIFFS",
                "original_raster_files":None,"insured_property_matches":0,
                "notice":"Full national 270m publisher raster not mounted on this server"}
    try:
        _,manifest=_ready()
        profiles=manifest["tiff_independent_grid_qa"]
        return {"state":"ready_publisher_rasters",
                "source":"USFS_WHP2023_270M_SIX_ORIGINAL_TIFFS",
                "release_id":manifest["release_id"],
                "source_archive_sha256":manifest["zip_original_source"]["sha256"],
                "original_raster_files":len(profiles),
                "domain_products":["CONUS","Alaska","Hawaii"],
                "raster_grid_cells":sum(p["grid_cell_count"] for p in profiles.values()),
                "raster_valid_cells":sum(p["valid_raster_pixels"] for p in profiles.values()),
                "raster_nodata_cells":sum(p["masked_nodata_pixels"] for p in profiles.values()),
                "vintage":"WHP2023 revised 2024-07-17; reflects LANDFIRE 2020",
                "masked_areas_remain_unknown":True,
                "point_to_property_association_requires_review":True,
                "insured_property_matches":0,
                "source_not_client_loss_model":True,
                "note":"Original publisher grid, not an active fire forecast, parcel damage, claims or national FEMA layer"}
    except RasterSourceUnavailable:
        return {"state":"unavailable",
                "source":"USFS_WHP2023_270M_SIX_ORIGINAL_TIFFS",
                "original_raster_files":None,"insured_property_matches":0,
                "notice":"Full original USDA WHP2023 raster missing/invalid; no wildfire hazard conclusion"}


def _sample_one(path,lon,lat):
    """Source-native cell sampling after CRS transform; retain mask and pixel identity."""
    import numpy as np
    import rasterio
    from rasterio.warp import transform
    with rasterio.open(path) as ds:
        xs,ys=transform("EPSG:4326",ds.crs,[lon],[lat])
        x,y=xs[0],ys[0]
        col,row=ds.index(x,y)
        if not 0<=col<ds.width or not 0<=row<ds.height:
            return None
        pix=next(ds.sample([(x,y)],masked=True))[0]
        masked=bool(np.ma.is_masked(pix))
        value=None if masked else float(pix)
        if not masked and not math.isfinite(value):
            raise RasterSourceUnavailable("Nonfinite verified source raster pixel")
        return {"column":int(col),"row":int(row),
                "original_pixel_value":value,"masked_nodata":masked,
                "source_native_pixel_id":None,"pixel_index_derived_from_grid":True}


def reviewed_facility_whp(conn,facility_id):
    base,manifest=_ready()
    site=conn.execute("SELECT id,latitude,longitude FROM facilities WHERE id=?",
                      (facility_id,)).fetchone()
    if site is None:
        raise LookupError("Unknown private research facility")
    review=conn.execute(
        "SELECT * FROM location_reviews WHERE facility_id=?",(facility_id,)
    ).fetchone()
    if not is_reviewed_site_coordinate(site,review):
        return {"source":"USFS_WHP2023","facility_id":facility_id,
                "state":"UNKNOWN_UNVERIFIED_SITE_COORDINATE",
                "continuous_value":None,"classified_value":None,
                "physical_site_association_verified":False,
                "hazard_is_insured_loss":False,
                "notice":"A current independently corroborated source-backed facility coordinate is required"}
    lon,lat=float(site["longitude"]),float(site["latitude"])
    original={}
    for domain in ("conus","ak","hi"):
        cont=_sample_one(base/"source-tiffs"/("whp2023_cnt_"+domain+".tif"),lon,lat)
        cls=_sample_one(base/"source-tiffs"/("whp2023_cls_"+domain+".tif"),lon,lat)
        if cont is None and cls is None:
            continue
        if cont is None or cls is None:
            raise RasterSourceUnavailable("Source continuous/classified geographic domains disagree")
        if not cont["masked_nodata"] or not cls["masked_nodata"]:
            original[domain]={"continuous":cont,"classified":cls}
    if len(original)>1:
        raise RasterSourceUnavailable("Multiple original USDA raster domains overlap at point; manual CRS review")
    if not original:
        return {"source":"USFS_WHP2023","facility_id":facility_id,
                "state":"UNKNOWN_OUTSIDE_VALID_PUBLISHER_RASTER_CELLS",
                "continuous_value":None,"classified_value":None,
                "hazard_is_insured_loss":False,
                "release_id":manifest["release_id"],
                "vintage":"2023 revised 2024, landscape ca. 2020"}
    region,record=next(iter(original.items()))
    cls=record["classified"]["original_pixel_value"]
    cnt=record["continuous"]["original_pixel_value"]
    code=int(cls) if cls is not None else None
    if code is not None and (code not in CLASS_CODES or cls!=code):
        raise RasterSourceUnavailable("Unrecognized original USDA classified raster code")
    status="PUBLISHER_RELATIVE_LANDSCAPE_HAZARD_AT_REVIEWED_POINT"
    if cnt is None or code is None:
        status="UNKNOWN_MASKED_SOURCE_RASTER_CELL"
    elif code in (6,7):
        status="SPECIAL_NON_BURNABLE_OR_WATER_MASK_NOT_LOW_RISK"
    return {"source":"USFS_WHP2023","facility_id":facility_id,
            "state":status,
            "original_domain":region,"continuous_value":cnt,
            "classified_value":code,
            "classified_label":CLASS_CODES.get(code) if code else None,
            "raster_grid_indices":{kind:{"row":value["row"],"column":value["column"]}
                                   for kind,value in record.items()},
            "original_native_pixel_ids_unpublished":True,
            "model_resolution_m":270,"raster_release_id":manifest["release_id"],
            "source_original_zip_sha256":manifest["zip_original_source"]["sha256"],
            "site_coordinate_evidence_url":review["evidence_url"],
            "current_site_point_reviewed":True,
            "publisher_vintage":"2023 revised 2024-07-17; 2020 fuels",
            "hazard_is_insured_loss":False,"hazard_is_fire_probability":False,
            "property_specific_loss_model":False,
            "source_not_current_season_forecast":True}
