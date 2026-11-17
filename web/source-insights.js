/* Public aggregate source intelligence for cross-industry facility underwriting.
   Source grains and CI artifacts never imply a deployed property-level dataset. */
(() => {
  'use strict';
  const script=document.getElementById('source-insights-script');
  const url=new URL('./coordination/parallel-ingestion.json',script?.src||document.baseURI);
  let snapshotPromise=null;
  const esc=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt=n=>n==null?'Unknown':Number(n).toLocaleString('en-US');
  const safeLink=(u,label)=>{try{const x=new URL(u);return ['http:','https:'].includes(x.protocol)?'<a href="'+esc(x.href)+'" rel="noopener noreferrer" target="_blank">'+esc(label)+' ↗</a>':'';}catch{return '';}};
  // The grain is deliberately stated alongside counts; source rows are never summed as physical properties.
  const TYPES={
    fema_nfhl:{family:'Natural hazards',risk:'Flood exposure',unit:'sample polygon features',use:'Review flood-zone polygon candidates for a separately corroborated property coordinate.',need:'National coverage, geometry/effective-date review, and a verified site footprint.'},
    usfs_whp:{family:'Natural hazards',risk:'Wildfire potential',unit:'sample raster pixels',use:'Check raster-pixel handling for independently located sites.',need:'National high-resolution pixel serving and engineering site context.'},
    usfs_whp_classified:{family:'Natural hazards',risk:'Wildfire classifications',unit:'sample raster pixels',use:'Check classified masks separately from continuous wildfire values.',need:'Do not turn non-burnable/water masks into low property-risk ratings.'},
    usfs_whp_aggregates:{family:'Natural hazards',risk:'Regional wildfire screening',unit:'administrative summary rows',use:'Compare county, ZIP and state-scale wildfire context.',need:'Site-specific pixel and occupancy/construction evidence.'},
    usfs_whp2023_six_national_tiffs:{family:'Natural hazards',risk:'National wildfire raster',unit:'original GeoTIFF source files (not sites)',use:'Six original 270m continuous and classified GeoTIFFs cover CONUS, Alaska, and Hawaii: 133,505,015 valid landscape cells in each product. Distinct source files and cells are not insured buildings.',need:'Actual authenticated raster install, approved property coordinates, local engineering review, and vintage limitations; masked, water or nonburnable source pixels are not zero property risk.'},
    epa_echo:{family:'Environmental',risk:'Compliance screening',unit:'source registry records',use:'Find EPA program identities and candidate compliance-research leads.',need:'Exact legal operator, address, source identifiers and verified violation facts.'},
    epa_rcra:{family:'Environmental',risk:'Hazardous waste',unit:'six-table regulatory rows',use:'Investigate generator, handler and hazardous-waste program records.',need:'Retain native table grain; assess operating activity and site attribution.'},
    epa_tri:{family:'Environmental',risk:'Chemical reporting',unit:'chemical-report rows',use:'Compare historical reportable releases and chemical filing patterns.',need:'Chemical, amount, reporting year, process and exposure context; not claims.'},
    epa_rmp_public:{family:'Environmental',risk:'Process safety program',unit:'public program-interest rows',use:'Find public risk-management-program associations.',need:'No protected RMP plan or off-site consequence detail is provided.'},
    uscg_nrc:{family:'Industrial incidents',risk:'Spills and releases',unit:'initial notification reports',use:'Screen reported release history, dates and possible incidents.',need:'Confirm event, exact site and follow-up; many coordinates missing.'},
    csb:{family:'Industrial incidents',risk:'Major process accidents',unit:'incident publication rows',use:'Review selected chemical accident events and lessons learned.',need:'Source-vintage identity and actual site causation; not a national accident census.'},
    phmsa_enforcement:{family:'Industrial incidents',risk:'Pipeline enforcement',unit:'enforcement case rows',use:'Research operator safety enforcement and cited reports.',need:'An enforcement case is not a pipeline accident or property claim.'},
    phmsa_liquid:{family:'Industrial incidents',risk:'Pipeline incident history',unit:'source rows not downloaded',use:'Future accident-file screening when lawful official access is restored.',need:'Source HTTP 403; underlying incident counts are unknown.'},
    eia861:{family:'Utility & interruption',risk:'Electricity reliability',unit:'utility/territory rows',use:'Compare serving utility SAIDI/SAIFI context and territory candidates.',need:'Independently confirm customer meter and the serving utility.'},
    eia_b1:{family:'Utility & interruption',risk:'Grid disturbance',unit:'reported grid-event rows',use:'Research regional power disturbances and event chronology.',need:'Derived record IDs, overlap with other OE-417 reports and no site assignment.'},
    eia_b2:{family:'Utility & interruption',risk:'Grid disturbance history',unit:'annual reported grid-event rows',use:'Research utility disruption history and date context.',need:'County/utility context cannot establish site downtime or covered loss.'},
    pnnl_outages:{family:'Utility & interruption',risk:'County outage history',unit:'multitable county-level rows',use:'Analyze historical county-level outage observations and persistence.',need:'Repeated rows, different data grains, dated coverage and utility-to-site mapping.'},
    ornl_eaglei_2025:{family:'Utility & interruption',risk:'2025 electricity customer-out observations',unit:'publisher county x 15-minute readings (NOT outages)',use:'Inspect 28,509,491 accepted original 2025 source readings as time-indexed county context; 812,872 county/day summary rows are a separate grain.',need:'1,972,650 rejected original records; missing/zero reports, monitored meters, exact serving utility and property-level downtime are unverified. CI-only source Parquet, NOT deployed.'},
    odin_county:{family:'Utility & interruption',risk:'Outage status snapshots',unit:'snapshot rows',use:'Review publisher-reported county/utility outage-status evidence.',need:'One snapshot is not a continuous outage history or meter-level confirmation.'},
    odin_feeds:{family:'Utility & interruption',risk:'Utility feed health',unit:'provider-status rows',use:'Check reporting-system reliability and unknown/errored feeds.',need:'Feed failures are not outages; do not convert missing values to zeros.'},
    baxter_bi:{family:'Utility & interruption',risk:'Disruption outcome',unit:'issuer publication rows',use:'Examine documented Helene operational interruption and recovery.',need:'Forward sales outlook is not realized profit loss or paid BI claim.'},
    sec_bi:{family:'Utility & interruption',risk:'SEC financial outcomes',unit:'unretrieved original filings',use:'Link supported event disclosures when original filings can be validated.',need:'Bulk primary-source retrieval blocked; historical case-study links are separate.'}
  };
  const LENSES=[
    {name:'Natural hazards',key:'A',primary:'usfs_whp_aggregates',other:'fema_nfhl',short:'Flood polygons and wildfire geography',review:'Parcel location, effective hazard geometry, roof, elevation and defensible space',target:'map'},
    {name:'Environmental',key:'B',primary:'epa_echo',other:'epa_tri',short:'EPA registration, waste and chemical reporting',review:'Exact regulatory ID, site operations, permit/violation detail and pollution coverage',target:'identity'},
    {name:'Industrial incidents',key:'C',primary:'uscg_nrc',other:'csb',short:'Release notifications, investigations and enforcement',review:'Event corroboration, reporter location, process safeguards and injury/damage evidence',target:'cases'},
    {name:'Utility & interruption',key:'D',primary:'ornl_eaglei_2025',other:'pnnl_outages',short:'2025 county customer-out readings, historical outages and utility context',review:'Serving utility, downtime evidence, backup capacity and BI contract language',target:'underwriting'}
  ];
  const PAGE={
    workbench:{name:'Evidence to request before assessment',intro:'Use these as research leads for any facility and industry. Selected perils in the worksheet are hypothetical until corroborated.',ids:['fema_nfhl','usfs_whp2023_six_national_tiffs','usfs_whp_aggregates','epa_echo','uscg_nrc','ornl_eaglei_2025','pnnl_outages'],next:'Confirm the insured property boundary, business dependencies, engineering controls and policy triggers before making a risk determination.'},
    insurance:{name:'Data supporting coverage-trigger review',intro:'The source evidence below helps identify questions for property, pollution, utility service and parametric contracts; it does not establish that coverage exists.',ids:['fema_nfhl','usfs_whp2023_six_national_tiffs','usfs_whp_aggregates','epa_rmp_public','eia861','ornl_eaglei_2025','pnnl_outages'],next:'For every proposed insurance option, verify insured interest, index provider, attachment point, exclusion, waiting period, payout basis and basis risk.'},
    'bi-scenarios':{name:'Independent operational interruption evidence',intro:'County and utility records provide context, not an observed shutdown at a particular building.',ids:['eia861','ornl_eaglei_2025','pnnl_outages','odin_county','baxter_bi'],next:'Confirm the actual serving meter, dependency, duration, gross-margin assumptions, restoration costs and policy coverage.'},
    'policy-review':{name:'Source evidence versus policy evidence',intro:'Regulatory or natural-hazard observations cannot confirm an active policy endorsement or a payable claim.',ids:['fema_nfhl','epa_echo','pnnl_outages'],next:'Require original declarations, endorsements, schedules, dates, sublimits, deductibles and claims correspondence.'},
    universal:{name:'Source identity is not an insured property',intro:'Government facility registries contain legal and reporting identities, not an exhaustive global parcel census.',ids:['epa_echo','epa_rcra','epa_rmp_public'],next:'Resolve property address, operator, parent, jurisdiction and verified geocode; use private indexes only with authorized access.'},
    registry:{name:'Broader regulatory sources under validation',intro:'The searchable public FDA, Ireland and Canada catalogs are separate from these staged EPA source indexes; they are not silently mixed into results.',ids:['epa_echo','epa_rcra','epa_tri','epa_rmp_public'],next:'Matching requires original source ID, address and ownership evidence; an RCRA table row is not automatically a new facility.'},
    facilities:{name:'Site research requires independent matching',intro:'The workspace shows its own research cases. Millions of separately staged source rows do not automatically appear as verified properties.',ids:['epa_echo','uscg_nrc','fema_nfhl','eia861'],next:'Check building-specific geography, contemporaneous sources and reviewer-approved facility crosswalk before linking findings.'},
    cases:{name:'Historical cases versus population-wide evidence',intro:'The three case studies are independently documented event timelines. Separate nationwide/regional source cohorts have not been matched to these individual events.',ids:['baxter_bi','uscg_nrc','csb','pnnl_outages'],next:'Preserve event date versus publication date and distinguish company costs, insurance recoveries and paid insured claims.'},
    map:{name:'Hazard-layer coverage and missing geography',intro:'The existing map uses research-location reference pins, not flood polygons, wildfire pixels, or geocoded insured parcels.',ids:['fema_nfhl','usfs_whp2023_six_national_tiffs','usfs_whp','usfs_whp_classified','usfs_whp_aggregates'],next:'Flood: six small FEMA test windows only. Wildfire: full WHP2023 native 270m source rasters validated in CI, but not permanently installed or matched to insured properties.'},
    epa:{name:'EPA programs requiring exact facility identity',intro:'The authenticated EPA viewer may query mounted private source-only databases. Public CI source totals do not themselves establish an installed searchable property or confirmed violation.',ids:['epa_echo','epa_rcra','epa_tri','epa_rmp_public'],next:'Search the authenticated EPA source indexes, inspect native program IDs and original dates, then independently approve property-specific matches.'},
    identity:{name:'Regulatory identities requiring a crosswalk',intro:'Agency keys, source coordinates and reported operators need independent review before being assigned to an insured property.',ids:['epa_echo','epa_rcra','epa_tri','epa_rmp_public'],next:'Keep EPA REGISTRY_ID, RCRA ID_NUMBER/location, TRI reporting IDs and site-level identity decisions distinct.'},
    underwriting:{name:'Evidence domains for a facility exposure profile',intro:'These sources can support property, pollution, industrial, interruption and resilience research after corroborated site matching.',ids:['epa_echo','epa_tri','uscg_nrc','eia861','ornl_eaglei_2025','pnnl_outages'],next:'No actuarial weight, loss frequency, severity or insurance acceptance score is supported by source counts alone.'},
    evidence:{name:'Research findings versus raw source index',intro:'Evidence results below are curated case records. The independently validated source cohorts are not included in these search results until a private API is mounted.',ids:['epa_tri','uscg_nrc','csb','ornl_eaglei_2025','pnnl_outages'],next:'Document source-native IDs, publication and effective dates, matching decisions and error/duplicate treatment.'},
    disclosures:{name:'Business interruption outcome verification',intro:'Some historical examples have original filing citations. The separate SEC bulk ingestion lane remains access blocked; company publications are not insurance claims.',ids:['baxter_bi','sec_bi','pnnl_outages'],next:'Separate reported sales outlook, accounting charges, recovered amounts, actual lost profit and policy settlement.'},
    methodology:{name:'Validation principles applied to actual datasets',intro:'High record volume establishes a research population, not individual-site risk, probability or insurance loss.',ids:['epa_rcra','uscg_nrc','ornl_eaglei_2025','pnnl_outages'],next:'Backtesting needs records available before the event plus independently verified exposure, denominator and outcomes.'},
    reviews:{name:'Source facts awaiting site identity validation',intro:'Official source records never bypass independent reviewer approval or an insurer-specific coverage decision.',ids:['epa_echo','uscg_nrc','pnnl_outages'],next:'Source-native ID, property match rationale, inspection of conflict evidence and second-person decision are required.'}
  };
  const stageText={
    sample_ci_indexed:'Sample indexed in CI',
    ci_indexed:'Source indexed in CI',
    staged_normalized:'Normalized in staging',
    downloaded_qa:'Downloaded / QA',
    access_blocked:'Official access blocked'
  };
  function valid(d){
    if(!d||d.schema_version!=='1.0'||d.review_status!=='verified_source_qa_not_deployed'||
        !Array.isArray(d.lanes)||d.lanes.length!==4||!/^\d{4}-\d{2}-\d{2}$/.test(d.as_of||''))return null;
    const seen=new Set();
    for(const l of d.lanes){
      if(!['A','B','C','D'].includes(l.id)||!Array.isArray(l.sources))return null;
      for(const s of l.sources){
        if(!s.id||seen.has(s.id)||!Object.prototype.hasOwnProperty.call(stageText,s.stage)||
          s.deployed!==0||s.verified_insured_sites!==0)return null;
        if(s.accepted!==null&&(!Number.isSafeInteger(s.accepted)||s.accepted<0))return null;
        if(s.rejected!==null&&(!Number.isSafeInteger(s.rejected)||s.rejected<0))return null;
        if(s.scanned!==null&&s.scanned!==s.accepted+s.rejected)return null;
        if(s.indexed_ci!==null&&(s.accepted===null||s.indexed_ci>s.accepted))return null;
        seen.add(s.id);
      }
    }
    return d;
  }
  function get(){
    if(!snapshotPromise)snapshotPromise=fetch(url,{cache:'no-store'})
      .then(r=>r.ok?r.json():null).then(valid).catch(()=>null);
    return snapshotPromise;
  }
  const byId=d=>new Map(d.lanes.flatMap(l=>l.sources.map(s=>[s.id,{...s,lane:l.id}])));
  const countLabel=(s,id)=>fmt(s.accepted)+' '+(TYPES[id]?.unit||'source rows');
  function sourceLink(id,label){
    return '<a class="si-link si-jump" data-si-source="'+esc(id)+'" href="?page=sources&record='+encodeURIComponent(id)+'">'+esc(label||'Explore dataset')+' →</a>';
  }
  function statline(s,id){
    const t=TYPES[id],label=s.stage==='access_blocked'?'Count unknown':countLabel(s,id);
    return '<span class="si-count">'+esc(label)+'</span><span class="si-stage">'+esc(stageText[s.stage]||'Unknown')+'</span>';
  }
  function mini(s,id){
    const t=TYPES[id];
    return '<article class="si-source-card"><div class="si-topline"><span>'+esc(t.risk)+'</span><span class="si-chip">'+esc(t.family)+'</span></div>'+
      '<h3>'+esc(s.name)+'</h3><div class="si-number">'+statline(s,id)+'</div>'+
      '<p>'+esc(t.use)+'</p><small><b>Still required:</b> '+esc(t.need)+'</small><div class="si-links">'+sourceLink(id,'Details')+
      safeLink(s.run_url,'QA evidence')+'</div></article>';
  }
  function banner(d,text){
    const rows=d.lanes.flatMap(l=>l.sources);
    const indexed=rows.filter(x=>['ci_indexed','sample_ci_indexed'].includes(x.stage)).length;
    const blocked=rows.filter(x=>x.stage==='access_blocked').length;
    return '<div class="si-integrity"><strong>Source-level QA · '+esc(d.as_of)+'</strong><span>'+esc(text)+
      '</span><span>'+indexed+' temporarily indexed · '+blocked+' blocked · <b>0 deployed / 0 approved insured-site links</b></span></div>';
  }
  function overview(d){
    const sources=byId(d);
    const cards=LENSES.map(l=>{
      const s=sources.get(l.primary),other=sources.get(l.other);
      if(!s||!other)return '';
      return '<article class="si-lens"><div class="si-lens-head"><span>LANE '+esc(l.key)+'</span><span>'+esc(l.name)+'</span></div>'+
        '<strong>'+esc(l.short)+'</strong><div class="si-lens-stat">'+esc(countLabel(s,l.primary))+'</div>'+
        '<p>'+esc(s.name)+' · '+esc(stageText[s.stage])+'</p>'+
        (l.key==='A'&&sources.has('usfs_whp2023_six_national_tiffs')?'<small><b>Full original WHP2023 national raster:</b> six TIFFs, 133,505,015 valid modeled cells per product; CI staged only, not insured sites.</small>':'')+
        '<small>Also: '+esc(other.name)+' ('+fmt(other.accepted)+' '+esc(TYPES[l.other]?.unit||'rows')+')</small>'+
        '<div class="si-lens-bottom"><span><b>Underwriting gate:</b> '+esc(l.review)+'</span>'+
        '<a href="?page='+esc(l.target)+'" data-si-nav="'+esc(l.target)+'">Review evidence →</a></div></article>';
    }).join('');
    return '<section class="si-panel si-overview"><div class="si-panel-head"><div><span class="si-eyebrow">ALL-INDUSTRY SOURCE INTELLIGENCE</span><h2>What the source data can tell us</h2>'+
      '<p>Four complementary evidence domains. Counts retain their source grain and do not represent unique facilities, loss events or insured claims.</p></div>'+
      '<a class="btn tiny" data-si-nav="sources" href="?page=sources">Explore 20 datasets →</a></div>'+
      '<div class="si-lens-grid">'+cards+'</div>'+banner(d,'Real official-source validation is separate from physical site matching and production deployment.')+'</section>';
  }
  function contextual(d,page){
    const cfg=PAGE[page];if(!cfg)return '';
    const sources=byId(d);
    const cards=cfg.ids.filter(id=>sources.has(id)).map(id=>mini(sources.get(id),id)).join('');
    const highlight=['map','underwriting','cases','disclosures','workbench','insurance','identity'].includes(page);
    return '<section class="si-panel si-context" data-si-panel="'+esc(page)+'"><div class="si-panel-head"><div>'+
      '<span class="si-eyebrow">PUBLISHER-SOURCED EVIDENCE · '+esc(d.as_of)+'</span><h2>'+esc(cfg.name)+'</h2>'+
      '<p>'+esc(cfg.intro)+'</p></div><a href="?page=sources" data-si-nav="sources" class="si-link">All source evidence →</a></div>'+
      (highlight?'<div class="si-ask"><b>Underwriting next step</b><p>'+esc(cfg.next)+'</p></div>':
       '<p class="si-guidance"><b>Next validation:</b> '+esc(cfg.next)+'</p>')+
      '<div class="si-card-track">'+cards+'</div>'+banner(d,'These are source validation cohorts, not separately verified individual properties.')+'</section>';
  }
  function quality(d){
    const data=d.lanes.flatMap(l=>l.sources);
    const indexed=data.filter(x=>['ci_indexed','sample_ci_indexed'].includes(x.stage)).length;
    const unknown=data.filter(x=>x.accepted==null).length;
    const tiles=[['Source streams',data.length,'Four source-owner lanes'],
      ['Temporary CI indexed',indexed,'Not an installed private API'],
      ['Official access blocked',unknown,'Missing is not zero observations'],
      ['Verified site deployments',0,'No new-source site match approved']];
    const steps=[
      ['Source download','Official download, vintage and original checksum confirmed'],
      ['Normalization','Reconciled native IDs, accepted/rejected records and duplicates'],
      ['Temporary index','Reproducible read-only queries tested on CI runners'],
      ['Durable service','Authenticated persistent index, backup, and refresh not verified'],
      ['Physical-site attribution','Operator/address/coordinate matched and independently approved'],
      ['Underwriting use','Source-specific perimeter and outcome/policy evidence reviewed']];
    const stage=data.map(s=>{
      const t=TYPES[s.id]||{};
      return '<tr><td>'+esc(s.name)+'</td><td>'+esc(t.family||'Other')+'</td><td>'+fmt(s.accepted)+'</td><td>'+esc(stageText[s.stage])+'</td><td>'+
        (s.deployed?'Mounted release verified':'Not deployed')+'</td><td>'+safeLink(s.run_url,'Run')+'</td></tr>';
    }).join('');
    return '<section class="si-panel si-quality"><div class="si-panel-head"><div><span class="si-eyebrow">READINESS / DATA INTEGRITY</span>'+
      '<h2>Source-to-site validation gates</h2><p>Evidence coverage, temporal validity and incident linking must be reconciled before insurance decisions.</p></div>'+
      '<a href="?page=feeds" data-si-nav="feeds" class="si-link">Source health →</a></div>'+
      '<div class="si-metric-grid">'+tiles.map(x=>'<div class="si-metric"><span>'+esc(x[0])+'</span><b>'+fmt(x[1])+'</b><small>'+esc(x[2])+'</small></div>').join('')+'</div>'+
      '<div class="si-gates">'+steps.map((x,i)=>'<div><strong>'+String(i+1).padStart(2,'0')+' · '+esc(x[0])+'</strong><span>'+esc(x[1])+'</span></div>').join('')+'</div>'+
      '<details class="si-qa-table"><summary>Review all original-source QA states</summary><div class="table-wrap"><table><thead><tr><th>Source</th><th>Risk area</th><th>Accepted source rows</th><th>CI state</th><th>Production state</th><th>Evidence</th></tr></thead><tbody>'+stage+'</tbody></table></div></details>'+
      banner(d,'A passing data-import job does not establish true negatives for an insured property.')+'</section>';
  }
  function inventory(d){
    const sources=byId(d);
    const row=[...sources.entries()].map(([id,s])=>{
      const t=TYPES[id];if(!t)return '';
      const haystack=[s.name,s.scope,s.notes,t.risk,t.family,t.use,t.need].join(' ').toLowerCase();
      return '<article class="si-inventory-row" data-si-source="'+esc(id)+'" data-si-family="'+esc(t.family)+'" data-si-stage="'+esc(s.stage)+'" data-si-search="'+esc(haystack)+'">'+
        '<div><span class="si-eyebrow">'+esc(t.family)+' / '+esc(t.risk)+'</span><h3>'+esc(s.name)+'</h3><p>'+esc(s.scope)+'</p></div>'+
        '<div class="si-inventory-count">'+statline(s,id)+'<small>Rejected: '+fmt(s.rejected)+'</small></div>'+
        '<div class="si-inventory-analysis"><strong>Use</strong><p>'+esc(t.use)+'</p><strong>Missing</strong><p>'+esc(t.need)+'</p>'+
        '<div class="si-links">'+safeLink(s.run_url,'Official-source QA')+safeLink(s.pr_url||d.lanes.find(x=>x.id===s.lane)?.pr_url,'Ingestion code')+'</div></div></article>';
    }).join('');
    const domains=LENSES.map(l=>'<option value="'+esc(l.name)+'">'+esc(l.name)+'</option>').join('');
    return '<section class="si-panel si-inventory"><div class="si-panel-head"><div><span class="si-eyebrow">SOURCED EVIDENCE CATALOG</span>'+
      '<h2>Reviewed source streams across four risk areas</h2><p>Search by industry concern, dataset, source ID or limitation. Detailed source grains are preserved; none are an insured-property census.</p></div>'+
      '<a href="?page=feeds" data-si-nav="feeds" class="si-link">Source health and provenance →</a></div>'+
      '<div class="si-controls"><label>Find a source<input id="si-inventory-search" class="field" placeholder="ECHO, flood, chemical, utility, NRC…" autocomplete="off"></label>'+
      '<label>Risk area<select id="si-inventory-family" class="select"><option value="">All risk areas</option>'+domains+'</select></label>'+
      '<label>Data status<select id="si-inventory-stage" class="select"><option value="">All statuses</option><option value="indexed">Validated in CI</option><option value="access_blocked">Official access blocked</option></select></label>'+
      '<button class="btn tiny" id="si-inventory-clear" type="button">Clear filters</button></div>'+
      '<div class="si-results-label" id="si-inventory-count" aria-live="polite">'+sources.size+' of '+sources.size+' sources</div>'+
      '<div id="si-inventory-list" class="si-inventory-list">'+row+'</div>'+
      '<div id="si-inventory-empty" class="si-empty" hidden>No source datasets match these filters. Missing data is not evidence of no risk.</div>'+
      banner(d,'Source names and evidence links are public aggregate metadata. The original installed SQLite records are private and not directly downloadable here.')+'</section>';
  }
  function wire(root,d){
    const input=root.querySelector('#si-inventory-search');
    if(!input)return;
    const family=root.querySelector('#si-inventory-family'),stage=root.querySelector('#si-inventory-stage');
    const rows=[...root.querySelectorAll('.si-inventory-row')],counter=root.querySelector('#si-inventory-count'),
      empty=root.querySelector('#si-inventory-empty');
    const route=new URL(window.location.href);
    const record=route.searchParams.get('record');
    if(record&&rows.some(row=>row.dataset.siSource===record))input.value=d.lanes.flatMap(l=>l.sources).find(s=>s.id===record)?.name||'';
    function apply(){
      let shown=0;
      for(const row of rows){
        const matches=(!input.value.trim()||row.dataset.siSearch.includes(input.value.trim().toLowerCase()))&&
          (!family.value||row.dataset.siFamily===family.value)&&
          (!stage.value||(stage.value==='indexed'?['ci_indexed','sample_ci_indexed'].includes(row.dataset.siStage):row.dataset.siStage===stage.value));
        row.hidden=!matches;
        if(matches)shown++;
      }
      if(counter)counter.textContent=shown+' of '+rows.length+' sources';
      if(empty)empty.hidden=shown>0;
    }
    const clear=root.querySelector('#si-inventory-clear');
    clear?.addEventListener('click',()=>{
      input.value='';family.value='';stage.value='';
      window.FacilityRiskRouter?.patch({record:null},'replace');
      apply();
    });
    input.addEventListener('input',()=>{
      window.FacilityRiskRouter?.patch({record:null},'replace');
      apply();
    });
    family.addEventListener('change',apply);
    stage.addEventListener('change',apply);
    apply();
  }
  function rootClick(event){
    const nav=event.target.closest?.('a[data-si-nav]');
    const link=event.target.closest?.('a.si-jump');
    if((!nav&&!link)||event.button!==0||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
    if(!window.FacilityRiskRouter)return;
    event.preventDefault();
    if(nav){
      window.FacilityRiskRouter.navigate(nav.dataset.siNav);
      return;
    }
    const id=link.dataset.siSource;
    window.FacilityRiskRouter.navigate('sources');
    window.FacilityRiskRouter.patch({record:id});
    // Subsequent async rendering uses the selected source ID from the URL.
  }
  document.addEventListener('click',rootClick);
  async function mount(page,element){
    if(page==='feeds'||!element)return;
    const slot=document.createElement('div');
    slot.className='si-mount';
    slot.dataset.sourceInsightsPage=page;
    const head=element.querySelector(':scope > .page-heading, .wb-hero, .page-heading');
    if(head)head.insertAdjacentElement('afterend',slot);
    else element.prepend(slot);
    const doc=await get();
    if(!slot.isConnected)return;
    if(!doc){slot.innerHTML='<div class="si-unavailable">Independent source-ingestion status is unavailable. Verified site coverage and source freshness must be checked before decisions. <a href="?page=feeds" data-si-nav="feeds">View Source health</a>.</div>';return;}
    slot.innerHTML=page==='overview'?overview(doc):page==='sources'?inventory(doc):page==='quality'?quality(doc):contextual(doc,page);
    if(page==='sources')wire(slot,doc);
  }
  window.SourceInsights=Object.freeze({mount,manifest:get,types:TYPES});
})();
