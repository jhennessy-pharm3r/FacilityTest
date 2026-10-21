"""Local underwriting evidence explorer. No login: bind to localhost only."""
from __future__ import annotations
from collections import Counter
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import connect, initialize, one, items, quality_report, source_breakdown
from .match import preview_match

ROOT=Path(__file__).resolve().parent.parent
WEB=ROOT/'web'
app=FastAPI(title='Pharm3r Facility Risk Intelligence',version='0.2.0',
            description='Evidence research prototype; not an actuarially calibrated risk score.')
app.mount('/assets',StaticFiles(directory=WEB),name='assets')


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
    return {'status':'ok','version':'0.2.0','facilities':c.execute('SELECT COUNT(*) FROM facilities').fetchone()[0]}


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
    matches=preview_match(items(c,'SELECT id,name,company,address,fei FROM facilities'),name,address,fei)
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
