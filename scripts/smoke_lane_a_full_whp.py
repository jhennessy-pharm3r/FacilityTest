"""Independent actual-full-raster query and mask/source domain audit.

Uses the original USDA six TIFFs installed from the source archive on this
ephemeral runner; public QA points are NEVER real insured facilities.
"""
import json
import os
from pathlib import Path

from facilityrisk import lane_a_national_whp as whp


def run():
    root=Path(os.environ["FACILITY_RISK_WHP2023_RASTER_ROOT"])
    facts=whp.status()
    if facts["state"]!="ready_publisher_rasters":
        raise RuntimeError("Actual original national USDA raster did not pass pinned source SHA validation")
    base,manifest=whp._ready()
    sample_count=0
    out=[]
    for domain,region in (("conus","norcal"),("ak","alaska"),("hi","hawaii")):
        pair={}
        for kind in ("cls","cnt"):
            name="whp2023_"+kind+"_"+domain+".tif"
            profile=manifest["tiff_independent_grid_qa"][name]
            matches=[x for x in profile["sampled_public_geographic_points"] if x["region"]==region]
            if len(matches)!=1:
                raise RuntimeError("Original national raster missing independently reprojection-validated QA point")
            q=matches[0]
            raw=whp._sample_one(base/"source-tiffs"/name,
                                q["longitude_wgs84"],q["latitude_wgs84"])
            if raw is None:
                raise RuntimeError("Original national raster cannot query coordinate within advertised source domain")
            if raw["original_pixel_value"]!=q["source_cell_value"]:
                raise RuntimeError("Raster sampled native pixel value does not agree with original full-audit receipt")
            if raw["pixel_index_derived_from_grid"] is not True:
                raise RuntimeError("Raster grid identity unexpectedly presented as source-native pixel ID")
            pair[kind]={"masked":raw["masked_nodata"],
                        "original_value":raw["original_pixel_value"],
                        "pixel_row":raw["row"],"pixel_column":raw["column"]}
            sample_count+=1
        out.append({"region":region,"source_domain":domain,"kind_samples":pair})
    if sample_count!=6:
        raise RuntimeError("Not all 6 original classified/continuous native domain samples completed")
    return {
        "official_archive_sha256":manifest["zip_original_source"]["sha256"],
        "release_id":facts["release_id"],
        "total_native_raster_grid_cells":facts["raster_grid_cells"],
        "valid_model_cells":facts["raster_valid_cells"],
        "masked_nodata_cells":facts["raster_nodata_cells"],
        "original_publisher_tiffs":facts["original_raster_files"],
        "geographic_domains":out,
        "publisher_grain":"source-native 270m pixels, not verified physical properties",
        "permanent_private_host_deployed":False,
        "real_facilities_or_claims_assessed":0,
        "result":"SOURCE_ONLY_QA_PASSED",
    }


if __name__=="__main__":
    print("LANE_A_FULL_WHP2023_REAL_RASTER_POINT_READS_PASS="+json.dumps(run(),sort_keys=True))
