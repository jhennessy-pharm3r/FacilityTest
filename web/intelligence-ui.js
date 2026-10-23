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
  function laneAFloodPanel(sites){
    if(window.PublicRiskAPI)return '';
    const options=sites.slice(0,250).map(s=>'<option value="'+esc(s.id)+'">'+esc(s.name||s.id)+'</option>').join('');
    return card(title('FEMA flood source evidence','Authenticated source-index check · site coordinates require independent review')+
      '<div class="intel-card-body"><p>Run a read-only FEMA NFHL polygon check for a private research site. Only the server-stored, independently reviewed CURRENT property coordinate can be evaluated. Outside the six QA windows, missing evidence remains UNKNOWN; no insured loss or effective FIRM determination is inferred.</p>'+
      '<div class="intel-map-source-query"><label for="lane-a-site">Private research site</label><div class="intel-source-check-controls"><select id="lane-a-site">'+options+'</select>'+
      '<button class="btn" id="lane-a-check-fema" type="button"'+(options?'':' disabled')+'>Check FEMA source polygons</button></div></div>'+
      '<div id="lane-a-fema-result" class="intel-source-check-result" role="status" aria-live="polite">Verifying mounted source index…</div></div>');
  }
  async function initLaneAFloodPanel(api){
    const button=$('#lane-a-check-fema'),output=$('#lane-a-fema-result'),picker=$('#lane-a-site');
    if(!button||!output)return;
    let mounted=false;
    try{
      const s=await api('lane-a/status');
      mounted=s?.state==='ready_partial';
      output.textContent=mounted?
        ('Bounded FEMA source index ready: '+Number(s.fema_source_polygons).toLocaleString()+
         ' polygons in six test windows. This is not national flood coverage.') :
        'Verified Lane A index not mounted here; no flood conclusion is available.';
    }catch{
      output.textContent='FEMA source index unavailable; no flood conclusion is available.';
    }
    if(!output.isConnected)return;
    button.disabled=!mounted||!picker?.value;
    button.addEventListener('click',async()=>{
      if(!picker?.value)return;
      button.disabled=true;
      output.textContent='Checking original FEMA polygons with stored location-review evidence…';
      try{
        const result=await api('facilities/'+encodeURIComponent(picker.value)+'/fema-nfhl');
        const state=String(result.coverage_state||'UNKNOWN');
        const hits=Array.isArray(result.source_features)?result.source_features:[];
        output.textContent=(state==='SOURCE_POLYGON_INTERSECTION_AT_CORROBORATED_POINT'?
          'Source polygons intersect the reviewed point: '+hits.map(x=>x.flood_zone||'unlabeled').join(', ')+'. ':
          state==='BOUNDARY_OR_SIMPLIFICATION_REVIEW_REQUIRED'?
          'Boundary or simplified geometry: qualified map review required. ':
          'No verified FEMA polygon conclusion: '+state.replaceAll('_',' ').toLowerCase()+'. ')+
          'No legal NFIP/FIRM effective-date, property damage, policy or insured loss determination.';
      }catch{
        output.textContent='FEMA source or reviewed-site evidence unavailable; exposure remains UNKNOWN.';
      }finally{button.disabled=!mounted;}
    });
  }
  function mapPage(sites){
    const plotted=sites.filter(s=>s.latitude!=null&&s.longitude!=null),verified=sites.filter(sitePrecise).length;
    const sidebar=plotted.map(s=>`<button class="intel-map-row" data-focus-lat="${Number(s.latitude)}" data-focus-lon="${Number(s.longitude)}"><span class="intel-location-dot ${sitePrecise(s)?'verified':'approx'}"></span><span><strong>${esc(s.name)}</strong><small>${sitePrecise(s)?'Reviewed site point':'Unverified / reference point'} · ${esc(s.country||'')}</small></span></button>`).join('');
    return `${info('Map pins are navigational. A city point or unreviewed analyst coordinate does not establish parcel-specific flood, wildfire or property exposure. FEMA zone checks require a separately verified site point.')}
    <div class="intel-map-grid">${card(`<div class="intel-map-canvas" id="intel-map-canvas"><div class="intel-map-fallback">Loading interactive basemap…</div></div><div class="intel-map-foot"><span>● ${plotted.length} mapped reference points</span><span>${verified} site point(s) independently reviewed</span></div>`)}${card(`${title('Facilities','Click a site to focus its location')}<div class="intel-map-site-list">${sidebar||'<p class="small-muted">No coordinate points available</p>'}</div>`)}</div>
    <div class="intel-perils">${[['Flood','FEMA NFHL','Requires site-verified coordinates'],['Tornado / storm','NOAA Storm Events','Point and county event limitations'],['Seismic','USGS ComCat','Epicenter proximity is not shaking intensity'],['Water stress','WRI Aqueduct','Basin-scale modeled exposure'],['Wildfire','USFS WHP2023','Verified QA raster pixels / geographic aggregates only; property-level raster still missing']].map(a=>`<div class="intel-peril"><b>${esc(a[0])}</b><span>${esc(a[1])}</span><small>${esc(a[2])}</small></div>`).join('')}</div>${laneAFloodPanel(sites)}`;
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
  function parallelIngestionPanel(summary) {
    if (!summary || !Array.isArray(summary.lanes)) return '';
    const amount = v => v == null ? 'Not measured' : Number(v).toLocaleString('en-US');
    const stages = {sample_ci_indexed:'Sample indexed in CI',ci_indexed:'Indexed in CI',staged_normalized:'Normalized, not indexed',downloaded_qa:'Official records QA',access_blocked:'Official access blocked'};
    const rows = summary.lanes.flatMap(lane => lane.sources.map(source => {
      const coords = source.valid_coordinates == null ? '' : ' · Source coordinates: ' + amount(source.valid_coordinates);
      return `<tr class="parallel-source-row" data-lane="${esc(lane.id)}" data-stage="${esc(source.stage)}"><td><strong>${esc(source.name)}</strong><small>${esc(lane.name)} · ${esc(source.scope)}</small></td>`+
        `<td><span class="pill ${source.stage === 'access_blocked' ? 'orange' : 'gray'}">${esc(stages[source.stage]||'Unknown')}</span></td>`+
        `<td>${amount(source.scanned)}</td><td>${amount(source.accepted)}</td><td>${amount(source.rejected)}</td>`+
        `<td>${amount(source.indexed_ci)}</td><td><strong>${amount(source.deployed)}</strong></td>`+
        `<td>${esc(source.notes)}${esc(coords)}<br><small>${safeLink(source.run_url,'Source run')} · ${safeLink(lane.pr_url,'Source PR')}</small></td></tr>`;
    })).join('');
    const laneRows = summary.lanes.map(lane => `<div class="qa-box"><span class="title">Lane ${esc(lane.id)} · ${esc(lane.name)}</span>`+
      `<b>${lane.sources.length} source streams</b><span>${esc(lane.gate)}</span></div>`).join('');
    const allStreams = summary.lanes.flatMap(lane=>lane.sources);
    const indexReady = allStreams.filter(s=>['ci_indexed','sample_ci_indexed'].includes(s.stage)).length;
    const sourceBlocked = allStreams.filter(s=>s.stage==='access_blocked').length;
    const inApp = allStreams.filter(s=>s.deployed>0).length;
    const summaryMetrics = '<div class="qa-grid">' + [
      ['Documented source streams', allStreams.length, 'Four official-source ingestion lanes'],
      ['Indexed in temporary CI', indexReady, 'Not queryable in the published app'],
      ['Official access blocked', sourceBlocked, 'Publisher access; unknown underlying totals'],
      ['Live production streams', inApp, 'No verified new-source production service']
    ].map(item=>'<div class="qa-box"><span class="title">'+esc(item[0])+'</span><b>'+
      Number(item[1]).toLocaleString('en-US')+'</b><span>'+esc(item[2])+'</span></div>').join('')+'</div>';
    const laneOptions = summary.lanes.map(l=>'<option value="'+esc(l.id)+'">Lane '+esc(l.id)+' — '+esc(l.name)+'</option>').join('');
    const sourceFilters = '<div class="filters"><div class="left"><select class="select" id="parallel-lane-filter" aria-label="Filter ingestion by lane">'+
      '<option value="">All source lanes</option>'+laneOptions+'</select>'+
      '<select class="select" id="parallel-stage-filter" aria-label="Filter ingestion by stage">'+
      '<option value="">All source stages</option><option value="indexed">Temporarily CI indexed</option>'+
      '<option value="access_blocked">Official access blocked</option></select></div>'+
      '<small id="parallel-visible-count">'+allStreams.length+' source streams</small></div>';

    const ageDays = (Date.now() - Date.parse(summary.as_of + 'T23:59:59Z')) / 86400000;
    const stale = !Number.isFinite(ageDays) || ageDays > 3;
    return card(`${title('Parallel-source ingestion progress','Real official-source QA from four separate lanes; not a deployed facility-risk dataset')}`+
      `<div class="intel-card-body"><p><strong>Source results as of ${esc(summary.as_of)}${stale?' (snapshot older than 72 hours)':''}.</strong> All four draft lanes remain outside the persistent, authenticated facility service. CI-only indexes and regulatory source observations cannot be interpreted as verified insured properties or hazard assessments.</p>`+
      `<p>${safeLink(summary.coordination_issue,'Coordination and latest progress')} · Each source row links its underlying official-source workflow and draft PR. Unknown source counts are not zero events.</p>`+
      `${summaryMetrics}<div class="qa-grid">${laneRows}</div></div>`+
      `${sourceFilters}<div class="table-wrap"><table><thead><tr><th>Source and scope</th><th>Stage</th><th>Scanned</th><th>Accepted</th><th>Rejected</th><th>CI indexed</th><th>App deployed</th><th>Evidence and limitations</th></tr></thead><tbody>${rows}</tbody></table></div>`+
      `<div class="intel-card-body"><strong>Deployment gate:</strong> no Lane A–D source has authenticated persistent serving, independently approved physical-site matching, or confirmed loss/claims linkage. Record grain differs by publisher; never sum these rows into a facility count.</div>`);
  }
  function feedsPage(src,checks,extended=[],ledger=[],generatedAt=null,runUrl='',mounted=null,parallel=null){
    const laneA=mounted?.lane_a;
    const laneARows=!laneA?'':laneA.state==='ready_partial'?[
      ['FEMA NFHL — bounded flood polygons','fema_nfhl','Six limited city QA envelopes; original map effective dates unverified'],
      ['USFS WHP 2023 — continuous QA pixels','usda_continuous','70 geographic raster QA pixels, not facility risk'],
      ['USFS WHP 2023 — classified QA pixels','usda_classified','70 QA pixels; water/non-burnable masks remain distinct'],
      ['USFS WHP 2023 — administrative aggregates','usda_summary','Countrywide publisher summary rows; not whole-country 270m raster']
    ].map(([name,code,limitation])=>'<tr><td><strong>'+esc(name)+'</strong></td><td>Read-only · bounded source data</td><td>'+
      Number(laneA.source_only_records?.[code]||0).toLocaleString()+'</td><td>'+
      esc(code==='fema_nfhl'?'FEMA current-service QA; FIRM effective date unverified':'WHP2023; revised 2024-07-17')+'</td><td>'+
      esc(limitation)+'<br><small>Release '+esc(laneA.release_id||'unknown')+' · 0 approved insured-site matches</small></td></tr>').join(''):
      '<tr><td><strong>Lane A flood / wildfire source release</strong></td><td>'+
      esc(String(laneA.state||'unavailable').replaceAll('_',' '))+
      '</td><td>Not mounted</td><td>Unverified private server</td><td>'+
      esc(laneA.notice||'Lane A source-only index unavailable; risk UNKNOWN')+'</td></tr>';
    const mountRows=mounted?([
      ['EPA FRS source index',mounted.frs,'source_identities'],
      ['NOAA Storm Events index',mounted.noaa,'records'],
      ['NOAA IncidentNews selected responses',mounted.incidentnews,'records']
    ].map(([name,index,countKey])=>'<tr><td><strong>'+esc(name)+'</strong></td><td>'+
      esc(String(index?.state||'not_configured').replaceAll('_',' '))+'</td><td>'+
      (index?.[countKey]==null?'Not mounted':Number(index[countKey]).toLocaleString())+'</td><td>'+
      esc(index?.vintage||'No indexed vintage')+'</td><td>'+
      esc(index?.notice||'No verified private source index')+'</td></tr>').join('')+laneARows):'';
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
      ${card(`${title('Published checks and freshness','Separate reachability, identities imported and verified property exposure')}<div class="intel-card-body">${esc(statusText)}${runUrl?' · '+safeLink(runUrl,'Inspect workflow') : ''}${aged?'<p><strong>These checks are stale or missing and must not be interpreted as current availability.</strong></p>':''}</div>`) }\n      ${parallelIngestionPanel(parallel)}
      ${card(`${title('Actual published data ingestion','Published identities are not verified properties, incidents, or hazard overlays')}<div class="table-wrap"><table><thead><tr><th>Dataset</th><th>Ingestion state</th><th>Source identities</th><th>Snapshot date</th><th>Limitations</th></tr></thead><tbody>${importRows||'<tr><td colspan="5">No published ingestion ledger available.</td></tr>'}</tbody></table></div>`)}
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
        root.innerHTML=mapPage(sites);await initMap(sites);
        if(!window.PublicRiskAPI)await initLaneAFloodPanel(api);
        return;
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
        root.innerHTML=feedsPage(intel.source_catalog||[],intel.source_health||[],extra,intel.ingestions||[],intel.public_status_generated_at,intel.source_run_url,mounted,intel.parallel_ingestion||null);
        const laneFilter=root.querySelector('#parallel-lane-filter');
        const stageFilter=root.querySelector('#parallel-stage-filter');
        const applyParallelFilters=()=>{
          const rows=Array.from(root.querySelectorAll('tr.parallel-source-row'));
          let visible=0;
          for (const tr of rows) {
            const laneOK=!laneFilter?.value||tr.dataset.lane===laneFilter.value;
            const stageOK=!stageFilter?.value||(stageFilter.value==='indexed'?
              ['ci_indexed','sample_ci_indexed'].includes(tr.dataset.stage):tr.dataset.stage===stageFilter.value);
            const show=laneOK&&stageOK;
            tr.style.display=show?'':'none';
            if(show)visible++;
          }
          const counter=root.querySelector('#parallel-visible-count');
          if(counter)counter.textContent=visible+' of '+rows.length+' source streams';
        };
        laneFilter?.addEventListener('change',applyParallelFilters);
        stageFilter?.addEventListener('change',applyParallelFilters);
      }
    }catch(e){if(root.isConnected)root.innerHTML=`<div class="loading-card">Unable to load research panel: ${esc(e.message)}</div>`;}
  }
  window.addEventListener('facilityrisk:dataset-changed',()=>{window.__facilityRiskMapOptIn=false;});
  window.IntelligenceUI={render,mount,pages};
})();
