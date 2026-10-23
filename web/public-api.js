/* Browser-only read-only data adapter for GitHub Pages.
   Research snapshots are loaded into memory: never uploaded, persisted, or sent to a service. */
(() => {
  'use strict';
  const script = document.getElementById('public-api-script');
  const seedUrl = new URL('./public-demo.json', script?.src || document.baseURI);
  const statusUrl = new URL('./source-status.json', script?.src || document.baseURI);
  const noaaStatusUrl = new URL('./ingestion/noaa-storm-events.json', script?.src || document.baseURI);
  let statusPromise = null;
  function fetchOptionalJson(url) {
    return fetch(url, {cache:'no-store'}).then(r => r.ok?r.json():null).catch(()=>null);
  }
  function getStatus() {
    if (!statusPromise) {
      statusPromise = Promise.all([fetchOptionalJson(statusUrl), fetchOptionalJson(noaaStatusUrl)])
        .then(([base, noaa]) => {
          if (!base || base.schema_version !== '1.0') return null;
          if (noaa?.schema_version !== '1.0' || noaa?.source !== 'NOAA Storm Events Details' ||
              noaa?.state !== 'staged_source_artifact' || !Number.isSafeInteger(noaa.records) || noaa.records < 1) {
            return base;
          }
          const existing = (base.ingestions||[]).filter(x => x.source !== noaa.source);
          const vetted = {source:noaa.source, state:noaa.state, records:noaa.records,
            checked_at:noaa.checked_at, scope:noaa.scope, details:noaa.details,
            documentation:noaa.documentation, artifact_run_url:noaa.artifact_run_url};
          return {...base, ingestions:[...existing,vetted]};
        });
    }
    return statusPromise;
  }
  const extendedCatalog = [["USCG National Response Center","High","Chemical spills and releases","https://nrc.uscg.mil/"],["U.S. Chemical Safety Board","High","Investigated process accidents","https://www.csb.gov/investigations/"],["NERIS Public Incident Basics","High","Current fire response reports","https://www.usfa.fema.gov/neris/public/"],["NFIRS historical fire incidents","High","Historical fire reports","https://www.usfa.fema.gov/data-insights/nfirs/data/"],["FDA inspections and compliance","High","FEI-scoped regulatory inspections","https://www.fda.gov/about-fda/performance-data/fda-data-dashboard"],["WRI Aqueduct Floods","High","Modeled inundation hazard","https://datasets.wri.org/datasets/aqueduct-floods-hazard-maps"],["EIA-861 Electricity Reliability","High","Utility SAIDI/SAIFI averages","https://www.eia.gov/electricity/data/eia861/"],["Ireland EPA LEAP","High","Irish licensed facility compliance","https://data.epa.ie/api-list/leap-open-data/"],["European Industrial Emissions Portal","Medium-High","European facility emissions","https://industry.eea.europa.eu/industrial-emissions/dataset"],["Canada National Pollutant Release Inventory","Medium-High","Canadian facility pollutant releases","https://open.canada.ca/data/en/dataset/40e01423-7728-429c-ac9d-2954385ccdfb"],["EPA Risk-Screening Environmental Indicators","Medium","Relative modeled pollution impact","https://www.epa.gov/rsei"],["USFS Wildfire Risk to Communities","Medium","Regional wildfire hazard","https://wildfirerisk.org/download/"],["UCDP Georeferenced Event Dataset","Medium","Conflict events and location precision","https://ucdp.uu.se/downloads/"],["PHMSA Hazmat Transportation Incidents","Medium","Transport disruption events","https://www.phmsa.dot.gov/hazmat-program-management-data-and-statistics/data-operations/incident-statistics"]] .map(([name,priority,category,documentation]) => ({name,priority,category,documentation,probe_state:'not_published',checked_at:null,access:'See official source for file/API access',test:'Site attribution, temporal evidence and dataset licensing require backend review.',limitation:'This public preview does not execute live source tests or contain private incident matches.',staged_candidates:0}));
  const MAX_FILE_BYTES = 20 * 1024 * 1024;
  let dataPromise = null;
  let datasetLabel = 'Public examples';

  function assertDataset(obj) {
    if (!obj || typeof obj !== 'object' || obj.schema_version !== '1.0') throw new Error('Unsupported snapshot schema (expected 1.0).');
    for (const k of ['facilities','evidence','sec_findings','sources']) {
      if (!Array.isArray(obj[k])) throw new Error('Missing required array: ' + k);
    }
    if (obj.facilities.length > 15000 || obj.evidence.length > 100000 || obj.sec_findings.length > 50000 || obj.sources.length > 2000) {
      throw new Error('Snapshot too large for this browser preview.');
    }
    const ids = new Set();
    for (const f of obj.facilities) {
      if (!f || typeof f.id !== 'string' || !f.id.trim() || ids.has(f.id)) throw new Error('Duplicate or missing facility identifier.');
      ids.add(f.id);
    }
    for (const e of obj.evidence) {
      if (!e || typeof e.facility_id !== 'string' || !ids.has(e.facility_id)) throw new Error('Orphan evidence record in snapshot.');
    }
    return obj;
  }
  function getData() {
    if (!dataPromise) {
      dataPromise = fetch(seedUrl, {cache:'no-store'}).then(r => {
        if (!r.ok) throw new Error('Public demonstration data could not be loaded (HTTP ' + r.status + ').');
        return r.json();
      }).then(assertDataset);
    }
    return dataPromise;
  }
  const values = (o,k) => String(o?.[k] ?? '').toLowerCase();
  function breakdown(rows) {
    const map = new Map();
    for (const e of rows) {
      const k=e.source||'Unclassified';
      if(!map.has(k)) map.set(k,{source:k,records:0,programs:0,linked:0,_programs:new Set()});
      const x=map.get(k); x.records++; if(/^https?:\/\//i.test(e.source_url||'')) x.linked++; x._programs.add(e.program||'');
    }
    return [...map.values()].map(x=>({source:x.source,records:x.records,programs:x._programs.size,linked:x.linked})).sort((a,b)=>b.records-a.records);
  }
  function domains(rows) {
    const map=new Map();
    for(const e of rows){const k=e.risk_domain||'Unclassified';if(!map.has(k))map.set(k,{name:k,records:0,_sites:new Set(),_sources:new Set()});const x=map.get(k);x.records++;x._sites.add(e.facility_id);x._sources.add(e.source);}
    return [...map.values()].map(x=>({name:x.name,records:x.records,facilities:x._sites.size,sources:x._sources.size})).sort((a,b)=>b.records-a.records);
  }
  function counts(d) {
    const facilities=d.facilities.length, ev=d.evidence.length, sec=d.sec_findings.length;
    const withFei=d.facilities.filter(x=>x.fei).length;
    const geo=d.facilities.filter(x=>x.latitude!=null&&x.longitude!=null).length;
    const urls=d.evidence.filter(x=>/^https?:\/\//i.test(x.source_url||'')).length;
    const dates=d.evidence.filter(x=>x.availability_date).length;
    const future=d.evidence.filter(x=>/^\d{4}-\d\d-\d\d$/.test(x.date_raw||'') && x.date_raw>new Date().toISOString().slice(0,10));
    const ids=new Set(), feis=new Set(), integrity=[];
    for(const f of d.facilities){if(ids.has(f.id))integrity.push('Duplicate ID '+f.id);ids.add(f.id);if(f.fei){if(feis.has(f.fei))integrity.push('Duplicate FEI '+f.fei);feis.add(f.fei);}if((f.latitude==null)!=(f.longitude==null))integrity.push('Partial coordinate '+f.id);if(f.latitude!=null&&(!(-90<=f.latitude&&f.latitude<=90)||!(-180<=f.longitude&&f.longitude<=180)))integrity.push('Invalid coordinates '+f.id);}
    for(const e of d.evidence){if(!ids.has(e.facility_id)) integrity.push('Orphan '+e.id);}
    return {facilities,evidence:ev,sec_findings:sec,public_references:0,geo_matched:geo,with_fei:withFei,evidence_with_url:urls,
      unmatched_sec_findings:d.sec_findings.filter(x=>!x.facility_id).length,evidence_with_verified_publication_date:dates,
      future_dated_evidence:future.length,sources:d.sources.length,snapshots:0,integrity_failures:integrity,
      missing_fei_facilities:d.facilities.filter(x=>!x.fei).map(x=>({id:x.id,name:x.name})),
      missing_coordinates_facilities:d.facilities.filter(x=>x.latitude==null||x.longitude==null).map(x=>({id:x.id,name:x.name})),
      unmatched_sec:d.sec_findings.filter(x=>!x.facility_id).map(x=>({id:x.id,facility_label:x.facility_label,country:x.country,attribution:x.attribution})),
      future_dated_samples:future.slice(0,20).map(x=>({id:x.id,facility_id:x.facility_id,source:x.source,record_type:x.record_type,date_raw:x.date_raw})),
      match_quality:[...new Map(d.evidence.map(e=>[e.match_quality||'Unknown',0])).keys()].map(label=>({label,records:d.evidence.filter(x=>(x.match_quality||'Unknown')===label).length})),
      runs:d.ingestions||[],source_counts:breakdown(d.evidence),snapshots:[],
      important_caveats:d.important_caveats||['Research data is not an insurance rating, claim register or predictive score.']
    };
  }
  function facilityList(d) {
    return d.facilities.map(f=>{
      const rows=d.evidence.filter(e=>e.facility_id===f.id);
      return {...f,evidence_count:rows.length,source_count:new Set(rows.map(x=>x.source)).size,covered_sources:[...new Set(rows.map(x=>x.source))]};
    });
  }
  function evidenceList(d,params,siteId) {
    let rows=d.evidence.filter(e=>!siteId||e.facility_id===siteId);
    const s=(params.get('search')||'').toLowerCase(),source=params.get('source')||'',domain=params.get('domain')||'';
    if(source)rows=rows.filter(e=>e.source===source);
    if(domain)rows=rows.filter(e=>e.risk_domain===domain);
    if(s)rows=rows.filter(e=>[e.finding,e.record_type,e.record_ref,e.program,e.facility_id].some(x=>String(x||'').toLowerCase().includes(s)));
    rows=rows.map(e=>({...e,facility_name:d.facilities.find(f=>f.id===e.facility_id)?.name||'Unidentified'}));
    rows.sort((a,b)=>String(b.date_raw||'').localeCompare(String(a.date_raw||''))||String(a.source).localeCompare(String(b.source)));
    const limit=Math.min(250,Math.max(1,Number(params.get('limit'))||50)); const offset=Math.max(0,Number(params.get('offset'))||0);
    return {items:rows.slice(offset,offset+limit),total:rows.length,limit,offset};
  }
  async function query(path) {
    const d=await getData();const u=new URL('https://local.test/api/'+path.replace(/^\//,''));const p=u.searchParams;const r=u.pathname.slice('/api/'.length),parts=r.split('/');
    if (r==='intelligence'){
      const snapshot = await getStatus();
      const intel = d.intelligence || {
      sites:d.facilities.map(f=>({...f,identifiers:f.fei?[{namespace:'FDA_FEI',identifier:f.fei,status:'observed',provenance_note:'Research identifier not independently verified'}]:[],
        candidates:[],location:{precision:(f.coordinate_precision||'').includes('City')?'city':'approximate'},hazard_checks:[],incidents:[],profile:null})),
      quality:{verified_frs_links:0,frs_candidates_pending:0,verified_site_locations:0,historical_incidents:0,hazard_screenings:0,profiles:0,live_source_checks:0},
      source_health:[],source_catalog:[]};
      if (!snapshot || snapshot.schema_version !== '1.0') return intel;
      return {...intel, source_health:snapshot.checks||[], source_catalog:(snapshot.checks||[]).map(x=>({source:x.source,documentation:x.documentation})), public_status_generated_at:snapshot.generated_at, ingestions:snapshot.ingestions||[], source_run_url:snapshot.run_url};
    }
    if (r==='source-extensions'){
      const snapshot = await getStatus();
      const checks = new Map((snapshot?.extended_checks||[]).map(x=>[x.source,x]));
      return {items:extendedCatalog.map(x=>({...x,probe_state:checks.get(x.name)?.state||'not_published',checked_at:checks.get(x.name)?.checked_at||null,probe_details:checks.get(x.name)?.details||'No published connectivity report'})),caveat:'Public metadata reports documentation/connectivity only, not facility-level ingestion or validated matches.'};
    }
    if (r==='health')return {status:'static_preview',version:'0.3.0',facilities:d.facilities.length};
    if (r==='overview') {
      const fl=facilityList(d),siteRows=[...fl].sort((a,b)=>b.evidence_count-a.evidence_count);
      return {stats:counts(d),facilities:siteRows.map(f=>({id:f.id,name:f.name,country:f.country,latitude:f.latitude,longitude:f.longitude,fei:f.fei,site_case:f.site_case,evidence_count:f.evidence_count,source_count:f.source_count})),
        domains:domains(d.evidence),sources:breakdown(d.evidence),latest:[...d.evidence].slice(0,8),recent_ingestions:d.ingestions||[],model_status:'Public preview; no calibrated loss prediction'};
    }
    if (r==='facilities') {
      let rows=facilityList(d);const s=(p.get('search')||'').toLowerCase(),country=p.get('country')||'',source=p.get('source')||'';
      if(s)rows=rows.filter(f=>[f.name,f.company,f.address,f.fei].some(v=>String(v||'').toLowerCase().includes(s)));
      if(country)rows=rows.filter(f=>f.country.includes(country));if(source)rows=rows.filter(f=>f.covered_sources.includes(source));
      rows.sort((a,b)=>a.name.localeCompare(b.name));const limit=Math.min(500,Math.max(1,Number(p.get('limit'))||100)),offset=Math.max(0,Number(p.get('offset'))||0);
      return {items:rows.slice(offset,offset+limit),total:rows.length,limit,offset};
    }
    if(parts[0]==='facilities'&&parts.length>=2){const id=decodeURIComponent(parts[1]);const site=d.facilities.find(x=>x.id===id);if(!site)throw new Error('Facility not found');
      const siteRows=d.evidence.filter(e=>e.facility_id===id);
      if(parts[2]==='intelligence'){
        const stored=d.intelligence?.sites?.find(x=>x.id===id);
        return stored||{facility_id:id,identifiers:site.fei?[{namespace:'FDA_FEI',identifier:site.fei,status:'observed',provenance_note:'Analyst-reported FEI; not independently verified'}]:[],
          candidates:[],location:{precision:'city',note:'Public reference coordinate only'},hazard_checks:[],incidents:[],profile:null};
      }
      if(parts[2]==='evidence')return evidenceList(d,p,id);
      return {facility:site,domains:domains(siteRows),sources:breakdown(siteRows),sec_findings:d.sec_findings.filter(x=>x.facility_id===id),
        latest_evidence:evidenceList(d,new URLSearchParams({limit:'8'}),id).items,source_snapshots:[]};
    }
    if(r==='evidence')return evidenceList(d,p);
    if(r==='financial')return {items:d.sec_findings,total:d.sec_findings.length,caveat:'Do not add disclosed financial figures across reporting periods.'};
    if(r==='sources'){const cov=new Map(breakdown(d.evidence).map(s=>[s.source,s.records]));return {items:d.sources.map(s=>({...s,covered_evidence_count:cov.get(s.name)||0})),total:d.sources.length,observed_source_labels:breakdown(d.evidence),caveat:'Listed public sources are not live synced on GitHub Pages.'};}
    if(r==='quality')return counts(d);
    if(r==='public-evidence')return {items:[],total:0,caveat:'Not included in static preview'};
    if(r==='source-fields')return {items:[],total:0};
    throw new Error('Unknown public preview route: '+r);
  }
  async function addFacility(item) {
    const d=await getData();
    if(!item || !item.id || !item.name)throw new Error('Facility identity fields are required');
    const id='research-'+String(item.id).replace(/[^a-zA-Z0-9_-]/g,'-').slice(0,90);
    if(d.facilities.some(f=>f.id===id))return id;
    if(d.facilities.length>=15000)throw new Error('This browser research workspace reached its maximum size');
    d.facilities.push({id,name:String(item.name).slice(0,160),company:String(item.company||item.name).slice(0,160),
      country:String(item.country||'Unknown'),address:[item.address,item.city,item.state,item.country].filter(Boolean).join(', ').slice(0,400),
      fei:item.fei||null,latitude:null,longitude:null,activity:item.activities||'Not assessed',site_case:'New unverified research request',
      research_summary:'FDA/public registry entry or manual request. Facility match and risk indicators have NOT been validated.',
      data_gaps:'No property geocode, verified environmental crosswalk, insurance values or site-specific hazard screening. Unknown is not low risk.',
      origin:item.source||'Manual unsourced research request'});
    datasetLabel=datasetLabel==='Public examples'?'Public examples + browser research entries':datasetLabel;
    refreshMetadata();
    window.dispatchEvent(new Event('facilityrisk:dataset-changed'));
    return id;
  }
  function refreshMetadata() {
    const label=document.getElementById('public-data-label');if(label)label.textContent=datasetLabel;
    const reset=document.getElementById('public-data-reset');if(reset)reset.hidden=datasetLabel==='Public examples';
  }
  async function importFile(file){
    if(!file) return;
    if(file.size>MAX_FILE_BYTES)throw new Error('Snapshot exceeds the 20 MB browser import limit.');
    const parsed=assertDataset(JSON.parse(await file.text()));
    dataPromise=Promise.resolve(parsed); datasetLabel='Local browser snapshot: '+(parsed.dataset_label||file.name);
    refreshMetadata();window.dispatchEvent(new Event('facilityrisk:dataset-changed'));
  }
  function reset(){dataPromise=null;datasetLabel='Public examples';refreshMetadata();window.dispatchEvent(new Event('facilityrisk:dataset-changed'));}
  function initControls(){
    const chooser=document.getElementById('public-data-file');
    const trigger=document.getElementById('public-data-import');
    const resetBtn=document.getElementById('public-data-reset');
    if(trigger&&chooser){trigger.addEventListener('click',()=>chooser.click());chooser.addEventListener('change',async()=>{try{await importFile(chooser.files?.[0]);}catch(err){alert('Snapshot import failed: '+err.message);}finally{chooser.value='';}});}
    if(resetBtn)resetBtn.addEventListener('click',reset);
    refreshMetadata();
  }
  window.PublicRiskAPI={query,importFile,reset,getData,assertDataset,addFacility};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',initControls);else initControls();
})();