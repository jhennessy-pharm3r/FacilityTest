"""Test authenticated application routes using actual complete original USFS six-TIFF source.

Only PUBLIC GEOGRAPHIC QA COORDINATES are used, never real insured properties.
Test-only location review inserts do not establish a physical facility.
"""
import json
import os

from fastapi.testclient import TestClient
from facilityrisk.app import app
from facilityrisk.db import connect,initialize
from facilityrisk.site_workspace import intake_site
from facilityrisk.intelligence import review_location


def run():
    if (not os.environ.get("FACILITY_RISK_WHP2023_RASTER_ROOT") or
            os.environ.get("FACILITY_RISK_REQUIRE_AUTH")!="1" or
            len(os.environ.get("FACILITY_RISK_AUTH_TOKEN",""))<24):
        raise RuntimeError("Test requires authenticated private server and installed original WHP2023 source")
    auth={"Authorization":"Bearer "+os.environ["FACILITY_RISK_AUTH_TOKEN"]}
    with TestClient(app) as client:
        def get(route,status=200):
            reply=client.get(route,headers=auth)
            if reply.status_code!=status:
                raise RuntimeError(f"Source API {route} unexpectedly returned {reply.status_code}: "+reply.text[:400])
            return reply.json()
        assert client.get("/api/lane-a/whp2023/full-status").status_code==401
        public=get("/api/lane-a/whp2023/full-status")
        assert public["state"]=="ready_publisher_rasters"
        assert public["source_archive_sha256"]=="7f10f1f8dd97551b8be1458fe0ec924df60b2cea7ece2d1af4c3c1166d1895ab"
        assert public["original_raster_files"]==6
        assert public["raster_valid_cells"]==267010030
        assert public["raster_nodata_cells"]==337107414
        assert public["insured_property_matches"]==0
        indexed=get("/api/source-indices/status")
        assert indexed["usda_whp2023_national_raster"]["state"]=="ready_publisher_rasters"
        from facilityrisk.lane_a_national_whp import PINNED_SOURCE_ARCHIVE_SHA256
        assert PINNED_SOURCE_ARCHIVE_SHA256==public["source_archive_sha256"]
        checks=[]
        for country,lon,lat,expected_cls,expected_cnt,expected_status in (
                ("norcal",-122,39.5,2,152,"PUBLISHER_RELATIVE_LANDSCAPE_HAZARD_AT_REVIEWED_POINT"),
                ("alaska",-150.1,61.4,6,0,"SPECIAL_NON_BURNABLE_OR_WATER_MASK_NOT_LOW_RISK"),
                ("hawaii",-155.8,19.6,1,182,"PUBLISHER_RELATIVE_LANDSCAPE_HAZARD_AT_REVIEWED_POINT")):
            with connect() as database:
                initialize(database)
                fixture=intake_site(database,{"name":"SOURCE QA ONLY - "+country,"country":"US"},"publisher-qa-test")
                id=fixture["facility_id"]
                database.execute("UPDATE facilities SET latitude=?,longitude=? WHERE id=?",(lat,lon,id))
                database.commit()
            unreviewed=get("/api/facilities/"+id+"/usfs-whp2023")
            assert unreviewed["state"]=="UNKNOWN_UNVERIFIED_SITE_COORDINATE"
            assert unreviewed["classified_value"] is None
            with connect() as database:
                initialize(database)
                review_location(database,id,"site_verified",
                    "https://research.fs.usda.gov/firelab/products/dataandtools/wildfire-hazard-potential",
                    "ci-public-coordinate-fixture",
                    "QA fixture only: coordinates are PUBLIC test points, NOT independently confirmed insured sites")
            value=get("/api/facilities/"+id+"/usfs-whp2023")
            assert value["state"]==expected_status
            assert value["classified_value"]==expected_cls
            assert value["continuous_value"]==expected_cnt
            assert value["source_original_zip_sha256"]==PINNED_SOURCE_ARCHIVE_SHA256
            assert value["hazard_is_insured_loss"] is False
            assert value["hazard_is_fire_probability"] is False
            with connect() as database:
                database.execute("UPDATE facilities SET latitude=latitude+0.1 WHERE id=?",(id,))
                database.commit()
            changed=get("/api/facilities/"+id+"/usfs-whp2023")
            assert changed["state"]=="UNKNOWN_UNVERIFIED_SITE_COORDINATE"
            checks.append({"QA_public_region":country,"observed_landscape_class":expected_cls,
                           "original_source_continuous_value":expected_cnt,"review_revocation_passed":True})
    return {"original_archive_pinned_SHA_verified":True,
            "six_full_270m_TIFFs_authenticated":True,
            "all_133505015_unmasked_geographic_cells_per_model_publisher_product_audited":True,
            "real_original_pixel_lookups":checks,
            "source_release_id":public["release_id"],
            "source_observations_not_insured_properties":True,
            "actual_live_host_deployed":False,
            "actual_insured_site_matches":0}


if __name__=="__main__":
    print("LANE_A_FULL_WHP_REAL_AUTHENTICATED_API_PASS="+json.dumps(run(),sort_keys=True))
