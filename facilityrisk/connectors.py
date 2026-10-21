"""Opt-in real-source adapters; each request leaves raw response provenance.

Network access must be available on the machine running the refresh command.
Do not infer individual insured-property loss from proximity or modeled hazard.
"""
from __future__ import annotations
import csv
import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests
from .db import add_run, complete_run
from .ingest import utcnow, stable_id
from .match import haversine_km

USER_AGENT = 'Pharm3r-FacilityRiskPrototype/0.1 (research; please identify operator contact before production)'
ECHO_DFR = 'https://echodata.epa.gov/echo/dfr_rest_services.get_dfr'
USGS_EVENTS = 'https://earthquake.usgs.gov/fdsnws/event/1/query'
WRI_AQUEDUCT = 'https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/aqueduct_water_risk/FeatureServer/1/query'


class SourceAccessError(RuntimeError):
    pass


def json_get(base: str, params: dict, session=None) -> tuple[str,dict]:
    sess = session or requests.Session()
    req_url = base + '?' + urlencode(params)
    try:
        res=sess.get(base,params=params,headers={'User-Agent':USER_AGENT,'Accept':'application/json'},timeout=25)
        res.raise_for_status()
        data=res.json()
    except (requests.RequestException,ValueError) as exc:
        raise SourceAccessError(f'Cannot retrieve valid JSON from {base}: {exc}') from exc
    if not isinstance(data,dict):
        raise SourceAccessError(f'Unexpected response format from {base}')
    if data.get('error'):
        raise SourceAccessError(f'Source reported an error: {data["error"]}')
    return getattr(res,'url',req_url),data


def archive_raw(conn,source:str,facility_id:str,url:str,payload:dict,notes:str='') -> str:
    sid=stable_id('snapshot',source,facility_id,url,payload)
    conn.execute('''INSERT INTO raw_snapshots(id,source,facility_id,url,retrieved_at,response_json,notes)
        VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET retrieved_at=excluded.retrieved_at''',
        (sid,source,facility_id,url,utcnow(),json.dumps(payload,ensure_ascii=False),notes))
    return sid


def facility(conn,facility_id:str) -> dict:
    row=conn.execute('SELECT * FROM facilities WHERE id=?',(facility_id,)).fetchone()
    if not row: raise ValueError(f'Unknown facility: {facility_id}')
    return dict(row)


def ingest_earthquakes_payload(conn,site:dict,url:str,payload:dict,radius_km:float) -> int:
    """USGS point proximity. NOT a shaking intensity or facility damage estimate."""
    features=payload.get('features')
    if not isinstance(features,list):
        raise ValueError('Invalid USGS GeoJSON: no features')
    count=0
    for event in features:
        props=event.get('properties') or {}
        coords=(event.get('geometry') or {}).get('coordinates') or []
        if len(coords)<2: continue
        lon,lat=coords[:2]
        if not isinstance(lat,(float,int)) or not isinstance(lon,(float,int)): continue
        distance=haversine_km(site['latitude'],site['longitude'],lat,lon)
        if distance>radius_km: continue
        event_id=str(event.get('id') or stable_id(event))
        magnitude=props.get('mag'); mag_text=f'M{magnitude}' if magnitude is not None else 'unknown magnitude'
        millis=props.get('time')
        event_date=datetime.fromtimestamp(millis/1000,timezone.utc).date().isoformat() if isinstance(millis,(float,int)) else ''
        title=str(props.get('title') or 'earthquake')
        evidence_id=stable_id('usgs',site['id'],event_id)
        conn.execute('''INSERT INTO evidence
          (id,facility_id,source,program,date_raw,record_type,finding,value_text,record_ref,
           evidence_scope,match_quality,source_url,limitations,risk_domain,origin,
           availability_date,spatial_distance_km,retrieval_at,last_imported)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(id) DO UPDATE SET finding=excluded.finding,spatial_distance_km=excluded.spatial_distance_km,
          last_imported=excluded.last_imported''',
          (evidence_id,site['id'],'USGS (live)','USGS ComCat GeoJSON',event_date,
           'Regional earthquake, spatial proximity',title,mag_text,event_id,
           'Epicenter near site, not an insured-site impact assessment',
           'Coordinate-derived distance',str(props.get('url') or url),
           f'Epicenter {distance:.1f} km from site point. No measured site shaking, damage, BI or loss established.',
           'Natural hazards','USGS official ComCat API; opt-in live query',None,distance,utcnow(),utcnow()))
        count+=1
    return count


def _require_current_site_point(conn, site, purpose):
    from .intelligence import is_reviewed_site_coordinate
    review=conn.execute('SELECT * FROM location_reviews WHERE facility_id=?',(site['id'],)).fetchone()
    if not is_reviewed_site_coordinate(site,review):
        raise ValueError(purpose+' requires independently reviewed current site coordinates')
    return site


def fetch_usgs(conn,facility_id:str,start:str,end:str,radius_km:float=150,min_magnitude:float=4,session=None)->dict:
    site=_require_current_site_point(conn,facility(conn,facility_id),'USGS geographic screening')
    if not(1<=radius_km<=300):raise ValueError('Radius must be 1 to 300 kilometers')
    if not(0<=min_magnitude<=9.9): raise ValueError('Magnitude out of range')
    params=dict(format='geojson',starttime=start,endtime=end,latitude=site['latitude'],
                longitude=site['longitude'],maxradiuskm=radius_km,minmagnitude=min_magnitude,
                orderby='time',limit=20000)
    url,payload=json_get(USGS_EVENTS,params,session)
    archive_raw(conn,'USGS ComCat',site['id'],url,payload,'USGS event points, not facility losses')
    count=ingest_earthquakes_payload(conn,site,url,payload,radius_km)
    conn.commit()
    return {'source':'USGS','facility':site['name'],'events_within_radius':count,'request_url':url}


def ingest_aqueduct_payload(conn,site:dict,url:str,payload:dict)->int:
    """Use the actual ArcGIS attributes, not model-derived loss assumptions."""
    features=payload.get('features')
    if not isinstance(features,list):raise ValueError('Invalid Aqueduct JSON: no features')
    if not features:return 0
    fields=features[0].get('attributes') or {}
    raw=fields.get('bws_raw');score=fields.get('bws_score');cat=fields.get('bws_cat')
    if raw is None and score is None and cat is None:
        raise ValueError('Aqueduct expected bws_* fields absent; check layer/schema')
    catlabels={0:'Low',1:'Low-medium',2:'Medium-high',3:'High',4:'Extremely high'}
    try: catnum=int(cat) if cat is not None else None
    except (TypeError,ValueError): catnum=None
    description=f'Aqueduct 4.0 baseline water stress; category {catlabels.get(catnum,"unclassified")}'
    value=f'bws_raw={raw}; bws_score={score}; bws_cat={cat}'
    record=fields.get('aqid') or fields.get('pfaf_id') or stable_id(fields)
    eid=stable_id('wri_4.0',site['id'],record)
    conn.execute('''INSERT INTO evidence
      (id,facility_id,source,program,date_raw,record_type,finding,value_text,record_ref,
       evidence_scope,match_quality,source_url,limitations,risk_domain,origin,
       availability_date,spatial_distance_km,retrieval_at,last_imported)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(id) DO UPDATE SET finding=excluded.finding,value_text=excluded.value_text,
      last_imported=excluded.last_imported''',
      (eid,site['id'],'WRI Aqueduct (live)','Aqueduct 4.0 / ArcGIS baseline','Model version: 2023',
       'Modeled regional water stress',description,value,str(record),'Hydrological basin intersection',
       'Coordinate-derived basin',url,
       'Basin screening, not actual water shortage or interruption; coordinates must be site-verified.',
       'Water stress','ArcGIS-hosted Aqueduct 4.0 model; opt-in live query',None,None,utcnow(),utcnow()))
    return 1


def fetch_aqueduct(conn,facility_id:str,session=None)->dict:
    site=_require_current_site_point(conn,facility(conn,facility_id),'WRI Aqueduct basin screening')
    params=dict(f='json',geometry=f"{site['longitude']},{site['latitude']}",
                geometryType='esriGeometryPoint',inSR=4326,
                spatialRel='esriSpatialRelIntersects',outFields='bws_raw,bws_score,bws_cat,aqid,pfaf_id',
                returnGeometry='false')
    url,payload=json_get(WRI_AQUEDUCT,params,session)
    archive_raw(conn,'WRI Aqueduct',site['id'],url,payload,'Point-in-basin modeled stress; not a loss')
    count=ingest_aqueduct_payload(conn,site,url,payload)
    conn.commit()
    return {'source':'WRI Aqueduct','facility':site['name'],'basin_records':count,'request_url':url}


def fetch_echo(conn,facility_id:str,frs_registry_id:str,session=None)->dict:
    """Store original DFR response until a separately tested schema mapping is ready.

    Caller explicitly supplies the verified FRS ID. No name-only auto-linking.
    """
    site=facility(conn,facility_id)
    if not(frs_registry_id.isdigit() and 10<=len(frs_registry_id)<=13):
        raise ValueError('Provide a verified EPA FRS registry ID, not an FEI or name.')
    url,payload=json_get(ECHO_DFR,dict(p_id=frs_registry_id,output='JSON'),session)
    archive_raw(conn,'EPA ECHO DFR',site['id'],url,payload,
                'Source identity supplied by operator; raw response only. Fields not normalized yet.')
    conn.commit()
    return {'source':'EPA ECHO DFR','facility':site['name'],
            'registry_id':frs_registry_id,'raw_snapshot_archived':True,
            'normalized_risk_records':0,'request_url':url}


def ingest_noaa_csv(conn,path:str|Path,radius_km:float=40)->dict:
    """Quarantine NOAA proximity reports instead of attaching them as site evidence.

    Only independently reviewed current physical points participate. Source
    file checksum, NOAA event ID and measured proximity remain available in
    the review queue; this never asserts loss at an insured property.
    """
    import gzip
    from .source_extensions import _file_hash,_site_spatial_grid,_nearby_grid_sites
    if not (1 <= radius_km <= 100):raise ValueError('Radius must be 1-100 km')
    path=Path(path)
    if not path.is_file():raise ValueError('NOAA source file not found')
    sites=[dict(row) for row in conn.execute("""
      SELECT f.id,f.latitude,f.longitude FROM facilities f
      JOIN location_reviews l ON l.facility_id=f.id
      WHERE l.precision IN ('site_verified','property_polygon')
        AND l.reviewed_latitude=f.latitude AND l.reviewed_longitude=f.longitude
        AND f.latitude BETWEEN -90 AND 90 AND f.longitude BETWEEN -180 AND 180
    """)]
    if not sites:raise ValueError('No independently reviewed site coordinates; NOAA matches blocked')
    grid=_site_spatial_grid(sites)
    sha=_file_hash(path)
    totals=dict(rows_seen=0,rows_without_coordinates=0,records_near_site=0,
                new_candidates=0,facilities_with_points=len(sites),source_sha256=sha,
                disposition='pending_review_not_evidence')
    opener=gzip.open if str(path).lower().endswith('.gz') else open
    try:
        with opener(path,'rt',encoding='utf-8-sig',errors='replace',newline='') as handle:
            reader=csv.DictReader(handle)
            needed={'EVENT_ID','EVENT_TYPE','BEGIN_LAT','BEGIN_LON'}
            if not needed.issubset(set(reader.fieldnames or [])):
                raise ValueError('NOAA CSV lacks Storm Events Details required columns')
            for event in reader:
                totals['rows_seen']+=1
                eid=str(event.get('EVENT_ID') or '').strip()
                if not eid:continue
                try:
                    lat=float(event.get('BEGIN_LAT') or 'nan')
                    lon=float(event.get('BEGIN_LON') or 'nan')
                except (TypeError,ValueError):
                    totals['rows_without_coordinates']+=1
                    continue
                if not (math.isfinite(lat) and math.isfinite(lon) and
                        -90<=lat<=90 and -180<=lon<=180):
                    totals['rows_without_coordinates']+=1
                    continue
                for site in _nearby_grid_sites(grid,lat,lon,radius_km):
                    distance=haversine_km(site['latitude'],site['longitude'],lat,lon)
                    if distance>radius_km:continue
                    totals['records_near_site']+=1
                    url=('https://www.ncei.noaa.gov/stormevents/eventdetails.jsp?id='+eid
                         if eid.isdigit() else 'https://www.ncei.noaa.gov/stormevents/')
                    candidate_id=stable_id('noaa_candidate',site['id'],eid)
                    result=conn.execute("""INSERT OR IGNORE INTO external_event_candidates
                      (id,facility_id,source_key,source_record_id,event_date,title,source_url,
                       latitude,longitude,distance_km,geo_precision,provenance_sha256,imported_at)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (candidate_id,site['id'],'noaa',eid,
                       str(event.get('BEGIN_DATE_TIME') or '')[:60],
                       str(event.get('EVENT_TYPE') or 'Weather event')[:1200],
                       url,lat,lon,distance,
                       'NOAA approximate begin coordinate; no site impact asserted',
                       sha,utcnow()))
                    totals['new_candidates']+=max(0,result.rowcount)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return totals
