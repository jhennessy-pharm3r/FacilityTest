"""Facility evidence explorer. External access requires authentication and TLS proxy."""
from __future__ import annotations
from collections import Counter
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import connect, initialize, one, items, quality_report, source_breakdown
from .match import preview_match
from .intelligence import get_intelligence, intelligence_quality, decide_candidate, review_location, make_underwriting_profile, verify_fei
from .security import add_security
from .advanced_sources import SOURCE_META
from .registry_catalog import init_registry, registry_search
from .source_extensions import catalog as extension_catalog, review_event_candidate
from .fei_api import lookup_fei
from .site_workspace import (SOURCES as REGULATOR_SOURCES, intake_site, search_external_registry,
                             track_external_registry_site, stage_identity_candidate,
                             suggest_regulatory_matches)

ROOT=Path(__file__).resolve().parent.parent
WEB=ROOT/'web'
app=FastAPI(title='Pharm3r Facility Risk Intelligence',version='0.5.0',
            description='Evidence research prototype; not an actuarially calibrated risk score.')
app.mount('/assets',StaticFiles(directory=WEB),name='assets')
add_security(app)


def conn_dependency():
    c=connect()
    initialize(c)
    try:yield c
    finally:c.close()


@app.get('/',include_in_schema=False)
def index():
    return FileResponse(WEB/'index.html')


@app.get('/api/health')
def health(c=Depends(conn_dependency)):
    return {'status':'ok','version':'0.5.0'}


@app.get('/api/overview')
def overview(c=Depends(conn_dependency)):
    q=quality_report(c)
    sites=items(c,'''SELECT f.id,f.name,f.country,f.latitude,f.longitude,f.fei,f.site_case,
         COUNT(e.id) AS evidence_count, COUNT(DISTINCT e.source) AS source_count
         FROM facilities f LEFT JOIN evidence e ON e.facility_id=f.id
         GROUP BY f.id ORDER BY evidence_count DESC''')
    domains=items(c,'''SELECT risk_domain AS name,COUNT(*) AS records,COUNT(DISTINCT facility_id) AS facilities
                       FROM evidence GROUP BY risk_domain ORDER BY records DESC''')
    sources=source_breakdown(c)
    runs=items(c,'SELECT id,source,finished_at,status,imported_count FROM ingestion_runs ORDER BY started_at DESC LIMIT 5')
    latest=items(c,'''SELECT e.id,e.facility_id,f.name AS facility,e.source,e.record_type,
               e.finding,e.date_raw,e.source_url FROM evidence e JOIN facilities f ON f.id=e.facility_id
               WHERE e.source IN ('SEC EDGAR','FDA','Manufacturer')
               ORDER BY e.last_imported DESC, e.date_raw DESC LIMIT 8''')
    return {'stats':q,'facilities':sites,'domains':domains,'sources':sources,
            'latest':latest,'recent_ingestions':runs,'model_status':'evidence review; no loss prediction score'}


@app.post('/api/facilities/intake')
async def facility_intake(request:Request,c=Depends(conn_dependency)):
    if __import__('os').environ.get('FACILITY_RISK_ENABLE_WRITES')!='1':
        raise HTTPException(403,'Manual intake writes are disabled')
    p=await request.json()
    try:return intake_site(c,p,request.state.actor)
    except ValueError as e:raise HTTPException(422,str(e)) from e


@app.get('/api/external-registry/sources')
def regulator_source_catalog(c=Depends(conn_dependency)):
    rows=items(c,'SELECT * FROM external_registry_imports ORDER BY source_key')
    return {'sources':[{'key':key,'name':meta[0],'documentation':meta[1]}
                       for key,meta in REGULATOR_SOURCES.items()],
            'imports':rows,'caveat':'Only locally imported and explicitly sourced datasets are searchable.'}


@app.get('/api/external-registry')
def external_registry(q:str='',country:str='',source_key:str='',
                     limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),
                     c=Depends(conn_dependency)):
    return search_external_registry(c,query=q,country=country,source_key=source_key,limit=limit,offset=offset)


@app.post('/api/external-registry/{external_id}/track')
def external_registry_track(external_id:str,request:Request,c=Depends(conn_dependency)):
    if __import__('os').environ.get('FACILITY_RISK_ENABLE_WRITES')!='1':
        raise HTTPException(403,'Research workspace writes are disabled')
    try:return track_external_registry_site(c,external_id,request.state.actor)
    except ValueError as e:raise HTTPException(404,str(e)) from e


@app.get('/api/facilities/{facility_id}/source-suggestions')
def source_suggestions(facility_id:str,source_key:str='',
                       limit:int=Query(20,ge=1,le=50),c=Depends(conn_dependency)):
    try:
        return suggest_regulatory_matches(c,facility_id,source_key=source_key,limit=limit)
    except ValueError as e:
        if str(e)=='Unknown facility':raise HTTPException(404,str(e)) from e
        raise HTTPException(422,str(e)) from e


@app.post('/api/facilities/{facility_id}/identity-candidates')
async def stage_regulatory_identity(facility_id:str,request:Request,c=Depends(conn_dependency)):
    if __import__('os').environ.get('FACILITY_RISK_ENABLE_WRITES')!='1':
        raise HTTPException(403,'Identity candidate writes are disabled')
    p=await request.json()
    if not isinstance(p,dict):raise HTTPException(422,'Expected identity candidate JSON object')
    try:return stage_identity_candidate(c,facility_id,p.get('external_id',''),request.state.actor)
    except ValueError as e:raise HTTPException(422,str(e)) from e


@app.get('/api/facilities/{facility_id}/event-candidates')
def facility_external_events(facility_id:str,status:str='',limit:int=Query(100,ge=1,le=250),
                             offset:int=Query(0,ge=0),c=Depends(conn_dependency)):
    if not one(c,'SELECT id FROM facilities WHERE id=?',(facility_id,)):
        raise HTTPException(404,'Unknown site')
    where='facility_id=?';args=[facility_id]
    if status:
        if status not in ('pending','reviewed_relevant','rejected'):raise HTTPException(422,'Invalid event review status')
        where+=' AND status=?';args.append(status)
    total=one(c,'SELECT COUNT(*) AS n FROM external_event_candidates WHERE '+where,tuple(args))['n']
    records=items(c,'SELECT * FROM external_event_candidates WHERE '+where+
                  ' ORDER BY imported_at DESC,id LIMIT ? OFFSET ?',tuple(args+[limit,offset]))
    return {'total':total,'items':records,'limit':limit,'offset':offset,
            'caveat':'Nearby records are context candidates, not verified site incidents or insured losses'}


@app.post('/api/external-events/{candidate_id}/review')
async def review_external_event(candidate_id:str,request:Request,c=Depends(conn_dependency)):
    if __import__('os').environ.get('FACILITY_RISK_ENABLE_WRITES')!='1':
        raise HTTPException(403,'Event review writes are disabled')
    p=await request.json()
    if not isinstance(p,dict):raise HTTPException(422,'Expected review JSON object')
    try:return review_event_candidate(c,candidate_id,p.get('decision',''),
                                      request.state.actor,p.get('evidence_url',''),
                                      p.get('reason',''))
    except ValueError as e:raise HTTPException(422,str(e)) from e


@app.get('/api/registry/status')
def registry_status(c=Depends(conn_dependency)):
    init_registry(c)
    info=one(c,"SELECT details_json,checked_at FROM registry_import_meta WHERE source='catalog'")
    return {'records':one(c,'SELECT COUNT(*) AS n FROM registry_facilities')['n'],
            'generated_at':info['checked_at'] if info else None,
            'metadata':__import__('json').loads(info['details_json']) if info else {},
            'coverage':'FDA drug/device registration data, not the entire world facility population'}


@app.get('/api/registry')
def registry(q:str='',country:str='',sector:str='',limit:int=Query(50,ge=1,le=100),
             offset:int=Query(0,ge=0),c=Depends(conn_dependency)):
    # Blank query intentionally browses the complete official source identity
    # catalog, never only the original researched case-study facilities.
    return registry_search(c,q=q[:120],country=country[:8],sector=sector[:50],limit=limit,offset=offset)


@app.get('/api/registry/{registry_id}')
def registry_detail(registry_id:str,c=Depends(conn_dependency)):
    init_registry(c)
    result=one(c,'SELECT * FROM registry_facilities WHERE id=?',(registry_id,))
    if not result: raise HTTPException(404,'Registry establishment not found')
    return result


@app.post('/api/registry/{registry_id}/track')
def track_registry_site(registry_id:str,request:Request,c=Depends(conn_dependency)):
    import os
    from .ingest import utcnow
    from .intelligence import audit
    if os.environ.get('FACILITY_RISK_ENABLE_WRITES')!='1':
        raise HTTPException(403,'Research workspace writes are disabled')
    init_registry(c)
    item=one(c,'SELECT * FROM registry_facilities WHERE id=?',(registry_id,))
    if not item:raise HTTPException(404,'Registry establishment not found')
    fid='registry-'+registry_id
    with c:
        c.execute('''INSERT OR IGNORE INTO facilities(id,name,company,activity,address,country,fei,
                 site_case,research_summary,source_coverage_note,data_gaps,origin,last_imported)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',(
                 fid,item['name'],item['company'],item['activities'],
                 ', '.join(filter(None,[item['address'],item['city'],item['state'],item['country']])),
                 item['country'],item['fei'] or None,'Research requested',
                 'Imported from an FDA registration/listing record; physical site and risk evidence are not yet independently verified.',
                 'FDA registry observation only. No EPA or FDA inspection crosswalk established.',
                 'Risk exposure unknown: site coordinates, construction, flood and fire protection, environmental matching, utilities and business interruption are not assessed.',
                 item['source']+' (catalog; observed)',utcnow()))
        audit(c,'registry_site_tracked',fid,request.state.actor,{'registry_id':registry_id,'source':item['source']})
    return {'facility_id':fid,'status':'tracked_unverified','warning':'Registration is not evidence of physical-site risk or verified coordinates'}


@app.get('/api/facilities')
def facilities(search:str='',country:str='',source:str='',limit:int=Query(100,ge=1,le=500),
               offset:int=Query(0,ge=0),c=Depends(conn_dependency)):
    filters=[];args=[]
    if search:
        filters.append('(f.name LIKE ? OR f.company LIKE ? OR f.address LIKE ? OR f.fei LIKE ?)')
        args+=['%'+search+'%']*4
    if country:
        filters.append('f.country LIKE ?');args.append('%'+country+'%')
    if source:
        filters.append('EXISTS(SELECT 1 FROM evidence ex WHERE ex.facility_id=f.id AND ex.source=?)')
        args.append(source)
    where='WHERE '+' AND '.join(filters) if filters else ''
    total=one(c,f'SELECT COUNT(*) AS n FROM facilities f {where}',tuple(args))['n']
    result=items(c,f'''SELECT f.*,COUNT(e.id) AS evidence_count,COUNT(DISTINCT e.source) AS source_count
          FROM facilities f LEFT JOIN evidence e ON e.facility_id=f.id {where}
          GROUP BY f.id ORDER BY f.name LIMIT ? OFFSET ?''',tuple(args+[limit,offset]))
    return {'items':result,'total':total,'limit':limit,'offset':offset}


@app.get('/api/facilities/{facility_id}')
def facility_detail(facility_id:str,c=Depends(conn_dependency)):
    site=one(c,'SELECT * FROM facilities WHERE id=?',(facility_id,))
    if not site: raise HTTPException(404,'Facility not found')
    domain=items(c,'''SELECT risk_domain AS name,COUNT(*) AS records,COUNT(DISTINCT source) AS sources
             FROM evidence WHERE facility_id=? GROUP BY risk_domain ORDER BY records DESC''',(facility_id,))
    sec=items(c,'SELECT * FROM sec_findings WHERE facility_id=? ORDER BY incident_window',(facility_id,))
    latest=items(c,'''SELECT * FROM evidence WHERE facility_id=?
               ORDER BY CASE WHEN date_raw GLOB '[12][0-9][0-9][0-9]*' THEN date_raw ELSE '' END DESC LIMIT 8''',(facility_id,))
    return {'facility':site,'domains':domain,'sources':source_breakdown(c,facility_id),
            'sec_findings':sec,'latest_evidence':latest,
            'source_snapshots':items(c,'SELECT id,source,url,retrieved_at,notes FROM raw_snapshots WHERE facility_id=? ORDER BY retrieved_at DESC',(facility_id,))}


@app.get('/api/facilities/{facility_id}/evidence')
def site_evidence(facility_id:str,source:str='',domain:str='',search:str='',
                  limit:int=Query(50,ge=1,le=250),offset:int=Query(0,ge=0),c=Depends(conn_dependency)):
    if not one(c,'SELECT id FROM facilities WHERE id=?',(facility_id,)):
        raise HTTPException(404,'Facility not found')
    wh=['facility_id=?'];params=[facility_id]
    if source:wh.append('source=?');params.append(source)
    if domain:wh.append('risk_domain=?');params.append(domain)
    if search:
        wh.append('(finding LIKE ? OR record_type LIKE ? OR record_ref LIKE ? OR program LIKE ?)')
        params.extend(['%'+search+'%']*4)
    where=' AND '.join(wh)
    total=one(c,f'SELECT COUNT(*) AS n FROM evidence WHERE {where}',tuple(params))['n']
    data=items(c,f'''SELECT * FROM evidence WHERE {where}
               ORDER BY CASE WHEN date_raw GLOB '[12][0-9][0-9][0-9]*' THEN date_raw ELSE '' END DESC,
               source,record_type LIMIT ? OFFSET ?''',tuple(params+[limit,offset]))
    return {'items':data,'total':total,'limit':limit,'offset':offset}


@app.get('/api/financial')
def financial(search:str='',c=Depends(conn_dependency)):
    if search:
        data=items(c,'''SELECT * FROM sec_findings WHERE company LIKE ? OR facility_label LIKE ?
          OR finding LIKE ? OR id LIKE ? ORDER BY id''',tuple(['%'+search+'%']*4))
    else:data=items(c,'SELECT * FROM sec_findings ORDER BY id')
    return {'items':data,'total':len(data),
            'caveat':'Multiple filings may describe the same incident; never sum amounts without financial-line reconciliation.'}


@app.get('/api/public-evidence')
def public_evidence(finding_group:str='',c=Depends(conn_dependency)):
    if finding_group:
        data=items(c,'SELECT * FROM public_evidence WHERE related_findings LIKE ? ORDER BY id',(f'%{finding_group}%',))
    else:data=items(c,'SELECT * FROM public_evidence ORDER BY id')
    return {'items':data,'total':len(data),
            'caveat':'A family code matches related public-evidence references; verify individual document linkage.'}


@app.get('/api/sources')
def sources(c=Depends(conn_dependency)):
    data=items(c,'SELECT * FROM sources ORDER BY name')
    coverage={r['source']:r for r in source_breakdown(c)}
    for s in data:
        s['covered_evidence_count']=coverage.get(s['name'],{}).get('records',0)
    return {'items':data,'total':len(data),'observed_source_labels':source_breakdown(c),
            'caveat':'Data-source summaries are analyst documentation; adapter connectivity is a separate state.'}


@app.get('/api/source-extensions')
def source_extensions(c=Depends(conn_dependency)):
    return {'items':extension_catalog(c), 'caveat':'Source status is a documentation or endpoint check only. No incident becomes verified site evidence without review.'}


@app.get('/api/quality')
def quality(c=Depends(conn_dependency)):
    results=quality_report(c)
    results['runs']=items(c,'SELECT * FROM ingestion_runs ORDER BY started_at DESC LIMIT 20')
    results['missing_fei_facilities']=items(c,'SELECT id,name FROM facilities WHERE fei IS NULL')
    results['missing_coordinates_facilities']=items(c,'SELECT id,name FROM facilities WHERE latitude IS NULL OR longitude IS NULL')
    results['unmatched_sec']=items(c,'SELECT id,facility_label,country,attribution FROM sec_findings WHERE facility_id IS NULL ORDER BY id')
    results['future_dated_samples']=items(c,"SELECT id,facility_id,source,record_type,date_raw FROM evidence WHERE date_raw GLOB '[12][0-9][0-9][0-9]-[01][0-9]-[0-3][0-9]' AND date(date_raw)>date('now') ORDER BY date_raw LIMIT 20")
    results['match_quality']=items(c,'SELECT match_quality AS label,COUNT(*) AS records FROM evidence GROUP BY match_quality ORDER BY records DESC LIMIT 18')
    results['source_counts']=source_breakdown(c)
    results['snapshots']=items(c,'SELECT id,source,facility_id,url,retrieved_at,notes FROM raw_snapshots ORDER BY retrieved_at DESC LIMIT 30')
    return results


@app.get('/api/match-preview')
def match_preview(name:str='',address:str='',fei:str='',c=Depends(conn_dependency)):
    if not(name or address or fei): return {'matches':[],'caveat':'Provide at least one identifying field'}
    matches=preview_match(items(c,"""SELECT f.id,f.name,f.company,f.address,f.fei,
        EXISTS(SELECT 1 FROM identity_links l WHERE l.facility_id=f.id
        AND l.namespace='FDA_FEI' AND l.identifier=f.fei AND l.status='verified') AS fei_verified
        FROM facilities f"""),name,address,fei)
    return {'matches':matches,'caveat':'Only exact confirmed FEI permits auto-linking; candidates require physical site review.'}


@app.get('/api/evidence')
def global_evidence(search:str='',source:str='',domain:str='',facility_id:str='',
                    limit:int=Query(50,ge=1,le=250),offset:int=Query(0,ge=0),
                    c=Depends(conn_dependency)):
    filters=[];params=[]
    if search:
        filters.append('(e.finding LIKE ? OR e.record_type LIKE ? OR e.record_ref LIKE ? OR e.program LIKE ? OR f.name LIKE ?)')
        params.extend(['%'+search+'%']*5)
    if source: filters.append('e.source=?');params.append(source)
    if domain: filters.append('e.risk_domain=?');params.append(domain)
    if facility_id: filters.append('e.facility_id=?');params.append(facility_id)
    where='WHERE '+' AND '.join(filters) if filters else ''
    total=one(c,f'SELECT COUNT(*) AS n FROM evidence e JOIN facilities f ON f.id=e.facility_id {where}',tuple(params))['n']
    data=items(c,f'''SELECT e.*,f.name AS facility_name,f.country AS facility_country FROM evidence e
            JOIN facilities f ON f.id=e.facility_id {where}
            ORDER BY e.date_raw DESC,e.source,e.record_type LIMIT ? OFFSET ?''' ,tuple(params+[limit,offset]))
    return {'items':data,'total':total,'limit':limit,'offset':offset}


@app.get('/api/source-fields')
def source_fields(source:str='',c=Depends(conn_dependency)):
    if source:
        data=items(c,'SELECT * FROM field_catalog WHERE source LIKE ? ORDER BY dataset,table_name',('%'+source+'%',))
    else:
        data=items(c,'SELECT * FROM field_catalog ORDER BY source,dataset,table_name')
    return {'items':data,'total':len(data),
            'caveat':'Analyst-compiled schema; must validate against source export versions before production.'}


@app.get('/api/intelligence')
def intelligence(c=Depends(conn_dependency)):
    sites=items(c,"SELECT id,name,country,latitude,longitude,fei FROM facilities ORDER BY name")
    for f in sites:
        f.update(get_intelligence(c,f['id']))
    return {'sites':sites,'quality':intelligence_quality(c),
            'source_health':items(c,'SELECT * FROM source_health ORDER BY source'),
            'source_catalog':[{'source':s,'documentation':meta[0],'test_url':meta[1]} for s,meta in SOURCE_META.items()],
            'caveats':['Analyst FEIs are observed, not independently validated',
               'Site coordinates must be reviewed before flood-zone tests',
               'Historical case studies document outcomes, not prospective loss predictions']}


@app.get('/api/facilities/{facility_id}/intelligence')
def intelligence_site(facility_id:str,c=Depends(conn_dependency)):
    result=get_intelligence(c,facility_id)
    if result is None:raise HTTPException(404,'Unknown facility')
    return result


@app.post('/api/intelligence/candidates/{candidate_id}/review')
async def review_frs_match(candidate_id:str,request:Request,c=Depends(conn_dependency)):
    if __import__('os').environ.get('FACILITY_RISK_ENABLE_WRITES')!='1':
        raise HTTPException(403,'Analyst review writes are disabled')
    p=await request.json()
    try:return decide_candidate(c,candidate_id,p.get('decision',''),request.state.actor,p.get('evidence_url',''),p.get('note',''))
    except ValueError as e:raise HTTPException(422,str(e)) from e


@app.post('/api/facilities/{facility_id}/fei-lookup')
def facility_fda_fei_lookup(facility_id:str,request:Request,c=Depends(conn_dependency)):
    if __import__('os').environ.get('FACILITY_RISK_ENABLE_WRITES')!='1':
        raise HTTPException(403,'FDA FEI lookup is disabled')
    try:
        return lookup_fei(c,facility_id,request.state.actor)
    except ValueError as e:
        message=str(e)
        if message=='Unknown facility':raise HTTPException(404,message) from e
        if 'credentials not configured' in message:raise HTTPException(503,message) from e
        raise HTTPException(422,message) from e
    except __import__('requests').RequestException as e:
        raise HTTPException(502,'FDA FEI lookup failed; source availability not confirmed') from e


@app.post('/api/facilities/{facility_id}/fei-review')
async def facility_fei_review(facility_id:str,request:Request,c=Depends(conn_dependency)):
    if __import__('os').environ.get('FACILITY_RISK_ENABLE_WRITES')!='1':
        raise HTTPException(403,'Analyst review writes are disabled')
    p=await request.json()
    try:return verify_fei(c,facility_id,request.state.actor,p.get('evidence_url',''),p.get('note',''))
    except ValueError as e:raise HTTPException(422,str(e)) from e


@app.post('/api/facilities/{facility_id}/location-review')
async def facility_location_review(facility_id:str,request:Request,c=Depends(conn_dependency)):
    if __import__('os').environ.get('FACILITY_RISK_ENABLE_WRITES')!='1':
        raise HTTPException(403,'Location review writes are disabled')
    p=await request.json()
    try:return review_location(c,facility_id,p.get('precision',''),p.get('evidence_url',''),request.state.actor,p.get('note',''))
    except ValueError as e:raise HTTPException(422,str(e)) from e


@app.post('/api/facilities/{facility_id}/profile')
async def set_facility_profile(facility_id:str,request:Request,c=Depends(conn_dependency)):
    if __import__('os').environ.get('FACILITY_RISK_ENABLE_WRITES')!='1':
        raise HTTPException(403,'Underwriting profile writes are disabled')
    p=await request.json()
    if not one(c,'SELECT id FROM facilities WHERE id=?',(facility_id,)):raise HTTPException(404,'Unknown facility')
    try:make_underwriting_profile(c,facility_id,p.get('sections',{}),actor=request.state.actor,source_scope=p.get('scope','Analyst assessment'),source_url=p.get('source_url',''))
    except ValueError as e:raise HTTPException(422,str(e)) from e
    return {'status':'updated','facility_id':facility_id}