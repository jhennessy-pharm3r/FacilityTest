"""Reviewer-only incident screening for an existing source-reported facility.

This performs bounded screening across first-party USCG NRC/CSB reporting
observations. It NEVER crosswalks an observation into a verified physical site,
accident, insured property, insurance loss or risk score. We retain original
native IDs and as-reported uncertainty. PHMSA enforcement cases have no
validated physical event-site coordinates and are intentionally excluded.
"""
from __future__ import annotations
from difflib import SequenceMatcher
import json
import math
import re
from .match import haversine_km
from .industrial_source_indices import _verified,_db

_VALID_COUNTRIES={"US","USA","UNITED STATES","UNITED STATES OF AMERICA",
                  "PUERTO RICO","PR","U.S.","UNITED STATES (PUERTO RICO)"}
_OPERATOR_STOP={"inc","llc","corp","corporation","company","co","limited","ltd",
                "the","of","and","facility","plant","manufacturing","site","operations"}
_ALLOWED_STATE=re.compile(r"[A-Z]{2}\Z")
_MAX_ROWS_PER_SOURCE=1500
_MAX_SOURCE_NAMESPACES=18

def _normalize(s):
    tokens=re.findall(r"[a-z0-9]+",str(s or "").lower())
    return " ".join(t for t in tokens if t not in _OPERATOR_STOP)[:180]

def _company_similarity(a,b):
    na,nb=_normalize(a),_normalize(b)
    if len(na)<5 or len(nb)<5:
        return 0.0
    return round(SequenceMatcher(None,na,nb).ratio(),3)

def _site_payload(site):
    if not isinstance(site,dict) or not site.get("id"):
        raise ValueError("Site identity record is required")
    name=str(site.get("name") or "")[:200].strip()
    company=str(site.get("company") or "")[:200].strip()
    city=str(site.get("city") or "")[:100].strip()
    state=str(site.get("state") or "").strip().upper()
    country=str(site.get("country") or "").strip().upper()
    if not city or not _ALLOWED_STATE.fullmatch(state):
        return {"state":"INSUFFICIENT_REPORTED_SITE_CITY_OR_STATE",
                "screenable":False,"site_id":site["id"],"country":country,
                "limitations":"US state and city are required; no address or headquarters guess is made"}
    if country and country not in _VALID_COUNTRIES:
        return {"state":"OUTSIDE_TESTED_US_REPORTING_SCREEN",
                "screenable":False,"site_id":site["id"],"country":country,
                "limitations":"No inference that other countries have no industrial incidents"}
    lat,lon=site.get("latitude"),site.get("longitude")
    if lat is None or lon is None:
        lat=lon=None
    else:
        try:lat=float(lat);lon=float(lon)
        except (TypeError,ValueError):lat=lon=None
        if lat is not None and not (-90<=lat<=90 and -180<=lon<=180):
            lat=lon=None
    return {"state":"SCREENABLE_UNVERIFIED_SITE_SOURCE_IDENTITY",
            "screenable":True,"site_id":site["id"],"site_name":name,"site_company":company,
            "city":city,"region":state,"country":country or "UNSPECIFIED",
            "site_lat":lat,"site_lon":lon,
            "coordinate_quality":str(site.get("coordinate_quality") or "unassessed")[:120],
            "identity_review_status":str(site.get("site_status") or "source_observation")[:120]}

def screen_site(site,*,radius_km=10,limit=30,source_years=None):
    if not isinstance(radius_km,(float,int)) or isinstance(radius_km,bool) or not 1<=radius_km<=50:
        raise ValueError("Radius must be 1-50 km for source-only context review")
    if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=50:
        raise ValueError("Limit must be 1-50 for reviewer screening")
    prepared=_site_payload(site)
    if not prepared["screenable"]:
        return {"site":prepared,"state":"NOT_SCREENED_INSUFFICIENT_SOURCE_IDENTITY",
                "reported_candidate_count":None,"results":[],
                "verified_insured_matches":0,"verified_losses":0,
                "no_zero_risk_inference":True}
    found,facts=_verified("observations")
    source_names=sorted(k for k in facts["source_counts"] if k=="csb" or re.fullmatch(r"nrc_20\d{2}",k))
    if source_years is not None:
        allowed={f"nrc_{int(y)}" for y in source_years}
        source_names=[x for x in source_names if x=="csb" or x in allowed]
    if len(source_names)>_MAX_SOURCE_NAMESPACES:
        raise ValueError("Unexpected source namespace expansion; revalidate index")
    city_norm=prepared["city"].strip().casefold()
    state=prepared["region"]
    lat,lon=prepared["site_lat"],prepared["site_lon"]
    has_coords=lat is not None and lon is not None
    # A bounding box is only a performance filter. Final source-coordinate
    # distance uses Haversine; source points are not property polygons.
    if has_coords:
        lat_delta=min(.6,float(radius_km)/110.57+0.01)
        lon_delta=min(1.0,float(radius_km)/(111.32*max(.20,abs(math.cos(math.radians(lat)))))+0.01)
    result=[]
    examined=0
    capped_sources=[]
    with _db(found["index"]) as conn:
        for source in source_names:
            if has_coords:
                rows=conn.execute("""SELECT source,source_id,publisher_native_id,
                         source_vintage,incident_date,city,state,latitude,longitude,
                         evidence_status,site_link_status,source_url,source_json
                         FROM source_incidents
                         WHERE source=? AND UPPER(state)=?
                         AND ((latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?)
                              OR LOWER(TRIM(city))=?)
                         LIMIT ?""",
                    (source,state,lat-lat_delta,lat+lat_delta,lon-lon_delta,lon+lon_delta,
                     city_norm,_MAX_ROWS_PER_SOURCE+1)).fetchall()
            else:
                rows=conn.execute("""SELECT source,source_id,publisher_native_id,
                         source_vintage,incident_date,city,state,latitude,longitude,
                         evidence_status,site_link_status,source_url,source_json
                         FROM source_incidents
                         WHERE source=? AND UPPER(state)=?
                         AND LOWER(TRIM(city))=? LIMIT ?""",
                    (source,state,city_norm,_MAX_ROWS_PER_SOURCE+1)).fetchall()
            if len(rows)>_MAX_ROWS_PER_SOURCE:
                capped_sources.append(source)
                rows=rows[:_MAX_ROWS_PER_SOURCE]
            examined+=len(rows)
            for row in rows:
                candidate=dict(row)
                if candidate["site_link_status"]!="candidate_only_not_matched":
                    raise ValueError("Source-to-site identity unexpectedly promoted")
                raw=json.loads(candidate["source_json"])
                reported_company=str(raw.get("company_as_reported") or "")[:180].strip()
                similarity=max(_company_similarity(prepared["site_company"],reported_company),
                               _company_similarity(prepared["site_name"],reported_company))
                same_city=bool(candidate["city"] and
                               candidate["city"].strip().casefold()==city_norm)
                distance=None
                if has_coords and candidate["latitude"] is not None and candidate["longitude"] is not None:
                    distance=round(haversine_km(lat,lon,float(candidate["latitude"]),float(candidate["longitude"])),2)
                # Only geographically plausible or operator+civic-text
                # candidate rows survive, never arbitrary company-only merges.
                nearby=distance is not None and distance<=radius_km
                named=same_city and similarity>=0.78
                if not (nearby or named):
                    continue
                checks=[]
                if nearby:checks.append("source_point_near_reported_site_reference")
                if named:checks.append("similar_reported_company_and_city")
                if same_city:checks.append("same_reported_city")
                result.append({
                    "source":candidate["source"],
                    "source_id":candidate["source_id"],
                    "publisher_native_id":candidate["publisher_native_id"],
                    "reporting_vintage":candidate["source_vintage"],
                    "incident_date_as_reported":candidate["incident_date"],
                    "reported_company":reported_company,
                    "reported_city":candidate["city"],
                    "reported_state":candidate["state"],
                    "reported_distance_km":distance,
                    "name_similarity":similarity,
                    "candidate_checks":checks,
                    "agency_evidence_status":candidate["evidence_status"],
                    "source_url":candidate["source_url"],
                    "source_coordinate_semantics":"incident_or_notification_location_not_verified_insured_property",
                    "review_status":"POTENTIAL_RELATIONSHIP_ONLY_UNVERIFIED",
                    "confirmed_causation":False,
                    "insured_loss_verified":False,
                    "exact_site_identity_verified":False
                })
    result.sort(key=lambda x:(0 if "similar_reported_company_and_city" in x["candidate_checks"] else 1,
                              x["reported_distance_km"] if x["reported_distance_km"] is not None else 1e8,
                              x["source"],x["source_id"]))
    return {
      "state":"REVIEWER_SOURCE_CANDIDATE_SCREEN_COMPLETED",
      "site":prepared,
      "release_id":found["release"],
      "source_namespaces_reviewed":len(source_names),
      "publisher_rows_examined":examined,
      "candidate_rows_before_display_limit":len(result),
      "results":result[:limit],
      "display_limit":limit,
      "source_scan_capped":bool(capped_sources),
      "capped_source_namespaces":capped_sources,
      "complete_historical_incident_coverage":False,
      "phmsa_primary_incident_census":"NOT_TESTED_ACCESS_BLOCKED",
      "phmsa_enforcement_case_grain":"SEPARATE_NOT_INCLUDED",
      "source_location_vs_site_position":"BOTH_UNVERIFIED_PROPERTY_FOOTPRINTS",
      "verification_required":"Original agency report, legal operator, dated location, physical address/property and independent outcome review",
      "verified_insured_matches":0,
      "verified_losses":0,
      "no_zero_risk_inference":True
    }
