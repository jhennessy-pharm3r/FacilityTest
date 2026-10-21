"""Source-backed, opt-in ingestion. All network requests are server-side.

No online result is represented as a validated property loss. FEMA screening
requires a reviewed site point; FRS only creates manual-review candidates.
"""
from __future__ import annotations
import csv
import json
import os
import re
from pathlib import Path
from .connectors import json_get, archive_raw, facility, SourceAccessError
from .ingest import stable_id,utcnow
from .intelligence import register_frs_candidates,assess_fema_payload,store_hazard

FRS_URL='https://ofmpub.epa.gov/frs_public2/frs_rest_services.get_facilities'
FEMA_URL='https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query'
FEMA_ALT_URL='https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer/28/query'
SOURCE_META={
 'EPA FRS':('https://www.epa.gov/frs/frs-api','https://ofmpub.epa.gov/frs_public2/frs_rest_services.get_facilities?facility_name=pfizer&state_abbr=NC&output=JSON'),
 'EPA ECHO':('https://echo.epa.gov/tools/web-services','https://echodata.epa.gov/echo/dfr_rest_services.get_dfr?p_id=110015778176&output=JSON'),
 'USGS':('https://earthquake.usgs.gov/fdsnws/event/1/','https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&starttime=2024-01-01&endtime=2024-01-02&minmagnitude=6'),
 'FEMA NFHL':('https://www.fema.gov/flood-maps/national-flood-hazard-layer','https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28?f=json'),
 'WRI Aqueduct':('https://www.wri.org/aqueduct','https://services.arcgis.com/P3ePLMYs2RVChkJx/arcgis/rest/services/aqueduct_water_risk/FeatureServer/1?f=json'),
 'FDA inspections':('https://www.fda.gov/about-fda/performance-data/fda-data-dashboard',None),
 'NOAA storm events':('https://www.ncei.noaa.gov/access/storm-events-database/',None)
}


def records_from_frs(payload):
    """Supports EPA's documented RegistryId/FacilityName, several JSON wrappers.

    Raises on unexplained schema; returning zero for a parse failure would
    otherwise look like no candidates.
    """
    rows=[]
    def walk(node):
        if isinstance(node,list):
            for it in node:walk(it)
        elif isinstance(node,dict):
            if 'RegistryId' in node:
                rid=str(node['RegistryId'] or '').strip()
                if rid.isdigit():
                    def fnum(v):
                        try:return float(v) if v not in ('',None) else None
                        except (ValueError,TypeError):return None
                    rows.append({'registry_id':rid,'name':node.get('FacilityName') or '',
                     'address':', '.join(str(node.get(k,'')) for k in ('LocationAddress','CityName','StateAbbr') if node.get(k)),
                     'latitude':fnum(node.get('Latitude83')),'longitude':fnum(node.get('Longitude83'))})
                return
            for key,value in node.items():
                if key not in ('ProgramFacilities','ProgramFacility','ProgramCoordinates'):
                    walk(value)
    walk(payload)
    unique={r['registry_id']:r for r in rows}
    if not unique:
        s=json.dumps(payload)[:350]
        # Explicit "no matches" may be legitimate; schema structure still retained.
        if re.search(r'no (records|facilit|match|results) (found|returned)|no facilities',s,re.I):return []
        if 'Results' in payload and (payload['Results']==[] or payload['Results']=={}):return []
        raise ValueError('Unrecognized EPA FRS schema or empty result; inspect raw snapshot')
    return list(unique.values())


def discover_frs(conn,facility_id,name,state,session=None):
    if len(name.strip())<4 or not re.fullmatch(r'[A-Za-z]{2}',state):
        raise ValueError('Require at least four name characters and a two-letter state')
    facility(conn,facility_id)
    params={'facility_name':name.strip(),'state_abbr':state.upper(),'output':'JSON','program_output':'yes'}
    url,payload=json_get(FRS_URL,params,session)
    archive_raw(conn,'EPA FRS candidates',facility_id,url,payload,'Candidate lookup; no automatic FEI↔FRS crosswalk')
    matches=records_from_frs(payload)
    added=register_frs_candidates(conn,facility_id,matches,url)
    return {'facility_id':facility_id,'candidate_count':added,'request_url':url,
            'notice':'Candidates require manual identity corroboration before use in ECHO.'}


def fetch_verified_echo(conn,facility_id,session=None):
    row=conn.execute("SELECT identifier FROM identity_links WHERE facility_id=? AND namespace='EPA_FRS' AND status='verified'",(facility_id,)).fetchone()
    if not row:raise ValueError('Cannot fetch ECHO without verified FRS match')
    from .connectors import fetch_echo
    return fetch_echo(conn,facility_id,row['identifier'],session=session)


def fetch_fema(conn,facility_id,session=None):
    """Regulatory flood-zone screening, not historical 2024 flood forecast.

    A successful no-feature result is *not mapped*, not safe. FEMA mapped
    Zone X is also not proof of zero residual flood risk.
    """
    site=facility(conn,facility_id)
    from .intelligence import is_reviewed_site_coordinate
    loc=conn.execute('SELECT * FROM location_reviews WHERE facility_id=?',(facility_id,)).fetchone()
    if not is_reviewed_site_coordinate(site,loc):
        raise ValueError('FEMA screening blocked: site coordinates have not been manually verified for the current point')
    lat,lon=site['latitude'],site['longitude']
    if lat is None or lon is None:raise ValueError('Missing property coordinates')
    # FEMA NFHL only for US sites and territories; international sites not eligible.
    country=(site['country'] or '').lower()
    if not any(x in country for x in ('united states','puerto rico')):
        raise ValueError('FEMA NFHL is US/territories only')
    params={'f':'json','geometry':f'{lon},{lat}','geometryType':'esriGeometryPoint',
            'inSR':4326,'spatialRel':'esriSpatialRelIntersects',
            'outFields':'FLD_ZONE,SFHA_TF,ZONE_SUBTY,DFIRM_ID,EFF_DATE',
            'returnGeometry':'false'}
    try:url,payload=json_get(FEMA_URL,params,session)
    except SourceAccessError:
        # FEMA exposes both ArcGIS and legacy GIS/NFHL paths; try only its official host.
        url,payload=json_get(FEMA_ALT_URL,params,session)
    archive_raw(conn,'FEMA NFHL',facility_id,url,payload,'Current regulatory flood-zone map; not historical condition at incident date')
    status,desc,zone=assess_fema_payload(payload)
    store_hazard(conn,facility_id,'Flood zone',status,'FEMA NFHL',desc,url,zone,
                 'reviewed_site_coordinate','',
                 'NFHL zone is regulatory mapping, not building-level inundation probability; verify effective vintage and survey.')
    return {'facility_id':facility_id,'status':status,'zone':zone,'request_url':url}


def ingest_fda_inspections_csv(conn,path):
    """Use authorized FDA Inspection Database CSV export; never guess FEIs.

    Schema drift reported as an error rather than silently skipping records.
    """
    path=Path(path)
    def key(v):return re.sub(r'[^a-z0-9]','',str(v).lower())
    with path.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        if not reader.fieldnames:raise ValueError('Missing FDA CSV header')
        names={key(n):n for n in reader.fieldnames}
        def col(*possibles):
            for p in possibles:
                if key(p) in names:return names[key(p)]
            raise ValueError('FDA CSV missing required field: '+str(possibles))
        fei_col=col('FEI Number','FEI','FEI #','FEI_NUM')
        date_col=col('Inspection End Date','End Date','Inspection Date','Inspection EndDate')
        cls_col=col('Classification','Final Classification','Inspection Classification')
        extra_col=names.get('firmname') or names.get('companyname')
        sites={str(x['fei']):x for x in conn.execute("SELECT id,fei FROM facilities WHERE fei IS NOT NULL")}
        linked=0;skipped=0
        for r in reader:
            fei=str(r.get(fei_col,'')).strip()
            if fei not in sites:skipped+=1;continue
            date=str(r.get(date_col,'')).strip()
            classif=str(r.get(cls_col,'')).strip()
            if not date or not classif:skipped+=1;continue
            fid=sites[fei]['id']
            eid=stable_id('fda_inspection_csv',fid,fei,date,classif)
            conn.execute('''INSERT OR IGNORE INTO evidence
            (id,facility_id,source,program,date_raw,record_type,finding,record_ref,evidence_scope,
             match_quality,source_url,limitations,risk_domain,origin,last_imported)
             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (eid,fid,'FDA inspections (CSV)','FDA Data Dashboard',date,'Inspection final classification',
             f'FDA listed inspection final classification: {classif}',fei,'FEI-specific inspection',
             'FEI exact match to analyst registry, not verified independent FEI registry',
             'https://www.fda.gov/about-fda/performance-data/fda-data-dashboard',
             'FDA inspections reflect regulatory assessments; classifications not proof of insured property damage.',
             'Manufacturing regulation','FDA public inspection CSV (user-provided)',utcnow()))
            linked+=1
    conn.commit()
    return {'linked':linked,'unmatched_or_incomplete':skipped,
            'caveat':'Requires official FDA export and verified FEI identity before production rating'}


def record_source_check(conn,source,state,url,details='',count=None):
    conn.execute('''INSERT INTO source_health(source,state,checked_at,url,item_count,details)
    VALUES(?,?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET state=excluded.state,
    checked_at=excluded.checked_at,url=excluded.url,item_count=excluded.item_count,
    details=excluded.details''',(source,state,utcnow(),url,count,details[:600]))
    conn.commit()


def source_probe(conn=None,session=None):
    """Public endpoint HTTP/JSON sanity; no insured-site IDs or personal data.

    A 200 response is a connectivity check, not proof the requested source
    payload is usable or current. Individual record ingest requires follow-up.
    """
    import requests
    sess=session or requests.Session()
    results=[]
    for source,(docs,url) in SOURCE_META.items():
        if not url:
            state='requires_file';detail='Manual/scheduled official dataset export'
        else:
            probe_url=url
            try:
                resp=sess.get(probe_url,timeout=18,headers={'User-Agent':'FacilityRisk-Source-Health/0.4','Accept':'application/json'})
                resp.raise_for_status()
                sample=resp.json()
                if not isinstance(sample,(dict,list)):raise ValueError('Unexpected JSON payload')
                if isinstance(sample,dict) and sample.get('error'):raise ValueError('Upstream JSON error: '+str(sample['error'])[:120])
                state='reachable';detail=f'HTTP {resp.status_code}; JSON response parsed; schema and facility matches not verified'
            except Exception as e:
                state='failed';detail=str(e)[:320]
                if source=='FEMA NFHL':
                    probe_url=FEMA_ALT_URL.rsplit('/28/query',1)[0]+'/28?f=json'
                    try:
                        alt=sess.get(probe_url,timeout=18,headers={'User-Agent':'FacilityRisk-Source-Health/0.4','Accept':'application/json'})
                        alt.raise_for_status()
                        obj=alt.json()
                        if not isinstance(obj,dict) or obj.get('error'):
                            raise ValueError('Invalid FEMA alternate metadata')
                        state='reachable';detail='Official alternate FEMA NFHL endpoint reachable; layer metadata parsed, site query not verified'
                    except Exception as e2:
                        detail=('Primary: '+str(e)[:140]+'; alternate: '+str(e2)[:140])[:320]
        out={'source':source,'state':state,'url':(probe_url if source=='FEMA NFHL' else url) or docs,'details':detail}
        if conn:record_source_check(conn,source,state,out['url'],detail)
        results.append(out)
    return results