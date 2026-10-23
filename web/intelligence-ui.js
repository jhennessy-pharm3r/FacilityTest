/* Read-only underwriting and incident research panels. No simulated hazards or insured-loss scores. */
(() => {
  'use strict';
  const $ = (s,root=document) => root.querySelector(s);
  const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const safeLink = (url,label='Primary source') => {
    try {const x=new URL(url);return ['http:','https:'].includes(x.protocol)?`<a target="_blank" rel="noopener noreferrer" href="${esc(x.href)}">${esc(label)} ↗</a>`:'';}catch{return '';}
  };
  const css = (s) => esc(s);
  let casesPromise=null, map=null;
  const sourceUrl = new URL('./case-studies.json',document.currentScript?.src||document.baseURI);
  const heading = (eyebrow,title,desc) => `<div class="page-heading"><div><div class="eyebrow">${esc(eyebrow)}</div><h1>${esc(title)}</h1><p class="subhead">${esc(desc)}</p></div></div>`;
  const info = s=>`<div class="section-note neutral"><span style="font-size:17px">ⓘ</span><span>${esc(s)}</span></div>`;
  const card = (inner,extra='')=>`<section class="panel intel-card ${extra}">${inner}</section>`;
  const title = (a,b='')=>`<div class="panel-header"><div><h2>${esc(a)}</h2>${b?`<span class="overline">${esc(b)}</span>`:''}</div></div>`;
  async function cases(){
    if(!casesPromise)casesPromise=fetch(sourceUrl,{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('Case study file not available');return r.json()}).then(x=>x.cases);
    return casesPromise;
  }
  function caseSite(c,facilities){return facilities.find(f=>f.id===c.public_facility_id||f.id===c.local_facility_id);}
  function timeline(caseObj){
    const evidence=caseObj.milestones.map(m=>`<div class="intel-milestone"><div class="intel-date">${esc(m.date)}${m.publication_date?`<small>Published ${esc(m.publication_date)}</small>`:'<small>Publication date unverified</small>'}</div><div class="intel-event"><span class="pill gray">${esc(m.stage)}</span><p>${esc(m.fact)}</p><div class="intel-ref">${safeLink(m.source_url)}<span>${esc(m.note)}</span></div></div></div>`).join('');
    return `<div class="intel-timeline">${evidence}</div>`;
  }
  function caseCard(c,sites){
    const f=caseSite(c,sites);const btn=f?`<button class="btn tiny" data-site="${esc(f.id)}">Open facility ↗</button>`:'';
    return card(`${title(c.title,c.peril)}<div class="intel-card-body"><div class="intel-badges"><span class="pill ${c.outcome_class==='documented_resilience'?'':'orange'}">${esc(c.outcome)}</span><span class="pill gray">${esc(c.incident_date)}</span></div><p class="intel-summary">${esc(c.summary)}</p><div class="intel-split"><div><strong>Business/financial consequence</strong><p>${esc(c.financial_effect)}</p></div><div><strong>Documented resilience</strong><p>${esc(c.resilience)}</p></div></div><div class="intel-pre"><b>Pre-event evidence gate:</b> ${esc(c.pre_event_evidence_status)}</div>${timeline(c)}<div class="intel-footer">${btn}<span>Events and filings are historical evidence, not a prospective risk probability.</span></div></div>`,'intel-case');
  }
  function casePage(cs,sites){return `<div class="intel-case-grid">${cs.map(c=>caseCard(c,sites)).join('')}</div>`;}
  function sitePrecise(s){return (s.location?.precision==='site_verified'||s.location?.precision==='property_polygon');}
  function mapPage(sites){
    const plotted=sites.filter(s=>s.latitude!=null&&s.longitude!=null),verified=sites.filter(sitePrecise).length;
    const sidebar=plotted.map(s=>`<button class="intel-map-row" data-focus-lat="${Number(s.latitude)}" data-focus-lon="${Number(s.longitude)}"><span class="intel-location-dot ${sitePrecise(s)?'verified':'approx'}"></span><span><strong>${esc(s.name)}</strong><small>${sitePrecise(s)?'Reviewed site point':'Unverified / reference point'} · ${esc(s.country||'')}</small></span></button>`).join('');
    return `${info('Map pins are navigational. A city point or unreviewed analyst coordinate does not establish parcel-specific flood, wildfire or property exposure. FEMA zone checks require a separately verified site point.')}
    <div class="intel-map-grid">${card(`<div class="intel-map-canvas" id="intel-map-canvas"><div class="intel-map-fallback">Loading interactive basemap…</div></div><div class="intel-map-foot"><span>● ${plotted.length} mapped reference points</span><span>${verified} site point(s) independently reviewed</span></div>`)}${card(`${title('Facilities','Click a site to focus its location')}<div class="intel-map-site-list">${sidebar||'<p class="small-muted">No coordinate points available</p>'}</div>`)}</div>
    <div class="intel-perils">${[['Flood','FEMA NFHL','Requires site-verified coordinates'],['Tornado / storm','NOAA Storm Events','Point and county event limitations'],['Seismic','USGS ComCat','Epicenter proximity is not shaking intensity'],['Water stress','WRI Aqueduct','Basin-scale modeled exposure'],['Wildfire','USFS / local hazard layers','Not yet integrated']].map(a=>`<div class="intel-peril"><b>${esc(a[0])}</b><span>${esc(a[1])}</span><small>${esc(a[2])}</small></div>`).join('')}</div>`;
  }
  async function initMap(sites){
    const root=$('#intel-map-canvas');if(!root)return;
    if(map){map.remove();map=null;}
    if(!window.L){root.innerHTML='<div class="intel-map-fallback">Basemap library unavailable. See the coordinates and locations in the facility list. No flood-zone classification was performed.</div>';return;}
    // External basemap tiles disclose geographic viewport to a third-party.
    // Do not transmit a private research location without a separate user opt-in.
    const snapshot=window.PublicRiskAPI?.getData ? await window.PublicRiskAPI.getData() : null;
    const privateMode=snapshot?.dataset_mode==='private_local_browser_import';
    if(privateMode&&!window.__facilityRiskMapOptIn){
      root.innerHTML='<div class="intel-map-fallback"><b>Private facility locations</b><p>Loading a third-party basemap shares the geographic viewport with the tile provider. Only enable for locations you are authorized to share.</p><button type="button" class="btn tiny" id="intel-private-map-optin">Enable external basemap</button></div>';
      root.querySelector('#intel-private-map-optin')?.addEventListener('click',()=>{window.__facilityRiskMapOptIn=true;initMap(sites);});
      return;
    }
    root.innerHTML='';
    map=L.map(root,{scrollWheelZoom:false,zoomControl:true,worldCopyJump:true}).setView([26,-70],3);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'&copy; OpenStreetMap contributors',maxZoom:16}).addTo(map);
    const bounds=[];
    for(const s of sites){if(s.latitude==null||s.longitude==null)continue;
      const ll=[Number(s.latitude),Number(s.longitude)];const good=sitePrecise(s);
      const marker=L.circleMarker(ll,{radius:good?8:7,color:good?'#246e68':'#bd795a',weight:2,fillColor:good?'#2f9990':'#d6a083',fillOpacity:.85});
      marker.bindPopup(`<strong>${esc(s.name)}</strong><p>${good?'Reviewed coordinate':'Reference coordinate — property not independently verified'}</p>`).addTo(map);bounds.push(ll);
    }
    if(bounds.length)map.fitBounds(bounds,{padding:[32,32],maxZoom:6});
    root.querySelectorAll?.('.leaflet-control-attribution')?.forEach(el=>el.setAttribute('aria-label','Map attribution'));
    document.querySelectorAll('[data-focus-lat]').forEach(b=>b.addEventListener('click',()=>{
      map.setView([Number(b.dataset.focusLat),Number(b.dataset.focusLon)],10,{animate:true});
    }));
    setTimeout(()=>map&&map.invalidateSize(),100);
  }
  function identityPage(sites,quality){
    const reviewed=quality?.verified_frs_links||0;
    const rows=sites.map(s=>{
      const f=(s.identifiers||[]).filter(x=>x.namespace==='EPA_FRS'&&x.status==='verified');
      const pending=(s.candidates||[]).filter(x=>x.decision==='pending');
      const p=s.location?.precision||'not reviewed';
      return `<tr><td><strong>${esc(s.name)}</strong><small>${esc(s.country||'')}</small></td><td>${esc(s.fei||'Unknown')}</td><td>${f.length?f.map(x=>esc(x.identifier)).join(', '):'<span class="intel-pending">Not verified</span>'}</td><td>${pending.length?`<strong>${pending.length} candidate(s)</strong>`:'—'}</td><td>${esc(p.replaceAll('_',' '))}</td></tr>`;
    }).join('');
    return `${info('An FDA FEI is not an EPA FRS Registry ID. Candidate links are never accepted based only on name similarity or proximity. Reviewer identity, evidence, and rationale are mandatory.')}
      <div class="intel-metrics"><div><strong>${reviewed}</strong><span>Verified FRS crosswalks</span></div><div><strong>${quality?.frs_candidates_pending||0}</strong><span>Open match candidates</span></div><div><strong>${quality?.verified_site_locations||0}</strong><span>Reviewed site points</span></div></div>
      ${card(`${title('Facility crosswalk review','Analyst FEIs are observed identifiers, not a verified public API match')}<div class="table-wrap"><table><thead><tr><th>Facility</th><th>Recorded FDA FEI</th><th>Verified EPA FRS</th><th>Awaiting review</th><th>Coordinate quality</th></tr></thead><tbody>${rows}</tbody></table></div>`)}
      ${card(`${title('Review protocol','No inferred matches become verified automatically')}<div class="intel-card-body">Search EPA FRS for candidate sites, compare legal operator and physical address, review multiple identifier systems and coordinate method, then log acceptance or rejection with a dated source. The local authenticated server supports this workflow; GitHub Pages is read-only.</div>`)}`;
  }
  function underwritingPage(sites,casesBySite){
    const rows=sites.map(s=>{
      const found=casesBySite.find(c=>c.public_facility_id===s.id||c.local_facility_id===s.id);
      const prof=s.profile||found?.underwriting;
      return card(`${title(s.name,s.country||'')}<div class="intel-card-body"><div class="intel-exposure-grid">${[['Property damage','property_damage'],['Business interruption','business_interruption'],['Environmental / pollution','environmental_liability'],['Supply chain','supply_chain'],['Resilience','resilience']].map(([name,k])=>`<div class="intel-exposure"><b>${name}</b><p>${esc(prof?.[k]||'Not yet assessed. Requires facility evidence and policy/engineering inputs.')}</p></div>`).join('')}</div><div class="intel-footer"><span>Insured values: ${s.profile?.replacement_value_usd!=null?'Entered in private profile':'Unknown'} · No actuarial score</span><button class="btn tiny" data-site="${esc(s.id)}">Facility evidence ↗</button></div></div>`);
    }).join('');
    return `${info('These are evidence-based exposure summaries, not underwriting acceptance recommendations. Missing engineering reports, asset values, policy terms or loss runs remain explicitly unknown.')}<div class="intel-case-grid">${rows}</div>`;
  }
  function feedsPage(src,checks,extended=[],ledger=[],generatedAt=null,runUrl='',mounted=null){
    const mountRows=mounted?[
      ['EPA FRS source index',mounted.frs,'source_identities'],
      ['NOAA Storm Events index',mounted.noaa,'records'],
      ['NOAA IncidentNews selected responses',mounted.incidentnews,'records']
    ].map(([name,index,countKey])=>'<tr><td><strong>'+esc(name)+'</strong></td><td>'+
      esc(String(index?.state||'not_configured').replaceAll('_',' '))+'</td><td>'+
      (index?.[countKey]==null?'Not mounted':Number(index[countKey]).toLocaleString())+'</td><td>'+
      esc(index?.vintage||'No indexed vintage')+'</td><td>'+
      esc(index?.notice||'No verified private source index')+'</td></tr>').join(''):'';
    const reportAge = generatedAt ? (Date.now()-Date.parse(generatedAt))/86400000 : Infinity;
    const aged = !Number.isFinite(reportAge)||reportAge>3;
    const statusText = generatedAt ? ('Last published public-source check: '+generatedAt+(aged?' (STALE, older than 72 hours)':'')) : 'No published public-source check available';
    const importRows=ledger.map(x=>`<tr><td><strong>${esc(x.source)}</strong><small>${esc(x.scope||'')}</small></td><td>${esc(String(x.state||'unknown').replaceAll('_',' '))}</td><td>${x.records==null?'Not verified':Number(x.records).toLocaleString()}</td><td>${esc(x.checked_at||'Not published')}</td><td>${esc(x.details||'')}</td></tr>`).join('');
    const q=Array.isArray(checks)?checks:[];
    const rows=(src.length?src:[{source:'EPA FRS'},{source:'EPA ECHO'},{source:'FEMA NFHL'},{source:'USGS'},{source:'NOAA Storm Events'},{source:'FDA inspections'},{source:'WRI Aqueduct'}]).map(s=>{
      const v=q.find(x=>x.source===s.source);const status=v?.state||'not_published';
      return `<tr><td><strong>${esc(s.source)}</strong></td><td><span class="pill ${status==='reachable'?'':'orange'}">${esc(status.replaceAll('_',' '))}</span></td><td>${esc(v?.checked_at||'No published check')}</td><td>${esc(v?.details||'Connection status not verified in this browser preview')}</td><td>${safeLink(s.documentation,'Docs')}</td></tr>`;
    }).join('');
    const extraRows=extended.map(s=>`<tr><td><strong>${esc(s.name)}</strong><small>${esc(s.category)} · ${esc(s.priority)}</small></td><td><span class="pill ${s.probe_state==='schema_reachable'?'':'orange'}">${esc((s.probe_state||'not_published').replaceAll('_',' '))}</span></td><td>${esc(s.checked_at||'Not run')}</td><td>${esc(s.probe_details||s.test)}<br><small>${esc(s.access)} · ${esc(s.limitation)}</small></td><td>${safeLink(s.documentation,'Official source')}</td></tr>`).join('');
    return `${mounted?card(`${title('Private indexed source deployment','Read-only mounted source databases, separate from insured research workspace')}<div class="table-wrap"><table><thead><tr><th>Source index</th><th>Readiness</th><th>Records</th><th>Source vintage</th><th>Meaning</th></tr></thead><tbody>${mountRows}</tbody></table></div>`):''}${info(mounted?'The authenticated private service can query source-only datasets when validated indexes are mounted. An imported identity or nearby weather event does not verify a physical insured property, its hazard intensity, damage, or policy coverage.':'GitHub Actions can refresh public-source health metadata, but GitHub Pages is a static viewer. A successful HTTP probe means only that a publisher endpoint responded; it does not mean facility data, matching or insurance exposure was ingested.')}
      ${card(`${title('Published checks and freshness','Separate reachability, identities imported and verified property exposure')}<div class="intel-card-body">${esc(statusText)}${runUrl?' · '+safeLink(runUrl,'Inspect workflow') : ''}${aged?'<p><strong>These checks are stale or missing and must not be interpreted as current availability.</strong></p>':''}</div>`) }\n      ${card(`${title('Actual published data ingestion','Published identities are not verified properties, incidents, or hazard overlays')}<div class="table-wrap"><table><thead><tr><th>Dataset</th><th>Ingestion state</th><th>Source identities</th><th>Snapshot date</th><th>Limitations</th></tr></thead><tbody>${importRows||'<tr><td colspan="5">No published ingestion ledger available.</td></tr>'}</tbody></table></div>`)}
      ${card(`${title('Source health and ingestion readiness','Source connection is separate from data validation')}<div class="table-wrap"><table><thead><tr><th>Source</th><th>State</th><th>Last checked</th><th>Notes</th><th>Reference</th></tr></thead><tbody>${rows}</tbody></table></div>`)}
      ${card(`${title('Additional dataset evaluations','Access checks do not establish facility linkage')}<div class="table-wrap"><table><thead><tr><th>Source</th><th>Probe state</th><th>Checked</th><th>Testing and limitations</th><th>Reference</th></tr></thead><tbody>${extraRows||'<tr><td colspan="5">No extended sources loaded</td></tr>'}</tbody></table></div>`)}
      ${card(`${title('Ingestion gates','All required before use in an underwriting decision')}<div class="intel-card-body"><div class="intel-gate-list">${['Endpoint or official export is accessible','Original response archived with retrieval time','Source schema validated and normalized','Correct facility identified and independently reviewed','Event/validity/publication dates separated','Hazard proximity distinguished from confirmed loss','Quality checks and refresh status pass'].map((x,i)=>`<div><span class="intel-step">${String(i+1).padStart(2,'0')}</span>${esc(x)}</div>`).join('')}</div></div>`)}`;
  }
  const pages={
    cases:['Historical events','Incident and recovery timelines','Dated primary-source reconstruction of losses, disruption and operational resilience.'],
    map:['Facility geography','Location and hazard screening','Navigable geography with clearly qualified precision and unverified hazard coverage.'],
    identity:['Data governance','Facility identity and crosswalks','Track recorded FEIs, review EPA candidate matches and confirm physical site coordinates.'],
    underwriting:['Insurance assessment','Underwriting exposure profiles','Separate property, BI, environmental, supply-chain and resilience evidence.'],
    feeds:['Ingestion operations','Data source connectivity','Live-source connectors, refresh readiness and validation status.']
  };
  function render(page){const a=pages[page];return heading(...a)+`<div id="intel-content" class="intel-content"><div class="loading-card">Preparing ${esc(a[1].toLowerCase())}…</div></div>`;}
  async function mount(page,{state,api}){
    const root=$('#intel-content');if(!root)return;
    try{
      if(page==='cases'){root.innerHTML=casePage(await cases(),state.facilities);return;}
      if(page==='map'){
        const intel=await api('intelligence');if(!root.isConnected)return;
        // Prefer server/snapshot review status; fall back to loaded location references.
        const status=new Map((intel.sites||[]).map(x=>[x.id,x]));
        const sites=state.facilities.map(f=>({...f,...(status.get(f.id)||{}),
          latitude:f.latitude,longitude:f.longitude}));
        root.innerHTML=mapPage(sites);await initMap(sites);return;
      }
      const intel=await api('intelligence');if(!root.isConnected)return;
      const status=new Map((intel.sites||[]).map(x=>[x.id,x]));
      const sites=state.facilities.map(f=>({...f,...(status.get(f.id)||{}),name:f.name,country:f.country,fei:f.fei}));
      if(page==='identity')root.innerHTML=identityPage(sites,intel.quality);
      if(page==='underwriting')root.innerHTML=underwritingPage(sites,await cases());
      if(page==='feeds'){
        let extra=[],mounted=null;
        try{const res=await api('source-extensions');extra=res.items||[];}catch(e){/* Older snapshots may omit this optional catalog. */}
        if(!window.PublicRiskAPI){
          try{mounted=await api('source-indices/status');}catch(e){/* Private sidecars may not exist on older backends. */}
        }
        root.innerHTML=feedsPage(intel.source_catalog||[],intel.source_health||[],extra,intel.ingestions||[],intel.public_status_generated_at,intel.source_run_url,mounted);
      }
    }catch(e){if(root.isConnected)root.innerHTML=`<div class="loading-card">Unable to load research panel: ${esc(e.message)}</div>`;}
  }
  window.addEventListener('facilityrisk:dataset-changed',()=>{window.__facilityRiskMapOptIn=false;});
  window.IntelligenceUI={render,mount,pages};
})();
