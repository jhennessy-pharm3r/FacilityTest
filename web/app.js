/* Pharm3r Facility Risk Intelligence — local evidence explorer, no external JS dependencies. */
'use strict';
const $ = (sel, root=document) => root.querySelector(sel);
const $$ = (sel, root=document) => Array.from(root.querySelectorAll(sel));
const ROOT = $('#view-root');
const DRAWER = $('#detail-drawer');
const CONTENT = $('#drawer-content');
const state = {
  overview:null, facilities:[], sources:null, finance:null, quality:null,
  page:'workbench', facility:null, detail:null, evidence:null, risk:null, assets:null, assessment:null, reportAvailable:false, reviewQueue:null, tab:'summary',
  facilityQuery:'', country:'', source:'', disclosureQuery:'',
  evQuery:'', evSource:'', evDomain:'', evOffset:0, evLimit:25,
  globalQuery:'',globalSource:'',globalDomain:'',globalOffset:0,globalRecords:null,requestToken:0
};

/* URL routes work on static GitHub Pages and on the private FastAPI viewer.
   Query strings carry page/source identifiers only. Insurance assessment fields,
   private report content and policy details are deliberately never serialized. */
const ROUTE_PAGES=new Set(['workbench','insurance','policy-review','bi-scenarios','universal','registry','overview','facilities','evidence','disclosures','reviews','sources','quality','methodology','cases','map','identity','underwriting','feeds']);
const ROUTE_TABS=new Set(['summary','risk','evidence','disclosures']);
const ROUTE_KEYS=new Set(['page','facility','tab','q','country','source','sector','industry','domain','p','record']);

function routeableFacility(id){
  if(!window.PublicRiskAPI)return true;
  const label=document.getElementById('public-data-label')?.textContent||'';
  // Locally imported or browser-created research data is private to this tab.
  // A link cannot reconstitute it in somebody else's browser.
  return label.startsWith('Public examples')&&String(id).startsWith('public-');
}
function readRoute(){
  const params=new URL(window.location.href).searchParams;
  const wanted=params.get('page');
  const privateOnly={reviews:false,'policy-review':Boolean(window.CoverageReviewUI),'bi-scenarios':Boolean(window.BIScenarioUI)};
  const available=privateOnly[wanted]!==undefined?privateOnly[wanted]||wanted==='reviews'&&!window.PublicRiskAPI:true;
  const page=ROUTE_PAGES.has(wanted)&&available?wanted:'workbench';
  const rawId=params.get('facility')||'';
  const facility=rawId.length>0&&rawId.length<=200?rawId:null;
  const tab=ROUTE_TABS.has(params.get('tab'))?params.get('tab'):'summary';
  const rawPage=Number(params.get('p')||'1');
  const number=Number.isSafeInteger(rawPage)&&rawPage>=1&&rawPage<=100000?rawPage:1;
  return {page,facility,tab,q:(params.get('q')||'').slice(0,240),
    country:(params.get('country')||'').slice(0,80),
    source:(params.get('source')||'').slice(0,160),
    domain:(params.get('domain')||'').slice(0,160),p:number};
}
function patchRoute(changes,method='push'){
  const url=new URL(window.location.href);
  for(const [key,value] of Object.entries(changes||{})){
    if(!ROUTE_KEYS.has(key))continue;
    if(value==null||value==='')url.searchParams.delete(key);
    else url.searchParams.set(key,String(value).slice(0,240));
  }
  if(!ROUTE_PAGES.has(url.searchParams.get('page')))url.searchParams.set('page',state.page);
  if(url.href!==window.location.href)window.history[method==='replace'?'replaceState':'pushState']({facilityRiskRoute:true},'',url);
}
function navigateToPage(page){
  if(!ROUTE_PAGES.has(page))return;
  if(window.PublicRiskAPI&&['reviews','policy-review','bi-scenarios'].includes(page))return;
  const url=new URL(window.location.href);
  url.search='';
  url.hash='';
  url.searchParams.set('page',page);
  if(url.href!==window.location.href)window.history.pushState({facilityRiskRoute:true},'',url);
  state.page=page;
  closeDrawer();
  if(state.overview)renderPage();
  window.scrollTo(0,0);
}
function routeFilters(route){
  state.facilityQuery=route.page==='facilities'?route.q:'';
  state.country=route.page==='facilities'?route.country:'';
  state.disclosureQuery=route.page==='disclosures'?route.q:'';
  state.globalQuery=route.page==='evidence'?route.q:'';
  state.globalSource=route.page==='evidence'?route.source:'';
  state.globalDomain=route.page==='evidence'?route.domain:'';
  state.globalOffset=route.page==='evidence'?(route.p-1)*50:0;
  state.globalRecords=null;
}
function restoreLocation(){
  if(!state.overview)return;
  const route=readRoute();
  const pageChanged=state.page!==route.page;
  state.page=route.page;
  routeFilters(route);
  if(pageChanged){
    closeDrawer();
    renderPage();
    window.scrollTo(0,0);
  }else if(route.page==='registry'){
    window.RegistryUI?.restoreRoute?.();
  }else if(route.page==='universal'){
    window.UniversalUI?.restoreRoute?.();
  }else if(['facilities','evidence','disclosures'].includes(route.page)){
    renderPage();
  }
  if(route.facility){
    if(state.facility!==route.facility)openSite(route.facility,{fromRoute:true,tab:route.tab});
    else if(state.tab!==route.tab)siteTab(route.tab,true);
  }else if(state.facility){
    closeDrawer();
  }
}
window.FacilityRiskRouter=Object.freeze({navigate:navigateToPage,patch:patchRoute,route:readRoute});

function escapeHTML(x) {return String(x == null?'':x).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function attr(x) {return escapeHTML(x);}
function safeURL(raw) {try {const u=new URL(String(raw||'')); return ['https:','http:'].includes(u.protocol)?u.href:'';}catch{return '';}}
function link(url,label='Open record') {const u=safeURL(url);return u?`<a href="${attr(u)}" target="_blank" rel="noopener noreferrer">${escapeHTML(label)} ↗</a>`:'<span class="small-muted">No source link</span>';}
function shortened(x,n=180){const s=String(x||'');return s.length>n?s.slice(0,n-1)+'…':s;}
function num(x){return Number(x||0).toLocaleString('en-US');}
function pct(a,b){return b?`${Math.round(100*a/b)}%`:'—';}
function empty(x,alt='Not available'){return x == null || String(x).trim()===''?alt:escapeHTML(x);}
async function api(path){if(window.PublicRiskAPI)return window.PublicRiskAPI.query(path);const res=await fetch('/api/'+path,{headers:{'Accept':'application/json'}});if(!res.ok)throw new Error(`API ${res.status}: ${path}`);return res.json();}
function note(text,neutral=false){return `<div class="section-note ${neutral?'neutral':''}"><span style="font-size:17px">${neutral?'ⓘ':'⚠'}</span><span>${escapeHTML(text)}</span></div>`;}
function heading(eyebrow,title,subtitle,action='') {return `<div class="page-heading"><div><div class="eyebrow">${escapeHTML(eyebrow)}</div><h1>${escapeHTML(title)}</h1><p class="subhead">${escapeHTML(subtitle)}</p></div>${action}</div>`;}
function panel(name,subtitle,content,right=''){return `<section class="panel"><div class="panel-header"><div><h2>${escapeHTML(name)}</h2>${subtitle?`<span class="overline">${escapeHTML(subtitle)}</span>`:''}</div>${right}</div>${content}</section>`;}
function pill(txt,warm=false){return `<span class="pill ${warm?'orange':''}">${escapeHTML(txt)}</span>`;}
function stat(name,value,foot,symbol){return `<div class="stat-card"><div class="stat-head"><span>${escapeHTML(name)}</span><span class="stat-symbol">${symbol}</span></div><div class="stat-value">${escapeHTML(value)}</div><div class="stat-foot">${foot}</div></div>`;}
function initials(name){const w=String(name||'').replace(/[^\p{L}\p{N} ]/gu,'').split(/\s+/).filter(Boolean);return (w.slice(0,2).map(x=>x[0]).join('')||'FR').toUpperCase();}
function renderMap(sites){const W=940,H=260;const x=lon=>((Number(lon)+180)/360*W),y=lat=>((78-Number(lat))/130*H);const labeled=sites.filter(s=>s.latitude!=null&&s.longitude!=null);
  const grid=Array.from({length:7},(_,i)=>`<line x1="${i*W/6}" x2="${i*W/6}" y1="0" y2="${H}" stroke="#dce8e3" stroke-width="1"/>`).join('')+Array.from({length:5},(_,i)=>`<line x1="0" x2="${W}" y1="${i*H/4}" y2="${i*H/4}" stroke="#dce8e3" stroke-width="1"/>`).join('');
  const markers=labeled.map(s=>`<g data-site="${attr(s.id)}" style="cursor:pointer" tabindex="0" role="button" aria-label="Open ${attr(s.name)}"><circle cx="${x(s.longitude)}" cy="${y(s.latitude)}" r="11" fill="#bd7c60" fill-opacity=".16"/><circle cx="${x(s.longitude)}" cy="${y(s.latitude)}" r="5.2" fill="#b96f50" stroke="#fff" stroke-width="2"/><title>${escapeHTML(s.name)} — ${escapeHTML(s.country)}</title></g>`).join('');
  return `<div class="mapstage"><div class="map-grid"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Facility coordinates plotted by longitude and latitude, not a detailed geographic basemap"><defs><linearGradient id="sea" x2="1" y2="1"><stop stop-color="#f5faf7"/><stop offset="1" stop-color="#e6f2ed"/></linearGradient></defs><rect width="${W}" height="${H}" fill="url(#sea)"/>${grid}<text x="24" y="26" class="coord-label">LOCATIONS BY LONGITUDE / LATITUDE</text><text x="30" y="${H-16}" class="coord-label">WESTERN HEMISPHERE</text><text x="${W-135}" y="${H-16}" class="coord-label">EASTERN HEMISPHERE</text>${markers}</svg></div><div class="legend"><span><span class="legend-dot"></span>${labeled.length} facilities with plotted coordinates</span><span>Click a point to view facility evidence →</span></div><p class="viz-caption">Coordinate plot for research navigation. These positions may be city-level approximations; they are not a verified property boundary or a hazard map.</p></div>`;
}
function countryLabel(s){return String(s.country||'Unknown').replace('United States (Puerto Rico)','Puerto Rico');}
function renderOverview(){const o=state.overview,q=o.stats;const countries=[...new Set(o.facilities.map(x=>x.country))];const max=Math.max(1,...o.domains.map(x=>x.records));const totalSourceEvidence=o.sources.reduce((a,x)=>a+x.records,0);
  const top=heading('Case-study research / source evidence','Facility Research Overview','Investigated cases, dated event evidence and source-quality metrics—not the full universe of facilities.','<button class="btn primary" data-page="workbench">Start assessment →</button>');
  const stats=`<div class="stat-grid">${stat('Research facilities',num(q.facilities),`${countries.length} jurisdiction labels · ${q.geo_matched} geocoded`,'⌂')}${stat('Evidence records',num(q.evidence),`<span>${num(q.evidence_with_url)} source-linked</span> records`,'▤')}${stat('SEC disclosures',num(q.sec_findings),`${q.unmatched_sec_findings} without verified site link`,'≡')}${stat('Source families',num(q.sources),`${o.sources.length} observed evidence labels`,'◫')}</div>`;
  const domains=o.domains.map((d,i)=>`<div class="domain-row"><span class="domain-label" title="${attr(d.name)}">${escapeHTML(d.name)}</span><div class="bar-track"><div class="bar-fill ${i%4===2?'warm':''}" style="width:${Math.max(2,100*d.records/max)}%"></div></div><strong class="bar-count">${num(d.records)}</strong></div>`).join('');
  const siteRows=o.facilities.slice(0,8).map(s=>`<tr class="row-action" data-site="${attr(s.id)}" tabindex="0"><td><strong>${escapeHTML(s.name)}</strong><div class="mini-location">${escapeHTML(countryLabel(s))}</div></td><td class="nowrap">${s.fei?`<span class="mono">${escapeHTML(s.fei)}</span>`:'<span class="small-muted">Unknown</span>'}</td><td>${num(s.source_count)} sources</td><td><strong>${num(s.evidence_count)}</strong></td><td class="nowrap">Open ↗</td></tr>`).join('');
  const sources=o.sources.slice(0,7).map(s=>`<div class="compact-item"><div class="label-row"><span class="kicker">${escapeHTML(s.source)}</span><b>${num(s.records)} records</b></div><div class="detail">${s.programs} program(s) · ${pct(s.linked,s.records)} source URLs</div></div>`).join('');
  return top+`<div class="registry-overview-action"><div><strong>Assess any facility</strong><span>Begin an insurance exposure assessment for any property. Public source discovery currently includes FDA, Canada NPRI and Ireland EPA identities; nationwide EPA and Overture indices require a hosted backend.</span></div><button class="btn primary" data-page="registry">Browse public registry →</button></div>`+stats+note('Research evidence is not a calibrated insurance risk score. A nearby hazard does not establish site damage, and post-event disclosures cannot be used as pre-event predictors.')+
  `<div class="twocol">${panel('Facility footprint','Research-site reference locations',renderMap(o.facilities))}${panel('Evidence by risk domain','Record volume measures research coverage, not risk severity',`<div class="panel-body">${domains||'<div class="empty">No records imported.</div>'}</div>`)}</div>`+
  `<div class="lowergrid">${panel('Facility research coverage','Select a site to inspect original evidence',`<div class="table-wrap"><table><thead><tr><th>Facility</th><th>FDA FEI</th><th>Coverage</th><th>Records</th><th></th></tr></thead><tbody>${siteRows}</tbody></table></div><div class="panel-body"><button class="btn tiny" data-page="facilities">View all facilities →</button></div>`)}${panel('Leading source labels','Observed labels in imported research',`<div class="item-stack">${sources}</div><div class="panel-body"><button class="btn tiny" data-page="sources">View source inventory →</button></div>`)}</div>`;
}
function filteredFacilities(){return state.facilities.filter(s=>{
  const q=state.facilityQuery.toLowerCase();return(!q||[s.name,s.company,s.fei,s.address,s.activity].some(x=>String(x||'').toLowerCase().includes(q)))&&(!state.country||s.country===state.country)&&(!state.source|| (s.covered_sources||[]).includes(state.source));
});}
function cardSite(s){return `<button class="facility-card" data-site="${attr(s.id)}"><div class="label-row"><span class="initial">${escapeHTML(initials(s.name))}</span>${pill(s.fei?'FEI recorded':'FEI missing',!s.fei)}</div><div><h3>${escapeHTML(s.name)}</h3><p class="address">${escapeHTML(shortened(s.address,95))}</p></div><div class="card-meta">${pill(countryLabel(s))}${pill(`${s.evidence_count||0} evidence`)}${pill(`${s.source_count||0} sources`)}</div><div class="card-footer"><span>${s.latitude==null?'Coordinates unresolved':(s.coordinate_precision||'Coordinates available')}</span><span class="card-arrow">→</span></div></button>`;}
function renderFacilities(){const countryList=[...new Set(state.facilities.map(x=>x.country))].sort();const items=filteredFacilities();return heading('Research workspace','Investigated facilities','Facilities with imported evidence or newly created investigation requests. Search the full registered catalog for other sites.','<button class="btn" data-page="quality">Review coverage gaps</button>')+
  `<div class="filters"><div class="left"><input class="field" id="facility-search" aria-label="Search facilities" placeholder="Search facility, company, address or FEI…" value="${attr(state.facilityQuery)}"/><select class="select" id="country-filter" aria-label="Filter country"><option value="">All countries</option>${countryList.map(c=>`<option value="${attr(c)}" ${state.country===c?'selected':''}>${escapeHTML(countryLabel({country:c}))}</option>`).join('')}</select></div><span class="results-text" id="facility-result-count">${items.length} sites</span></div>`+
  `<div id="facility-cards" class="facility-grid">${items.length?items.map(cardSite).join(''):'<div class="panel empty">No matching facilities.</div>'}</div>`+note('Geographic references and source-specific site identity must be independently verified before hazard overlays or loss modeling.',true);
}

function renderGlobalRecords(){const p=state.globalRecords;if(!p)return '<div class="empty">Loading evidence…</div>';return `<div class="label-row" style="padding:16px 20px"><span class="small-muted">${num(p.total)} matching findings · page ${Math.floor(state.globalOffset/50)+1}</span><span class="small-muted">Sources and publication dates require independent validation</span></div>`+
  (p.items||[]).map(e=>`<div class="compact-item"><div class="label-row"><span class="card-meta">${pill(e.source)}${pill(e.risk_domain||'Other')}</span><span class="small-muted">${empty(e.date_raw,'Date not given')}</span></div><div style="margin-top:9px"><button class="link-inline" data-site="${attr(e.facility_id)}">${escapeHTML(e.facility_name)} →</button></div><div class="headline">${escapeHTML(e.record_type||e.program||'Finding')}</div><div class="detail">${escapeHTML(shortened(e.finding||e.value_text,380))}</div><div class="evidence-meta">${link(e.source_url,'Original record')} · ${escapeHTML(shortened(e.evidence_scope||'Scope unclassified',130))}</div></div>`).join('')+
  `<div class="pagination" style="padding:14px 20px"><span>${p.total?`${state.globalOffset+1}–${Math.min(p.total,state.globalOffset+50)}`:'0'} of ${num(p.total)}</span><div style="display:flex;gap:9px"><button class="btn tiny" id="global-prev" ${state.globalOffset===0?'disabled':''}>← Previous</button><button class="btn tiny" id="global-next" ${state.globalOffset+50>=p.total?'disabled':''}>Next →</button></div></div>`;}
function renderGlobalPage(){const src=state.overview.sources.map(x=>x.source);const dom=state.overview.domains.map(x=>x.name);return heading('Source evidence','Evidence search','Search all imported source records across facilities, programs and research categories.')+
 `<div class="filters"><div class="left"><input id="global-search" class="field" aria-label="Search across evidence" placeholder="Keyword, facility, event or record identifier…" value="${attr(state.globalQuery)}"/><select id="global-source" class="select" aria-label="Select evidence source"><option value="">All sources</option>${src.map(x=>`<option value="${attr(x)}" ${x===state.globalSource?'selected':''}>${escapeHTML(x)}</option>`).join('')}</select><select id="global-domain" class="select" aria-label="Select risk category"><option value="">All categories</option>${dom.map(x=>`<option value="${attr(x)}" ${x===state.globalDomain?'selected':''}>${escapeHTML(x)}</option>`).join('')}</select></div></div>`+
  note('Record counts describe analyst research coverage, not facility severity or claims frequency. All entries retain a link to their reported source.',true)+
  panel('Cross-facility evidence',`${num(state.overview.stats.evidence)} curated records in scope`,`<div id="global-evidence-result">${renderGlobalRecords()}</div>`);}
async function loadGlobalEvidence(){const token=++state.requestToken;const p=new URLSearchParams({search:state.globalQuery,source:state.globalSource,domain:state.globalDomain,offset:String(state.globalOffset),limit:'50'});try{const data=await api('evidence?'+p);if(token!==state.requestToken)return;state.globalRecords=data;const target=$('#global-evidence-result');if(target)target.innerHTML=renderGlobalRecords();}catch(e){showToast(e.message);}}

function renderDisclosures(){const rows=state.finance.items.filter(x=>[x.company,x.facility_label,x.finding,x.id].some(v=>String(v||'').toLowerCase().includes(state.disclosureQuery.toLowerCase())));
  const cards=rows.map(r=>`<article class="disclosure-card"><div class="disclosure-top"><div class="card-meta">${pill(r.event_group||'SEC')}${pill(r.facility_id?'Facility linked':'Site attribution pending',!r.facility_id)}<span class="small-muted">${escapeHTML(r.id)}</span></div><span class="small-muted">${escapeHTML(r.filing_date||r.reporting_period||'Undated')}</span></div><h3>${escapeHTML(r.company||'Issuer')} · ${escapeHTML(r.facility_label||'Facility not established')}</h3><p>${escapeHTML(r.finding||'No extract')}</p><div class="disclosure-extra"><div><div class="extra-label">Financial or operational consequence</div><div class="extra-text">${empty(r.financial_impact||r.supply_impact,'No amount or operational consequence stated')}</div></div><div><div class="extra-label">Attribution / caution</div><div class="extra-text">${empty(r.attribution||r.caveats,'Confirm source and facility link')}</div></div></div><div class="card-footer">${link(r.filing_url,'Original SEC filing')}${r.facility_id?`<button class="link-inline" data-site="${attr(r.facility_id)}">Open facility →</button>`:''}</div></article>`).join('');
  return heading('Historical outcomes','SEC disclosures','Issuer disclosures and impact language. Multiple filings can describe the same event.')+
  `<div class="filters"><input id="disclosure-search" class="field" aria-label="Filter SEC disclosures" value="${attr(state.disclosureQuery)}" placeholder="Search company, site, finding or filing ID…"/><span id="disclosure-total" class="results-text">${rows.length} / ${state.finance.total} findings</span></div>`+note('Financial amounts represent distinct disclosure lines—not a summed insured loss. Check event grouping, time period, recovery estimates, and company-vs-site attribution.')+`<div id="disclosure-list" class="disclosure-list">${cards||'<div class="panel empty">No matching findings.</div>'}</div>`;
}
function renderSources(){const src=state.sources.items;let cards=src.map(s=>`<article class="source-card"><div class="label-row"><span class="source-icon">${escapeHTML(initials(s.name))}</span><span class="pill gray">${escapeHTML(s.record_level||'Varied record levels')}</span></div><h3 style="margin-top:16px">${escapeHTML(s.name)}</h3><p>${escapeHTML(shortened(s.uses||s.description,270))}</p><div class="source-footer"><span>${escapeHTML(shortened(s.access_method,68))}</span>${link(s.url,'Source ↗')}</div><p class="note-line"><strong>Matching:</strong> ${escapeHTML(shortened(s.facility_matching,230))}</p><p class="note-line"><strong>Caution:</strong> ${escapeHTML(shortened(s.limitations,230))}</p></article>`).join('');
  return heading('Data inventory','Public data sources','Documented sources, coverage levels, matching requirements and limitations.')+
  note('A source being documented or represented in analyst research does not establish that its live API was connected or refreshed. See Data quality for ingestions.',true)+`<div class="source-grid">${cards}</div>`+
  panel('Imported source labels','The underlying evidence may use different names from the source catalog',`<div class="table-wrap"><table><thead><tr><th>Observed label</th><th>Evidence</th><th>Linked URLs</th><th>Programs</th></tr></thead><tbody>${state.sources.observed_source_labels.map(r=>`<tr><td><strong>${escapeHTML(r.source)}</strong></td><td>${num(r.records)}</td><td>${num(r.linked)}</td><td>${num(r.programs)}</td></tr>`).join('')}</tbody></table></div>`);
}
function renderQuality(){const q=state.quality;let cards=[['Facilities geocoded',`${q.geo_matched}/${q.facilities}`,'Requires property boundary review'],['Facilities with FEI',`${q.with_fei}/${q.facilities}`,'FEI is not EPA FRS ID'],['Linked evidence URLs',`${q.evidence_with_url}/${q.evidence}`,'Citation presence, not link verification'],['Verified availability date',`${q.evidence_with_verified_publication_date}/${q.evidence}`,'Required for predictive backtesting'],['Unmatched SEC findings',num(q.unmatched_sec_findings),'Company disclosures not forced onto a site'],['Future-dated raw values',num(q.future_dated_evidence),'May represent permit expiry / effective dates']];
  let runs=(q.runs||[]).map(r=>`<tr><td><strong>${escapeHTML(r.source)}</strong></td><td>${escapeHTML(r.status)}</td><td>${num(r.imported_count)}</td><td>${escapeHTML(r.finished_at||r.started_at)}</td></tr>`).join('');
  return heading('Evidence governance','Data quality','Review outstanding attribution, temporal coverage and ingestion provenance.')+
  `<div class="qa-grid">${cards.map(x=>`<div class="qa-box"><span class="title">${escapeHTML(x[0])}</span><b>${escapeHTML(x[1])}</b><span>${escapeHTML(x[2])}</span></div>`).join('')}</div>`+
  `${q.integrity_failures.length?note(`Integrity failures: ${q.integrity_failures.join('; ')}`):note('No orphan facility evidence, duplicate FEIs or invalid coordinate ranges detected by the current database checks. This does not verify source accuracy.',true)}`+
  `<div class="qa-lists">${panel('Unmatched disclosures','Not attributed to the 12 imported physical sites',`<div>${(q.unmatched_sec||[]).map(x=>`<div class="qa-line"><strong>${escapeHTML(x.id)}</strong> · ${escapeHTML(shortened(x.facility_label,100))}<br>${escapeHTML(shortened(x.attribution,165))}</div>`).join('')||'<div class="empty">None</div>'}</div>`)}${panel('Missing geolocation','Do not impute coordinates without verification',`<div>${(q.missing_coordinates_facilities||[]).map(x=>`<div class="qa-line"><strong>${escapeHTML(x.name)}</strong><br><span>${escapeHTML(x.id)}</span></div>`).join('')||'<div class="empty">None</div>'}</div>`)} </div>`+
  `<div style="height:18px"></div>${panel('Future-dated records','Check whether these are permit effective/expiry dates, not events',`<div class="panel-body">${(q.future_dated_samples||[]).map(x=>`<div class="qa-line"><strong>${escapeHTML(x.date_raw)}</strong> · ${escapeHTML(x.source)} · ${escapeHTML(x.record_type)}<br><button class="link-inline" data-site="${attr(x.facility_id)}">Open facility →</button></div>`).join('')||'<div class="empty">None at the current as-of date</div>'}</div>`)}<div style="height:18px"></div>${panel('Ingestion history','Completed operations; not all source feeds have been tested live',`<div class="table-wrap"><table><thead><tr><th>Source</th><th>Status</th><th>Rows processed</th><th>UTC completed</th></tr></thead><tbody>${runs||'<tr><td colspan="4">No ingestions recorded.</td></tr>'}</tbody></table></div>`)}`+
  `${panel('Research limitations','Review before actuarial use',`<div class="panel-body">${q.important_caveats.map(x=>`<div class="qa-line">• ${escapeHTML(x)}</div>`).join('')}</div>`)}`;
}
function renderMethodology(){const cards=[['01','Identify physical site','Normalize source names, addresses, FEI and independent identifiers. Similar text is only a candidate match; FEI auto-link requires exact verified ID.'],['02','Retain provenance','Preserve publisher URL, original raw date, evidence scope, matching confidence, limitations and retrieval metadata.'],['03','Separate exposure and incident','A flood-zone intersection, chemical release or nearby earthquake is not a demonstrated insured-property loss.'],['04','Link verified outcomes','Organize SEC findings by event group and reporting period, then verify site attribution and separate gross costs from recoveries.'],['05','Respect time direction','Backtesting requires publication-availability dates preceding the outcome. Never backdate a record merely because it describes an older event.'],['06','Do not calculate a score yet','Coverage count, compliance frequency and environmental releases require exposure denominators, severity definitions and historical loss validation before weighting.']];return heading('Model governance','Assessment methodology','Current prototype is an evidence explorer, not an automated insurance-rating model.')+
  `<div class="method-grid">${cards.map(x=>`<div class="method-card"><span class="step">${x[0]} / PROCESS</span><h3>${escapeHTML(x[1])}</h3><p>${escapeHTML(x[2])}</p></div>`).join('')}</div>`+
  note('Do not make coverage or acceptance decisions using this research prototype. Supplement it with insured asset values, construction, flood/fire protection, production redundancy, historical claims and engineering reports.');}

function renderApprovalQueue(){
  const queue=state.reviewQueue;
  let body='';
  if(!queue)body='<div class="loading-card">Loading independent review proposals…</div>';
  else if(queue.error)body='<div class="empty">'+escapeHTML(queue.error)+'</div>';
  else if(!(queue.items||[]).length)body='<div class="empty">No pending independent identity or coordinate approvals in this private workspace.</div>';
  else body=queue.items.map(r=>{
    let payload={};try{payload=JSON.parse(r.payload_json||'{}');}catch{}
    const source=link(payload.evidence_url,'Corroboration source');
    const requestLabel=r.action==='match_candidate'?'Regulatory crosswalk':r.action==='fei'?'FDA FEI review':'Physical-site location';
    const oldValue=payload.fei||payload.identifier||payload.precision||'Source observation';
    return '<article class="compact-item"><div class="label-row"><b>'+escapeHTML(requestLabel)+'</b>'+pill('Pending second reviewer')+
      '</div><p><strong>Facility:</strong> '+escapeHTML(r.facility_id)+
      ' · <strong>Proposed by:</strong> '+escapeHTML(r.requested_by)+
      ' · <strong>Observed value:</strong> '+escapeHTML(oldValue)+'</p>'+
      '<p class="detail">'+escapeHTML(payload.note||'')+'</p>'+
      '<p class="evidence-meta">'+source+' · '+escapeHTML(r.requested_at)+'</p>'+
      '<label class="small-muted" for="review-note-'+attr(r.id)+'">Independent approval rationale</label>'+
      '<textarea class="field" rows="2" id="review-note-'+attr(r.id)+
      '" data-review-note="'+attr(r.id)+'" placeholder="Document independent validation; minimum 12 characters"></textarea>'+
      '<div class="label-row" style="justify-content:flex-end;gap:8px;padding:10px 0">'+
      '<button class="btn tiny" data-review-action="reject" data-review-id="'+attr(r.id)+'">Reject</button>'+
      '<button class="btn primary tiny" data-review-action="approve" data-review-id="'+attr(r.id)+'">Approve after verification</button></div>'+
      '</article>';
  }).join('');
  return heading('Source governance','Independent approvals',
    'Pending site-identity and coordinate proposals. A separate authenticated approver must corroborate original sources.')+
    note('This is private source-identity governance, not an insurance coverage or risk acceptance approval. Shared service tokens cannot approve.',true)+
    panel('Review queue', 'Approver access required to record a decision',
      '<div class="panel-body"><button class="btn tiny" id="review-refresh">Refresh queue</button></div><div id="approval-results">'+body+'</div>');
}
async function loadApprovalQueue(){
  try{state.reviewQueue=await api('review-approvals?status=pending&limit=100');}
  catch(error){state.reviewQueue={error:error.message,items:[]};}
  if(state.page==='reviews'){const el=$('#approval-results');if(el){
    const next=renderApprovalQueue();
    const doc=document.createElement('div');doc.innerHTML=next;
    const result=doc.querySelector('#approval-results');
    if(result)el.innerHTML=result.innerHTML;
  }}
}
async function decideReview(id,decision){
  const el=$('textarea[data-review-note]').find(x=>x.dataset.reviewNote===id);
  const reason=(el?.value||'').trim();
  if(reason.length<12){showToast('Enter an independent review rationale of at least 12 characters');return;}
  try{
    const response=await fetch('/api/review-approvals/'+encodeURIComponent(id)+'/decide',{
      method:'POST',headers:{'Accept':'application/json','Content-Type':'application/json'},
      body:JSON.stringify({decision,note:reason}),credentials:'same-origin'});
    if(!response.ok){
      const err=await response.json().catch(()=>({}));
      throw Error(String(err.detail||'Approval request rejected')+' (HTTP '+response.status+')');
    }
    const result=await response.json();
    showToast(result.status==='approved'?'Identity evidence approved':'Review decision: '+result.status);
    await loadApprovalQueue();
  }catch(err){showToast(err.message);}
}

function renderPage(){const views={workbench:()=>window.WorkbenchUI.render(),insurance:()=>window.InsuranceUI.render(),'policy-review':()=>window.CoverageReviewUI.render(),'bi-scenarios':()=>window.BIScenarioUI.render(),universal:()=>window.UniversalUI.render(),registry:()=>window.RegistryUI.render(),overview:renderOverview,facilities:renderFacilities,evidence:renderGlobalPage,disclosures:renderDisclosures,reviews:renderApprovalQueue,sources:renderSources,quality:renderQuality,methodology:renderMethodology,
    cases:()=>window.IntelligenceUI.render('cases'),map:()=>window.IntelligenceUI.render('map'),
    identity:()=>window.IntelligenceUI.render('identity'),underwriting:()=>window.IntelligenceUI.render('underwriting'),
    feeds:()=>window.IntelligenceUI.render('feeds')};
  state.page=views[state.page]?state.page:'overview';
  ROOT.innerHTML=views[state.page]();
  $$('.nav-item').forEach(b=>b.classList.toggle('active',b.dataset.page===state.page));
  $('#breadcrumb-page').textContent=({workbench:'ASSESSMENT WORKBENCH',insurance:'INSURANCE OPTIONS','policy-review':'POLICY REVIEW','bi-scenarios':'INTERRUPTION SCENARIOS',universal:'UNIVERSAL FACILITIES',registry:'ALL FACILITIES',overview:'OVERVIEW',facilities:'RESEARCH CASES',evidence:'EVIDENCE SEARCH',disclosures:'SEC DISCLOSURES',sources:'DATA SOURCES',quality:'DATA QUALITY',reviews:'APPROVAL QUEUE',methodology:'METHODOLOGY',cases:'CASE STUDIES',map:'HAZARD MAP',identity:'IDENTITY REVIEW',underwriting:'EXPOSURE PROFILES',feeds:'SOURCE STATUS'})[state.page];
  $('#side-facility-count').textContent=state.facilities.length;
  if(state.page==='evidence'&&!state.globalRecords)loadGlobalEvidence();
  if(state.page==='reviews')loadApprovalQueue();
  if(state.page==='registry'&&window.RegistryUI)window.RegistryUI.mount();
  if(state.page==='universal'&&window.UniversalUI)window.UniversalUI.mount();
  if(state.page==='insurance'&&window.InsuranceUI)window.InsuranceUI.mount();
  if(state.page==='workbench'&&window.WorkbenchUI)window.WorkbenchUI.mount();
  if(state.page==='policy-review'&&window.CoverageReviewUI)window.CoverageReviewUI.mount();
  if(state.page==='bi-scenarios'&&window.BIScenarioUI)window.BIScenarioUI.mount();
  if(window.IntelligenceUI?.pages?.[state.page])window.IntelligenceUI.mount(state.page,{state,api});
}
function siteTab(t,fromRoute=false){if(!ROUTE_TABS.has(t)||!state.facility)return;state.tab=t;if(!fromRoute&&routeableFacility(state.facility))patchRoute({facility:state.facility,tab:t==='summary'?null:t});renderDrawer();DRAWER.scrollTop=0;}
function identityCell(key,value){return `<div class="identity-cell"><label>${escapeHTML(key)}</label><p>${empty(value)}</p></div>`;}
function renderEvidence(e){return `<article class="evidence-row"><div class="evidence-row-top"><div class="card-meta">${pill(e.source)}${pill(e.risk_domain||'Unclassified')}${e.origin?.includes('analyst')?pill('Analyst sourced',true):''}</div><span class="small-muted">${empty(e.date_raw,'Date unknown')}</span></div><h4>${escapeHTML(e.record_type||e.program||'Evidence finding')}</h4><p>${escapeHTML(e.finding||e.value_text||'No text')}</p>${e.value_text&&e.finding?`<p class="note-line">${escapeHTML(shortened(e.value_text,350))}</p>`:''}<div class="evidence-meta"><span>Match: ${empty(e.match_quality)}</span><span>Scope: ${empty(e.evidence_scope)}</span>${e.spatial_distance_km!=null?`<span>Distance: ${Number(e.spatial_distance_km).toFixed(1)} km</span>`:''}<span>Available as of: ${empty(e.availability_date,'Not verified')}</span>${link(e.source_url,'Publisher record')}</div>${e.limitations?`<p class="note-line">${escapeHTML(shortened(e.limitations,300))}</p>`:''}</article>`;}
function renderDrawer(){const d=state.detail;if(!d)return;const f=d.facility;const count=state.facilities.find(x=>x.id===f.id)?.evidence_count||0;
  let body='';
  if(state.tab==='summary'){
    body=`<div class="drawer-lead">${escapeHTML(f.research_summary||'Analyst-researched facility. Evidence coverage is not equivalent to an assessed loss probability.')}</div>`+
    `<div class="identity-grid">${identityCell('Operator / legal name',f.company)}${identityCell('Site activity',f.activity)}${identityCell('Site address',f.address)}${identityCell('FDA FEI',f.fei)}${identityCell('Jurisdiction',f.country)}${identityCell('Location point',f.latitude!=null?`${f.latitude}, ${f.longitude}`:'Not verified')}</div>`+
    `<div class="drawer-section-head"><h3>Recorded domains</h3><button class="link-inline" data-tab="evidence">All evidence →</button></div>`+
    (d.domains||[]).map(x=>`<div class="qa-line"><span>${escapeHTML(x.name)}</span><strong style="float:right">${num(x.records)} records · ${num(x.sources)} source(s)</strong></div>`).join('')+
    `<div class="drawer-section-head"><h3>Research cautions</h3></div><div class="drawer-lead">${escapeHTML(f.data_gaps||'Inspect original records and source coverage before interpreting a missing finding.')}</div>`+
    `<div class="drawer-section-head"><h3>Latest linked evidence</h3><button class="link-inline" data-tab="evidence">Browse all →</button></div>`+(d.latest_evidence||[]).slice(0,4).map(renderEvidence).join('');
  } else if(state.tab==='evidence'){
    const ev=state.evidence;const sources=(d.sources||[]).map(x=>x.source), domains=(d.domains||[]).map(x=>x.name);
    body=`<div class="drawer-filter-row"><input class="field" id="evidence-search" placeholder="Search findings and record IDs…" value="${attr(state.evQuery)}" aria-label="Search evidence"/><select class="select" id="evidence-source" aria-label="Filter evidence by source"><option value="">All sources</option>${sources.map(x=>`<option value="${attr(x)}" ${x===state.evSource?'selected':''}>${escapeHTML(x)}</option>`).join('')}</select><select class="select" id="evidence-domain" aria-label="Filter evidence by domain"><option value="">All domains</option>${domains.map(x=>`<option value="${attr(x)}" ${x===state.evDomain?'selected':''}>${escapeHTML(x)}</option>`).join('')}</select></div><div class="label-row"><span class="small-muted">${num(ev?.total)} matching evidence rows</span><button class="btn tiny" id="export-evidence">Export CSV ↓</button></div>`+
    (ev?.items||[]).map(renderEvidence).join('')+(ev?.items?.length?'':'<div class="empty">No evidence matches these filters.</div>')+
    `<div class="pagination"><span>${ev?.total?`${state.evOffset+1}–${Math.min(state.evOffset+state.evLimit,ev.total)} of ${num(ev.total)}`:'0 matching records'}</span><div style="display:flex;gap:9px"><button class="btn tiny" id="ev-prev" ${state.evOffset===0?'disabled':''}>← Previous</button><button class="btn tiny" id="ev-next" ${!ev||state.evOffset+state.evLimit>=ev.total?'disabled':''}>Next →</button></div></div>`;
  }else if(state.tab==='risk'){
    const r=state.risk||{};const i=r.identifiers||[],haz=r.hazard_checks||[],inc=r.incidents||[];
    const prof=r.profile||{};
    const assets=state.assets?.assets||[];
    const perils=state.assessment?.peril_coverage?.perils||[];
    const exposures=[['Property damage','property_damage'],['Business interruption','business_interruption'],['Environmental / pollution','environmental_liability'],['Supply chain','supply_chain'],['Operational resilience','resilience']];
    body=note('Exposure descriptions are research evidence, not a calibrated rating, engineering survey or insured loss estimate.',true)+
      `<div class="drawer-section-head"><h3>Site and identity checks</h3></div>`+
      `<div class="identity-grid">${identityCell('Location review',r.location?.precision||'Not verified')}${identityCell('FDA FEI validation',i.find(x=>x.namespace==='FDA_FEI'&&x.status==='verified')?'Independently reviewed':'Recorded only / unverified')}${identityCell('EPA FRS match',i.find(x=>x.namespace==='EPA_FRS'&&x.status==='verified')?.identifier||'Not verified')}${identityCell('Match candidates',(r.candidates||[]).filter(x=>x.decision==='pending').length+' awaiting review')}</div>`+
      `<div class="drawer-section-head"><h3>Insurance exposure evidence</h3></div>`+
      exposures.map(([n,k])=>`<div class="compact-item"><b>${escapeHTML(n)}</b><div class="detail">${escapeHTML(prof[k]||'Unknown. No supported assessment entered.')}</div></div>`).join('')+
      `<div class="drawer-section-head"><h3>Physical property inventory</h3></div>`+
      (assets.length?assets.map(a=>`<div class="compact-item"><div class="label-row"><b>${escapeHTML(a.name)}</b>${pill(a.asset_type||'Unclassified')}</div><p class="note-line">${escapeHTML(a.address||'Address not reported')} · ${escapeHTML(a.country||'Country unknown')}</p><div class="detail">Identity: ${escapeHTML(a.status)} · Point: ${escapeHTML(a.coordinate_quality)} · Reported operator: ${escapeHTML(a.reported_operator||'Not supplied')} · Reported parent: ${escapeHTML(a.reported_parent||'Not supplied')}</div><div class="evidence-meta">${link(a.source_url,'Asset source')}</div></div>`).join(''):'<div class="drawer-lead">No separately recorded campus, building, parcel or leased-unit identities. This is not evidence of no exposure.</div>')+

      `<div class="drawer-section-head"><h3>Catastrophe peril coverage</h3></div>`+
      `<p class="note-line">Every peril without a current point-reviewed source classification remains unknown. No loss, premium or insured coverage is inferred.</p>`+
      (perils.length?perils.map(p=>`<div class="compact-item"><div class="label-row"><b>${escapeHTML(p.peril)}</b>${pill(p.status,p.status!=='source_screened')}</div><p class="detail">${escapeHTML(p.interpretation)}</p></div>`).join(''):'<div class="drawer-lead">No private catastrophe source coverage matrix available; do not infer zero exposure.</div>')+
      `<div class="drawer-section-head"><h3>Geographic hazard screening</h3></div>`+
      (haz.length?haz.map(x=>`<div class="compact-item"><div class="label-row"><b>${escapeHTML(x.peril)}</b>${pill(x.status)}</div><p>${escapeHTML(x.description||'')}</p><div class="evidence-meta">${link(x.source_url,'Source layer')} · ${escapeHTML(x.limitations||'')}</div></div>`).join(''):'<div class="drawer-lead">No site-reviewed hazard overlays completed. This is unknown, not lower risk.</div>')+
      `<div class="drawer-section-head"><h3>Confirmed historical events</h3></div>`+
      (inc.length?inc.map(x=>`<div class="compact-item"><div class="label-row"><b>${escapeHTML(x.title)}</b><span>${escapeHTML(x.incident_date)}</span></div><p>${escapeHTML(x.operational_outcome||'')}</p><div class="evidence-meta">${link(x.source_url,'Primary source')} · Publication chronology must be independently checked</div></div>`).join(''):'<div class="drawer-lead">No confirmed event linked to this site. No reported event does not mean no incident occurred.</div>');
  }else{
    body=(d.sec_findings||[]).length?d.sec_findings.map(x=>`<div class="disclosure-card"><div class="label-row">${pill(x.event_group||'SEC')}<span class="small-muted">${escapeHTML(x.filing_date)}</span></div><h3>${escapeHTML(x.finding_type||'Filing finding')}</h3><p>${escapeHTML(x.finding||'')}</p><p class="note-line">${escapeHTML(x.financial_impact||x.supply_impact||'No quantified impact')}</p><p class="note-line">${escapeHTML(x.attribution||x.caveats||'')}</p>${link(x.filing_url,'Original filing')}</div>`).join(''):'<div class="empty">No directly associated SEC disclosure rows. This does not establish no historic incidents.</div>';
  }
  CONTENT.innerHTML=`<div class="drawer-head"><div class="drawer-heading-row"><div><span class="eyebrow">Manufacturing / site profile</span><h2 class="drawer-title">${escapeHTML(f.name)}</h2><p class="drawer-sub">${escapeHTML(f.company)} · ${escapeHTML(countryLabel(f))}</p></div><button class="btn icon-only" id="drawer-close" aria-label="Close facility details">✕</button></div><div class="drawer-stats">${pill(`${num(count)} evidence`)}${pill(`${d.sources?.length||0} source labels`)}${pill(f.fei?'FDA FEI recorded':'FDA FEI missing',!f.fei)}${pill(f.latitude==null?'Site point missing':(f.coordinate_precision||'Site point documented'),f.latitude==null)}</div>${state.reportAvailable?'<a class="btn tiny" target="_blank" rel="noopener noreferrer" href="/api/facilities/'+encodeURIComponent(f.id)+'/assessment.html">Print source assessment ↗</a>':''}</div>`+
  `<div class="drawer-tabs" role="tablist">${[['summary','Facility profile'],['risk','Risk evidence'],['evidence','Evidence explorer'],['disclosures','SEC findings']].map(([v,n])=>`<button data-tab="${v}" role="tab" aria-selected="${state.tab===v?'true':'false'}" class="drawer-tab ${state.tab===v?'active':''}">${n}</button>`).join('')}</div><div class="drawer-body">${body}</div>`;
}
async function openSite(id,{fromRoute=false,tab='summary'}={}){if(!id)return;if(fromRoute&&!routeableFacility(id))return;if(!fromRoute){if(routeableFacility(id))patchRoute({page:state.page,facility:id,tab:null});else patchRoute({facility:null,tab:null},'replace');}try{state.facility=id;state.detail=null;state.risk=null;state.assets=null;state.assessment=null;state.tab=ROUTE_TABS.has(tab)?tab:'summary';state.evQuery='';state.evSource='';state.evDomain='';state.evOffset=0;$('#drawer-backdrop').hidden=false;DRAWER.classList.add('open');DRAWER.setAttribute('aria-hidden','false');document.body.classList.add('drawer-open');CONTENT.innerHTML='<div class="loading-card">Loading facility evidence…</div>';const [d,e,r,report,assets]=await Promise.all([api('facilities/'+encodeURIComponent(id)),api('facilities/'+encodeURIComponent(id)+'/evidence?limit=25'),api('facilities/'+encodeURIComponent(id)+'/intelligence'),api('facilities/'+encodeURIComponent(id)+'/assessment').catch(()=>null),api('facilities/'+encodeURIComponent(id)+'/assets').catch(()=>null)]);if(state.facility!==id)return;state.detail=d;state.evidence=e;state.risk=r;state.assets=assets;state.assessment=report;state.reportAvailable=report?.report_type==='facility_source_evidence_assessment';renderDrawer();}catch(e){showToast(e.message);closeDrawer();if(fromRoute)patchRoute({facility:null,tab:null},'replace');}}
function closeDrawer(){state.facility=null;state.detail=null;DRAWER.classList.remove('open');DRAWER.setAttribute('aria-hidden','true');$('#drawer-backdrop').hidden=true;document.body.classList.remove('drawer-open');}
async function refreshEvidence(){if(!state.facility)return;const params=new URLSearchParams({limit:String(state.evLimit),offset:String(state.evOffset),source:state.evSource,domain:state.evDomain,search:state.evQuery});try{state.evidence=await api(`facilities/${encodeURIComponent(state.facility)}/evidence?${params}`);if(state.tab==='evidence')renderDrawer();}catch(e){showToast(e.message);}}
function showToast(text){const t=$('#toast');t.textContent=text;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),3600);}
function csvEsc(value){let s=String(value==null?'':value).replace(/\r\n?/g,'\n');if(/^[\s\uFEFF]*[=+@-]/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"';}
async function exportEvidence(){if(!state.facility)return;try{const all=[];let offset=0;while(true){const query=new URLSearchParams({limit:'250',offset:String(offset),source:state.evSource,domain:state.evDomain,search:state.evQuery});const page=await api(`facilities/${encodeURIComponent(state.facility)}/evidence?${query}`);all.push(...page.items);offset+=page.items.length;if(offset>=page.total||!page.items.length)break;}
    const fields=['id','facility_id','source','program','date_raw','record_type','finding','value_text','record_ref','evidence_scope','match_quality','risk_domain','source_url','limitations','origin','availability_date','spatial_distance_km'];const data=[fields.join(','),...all.map(r=>fields.map(f=>csvEsc(r[f])).join(','))].join('\r\n');const blob=new Blob(['\ufeff'+data],{type:'text/csv;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`facility-evidence-${state.facility}.csv`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1200);showToast(`${num(all.length)} evidence records exported`);
  }catch(e){showToast('Export failed: '+e.message);}}
function updateFacilityList(){const items=filteredFacilities();$('#facility-result-count').textContent=`${items.length} sites`;$('#facility-cards').innerHTML=items.length?items.map(cardSite).join(''):'<div class="panel empty">No matching facilities.</div>';}
function updateDisclosureList(){renderPage();const el=$('#disclosure-search');if(el){el.focus();el.setSelectionRange(el.value.length,el.value.length);}}
function setupEvents(){window.addEventListener('popstate',restoreLocation);window.addEventListener('facilityrisk:assess-site',e=>{
  if(!e.detail||!window.WorkbenchUI)return;
  window.WorkbenchUI.beginFromSource(e.detail);
  navigateToPage('workbench');
});
document.addEventListener('click',async e=>{
  const pageLink=e.target.closest('[data-page]');
  if(pageLink){
    if(pageLink.tagName==='A'&&(e.button!==0||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey))return;
    e.preventDefault();navigateToPage(pageLink.dataset.page);return;
  }
  if(e.target.closest('[data-site]')){openSite(e.target.closest('[data-site]').dataset.site);return;}
  if(e.target.closest('[data-tab]')){siteTab(e.target.closest('[data-tab]').dataset.tab);return;}
  if(e.target.closest('#drawer-close')||e.target.id==='drawer-backdrop'){if(state.facility){closeDrawer();patchRoute({facility:null,tab:null});}return;}
  if(e.target.closest('#copy-view-link')){
    try{await navigator.clipboard.writeText(window.location.href);showToast(window.PublicRiskAPI&&String(document.getElementById('public-data-label')?.textContent||'').startsWith('Local browser snapshot')?'Page link copied; private imported data is not included':'Link to this view copied');}
    catch{showToast('Copy the URL from your browser address bar');}
    return;
  }
  if(e.target.closest('#ev-prev')){state.evOffset=Math.max(0,state.evOffset-state.evLimit);await refreshEvidence();return;}
  if(e.target.closest('#ev-next')){state.evOffset+=state.evLimit;await refreshEvidence();return;}
  if(e.target.closest('#review-refresh')){await loadApprovalQueue();return;}
  if(e.target.closest('[data-review-action]')){
    const btn=e.target.closest('[data-review-action]');
    await decideReview(btn.dataset.reviewId,btn.dataset.reviewAction);return;
  }
  if(e.target.closest('#export-evidence')){await exportEvidence();return;}
  if(e.target.closest('#global-prev')){state.globalOffset=Math.max(0,state.globalOffset-50);patchRoute({page:'evidence',p:state.globalOffset?String(state.globalOffset/50+1):null});await loadGlobalEvidence();return;}
  if(e.target.closest('#global-next')){state.globalOffset+=50;patchRoute({page:'evidence',p:String(state.globalOffset/50+1)});await loadGlobalEvidence();return;}
});
  document.addEventListener('input',e=>{if(e.target.id==='facility-search'){state.facilityQuery=e.target.value;patchRoute({page:'facilities',q:state.facilityQuery},'replace');updateFacilityList();}
    if(e.target.id==='disclosure-search'){state.disclosureQuery=e.target.value;patchRoute({page:'disclosures',q:state.disclosureQuery},'replace');updateDisclosureList();}
    if(e.target.id==='global-search'){state.globalQuery=e.target.value;state.globalOffset=0;patchRoute({page:'evidence',q:state.globalQuery,p:null},'replace');clearTimeout(window.__globalSearch);window.__globalSearch=setTimeout(loadGlobalEvidence,350);}
    if(e.target.id==='evidence-search'){state.evQuery=e.target.value;state.evOffset=0;clearTimeout(window.__frSearch);window.__frSearch=setTimeout(refreshEvidence,420);}
  });
  document.addEventListener('change',e=>{if(e.target.id==='country-filter'){state.country=e.target.value;patchRoute({page:'facilities',country:state.country});updateFacilityList();}
    if(e.target.id==='evidence-source'){state.evSource=e.target.value;state.evOffset=0;refreshEvidence();}
    if(e.target.id==='evidence-domain'){state.evDomain=e.target.value;state.evOffset=0;refreshEvidence();}
    if(e.target.id==='global-source'){state.globalSource=e.target.value;state.globalOffset=0;patchRoute({page:'evidence',source:state.globalSource,p:null});loadGlobalEvidence();}
    if(e.target.id==='global-domain'){state.globalDomain=e.target.value;state.globalOffset=0;patchRoute({page:'evidence',domain:state.globalDomain,p:null});loadGlobalEvidence();}
  });
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&state.facility){closeDrawer();patchRoute({facility:null,tab:null});}if(e.key==='Enter'&&e.target.matches('tr[data-site],g[data-site]')){e.preventDefault();openSite(e.target.dataset.site);}});
}
async function reloadDataset(){try{const [overview,facilities,sources,finance,quality]=await Promise.all([api('overview'),api('facilities?limit=500'),api('sources'),api('financial'),api('quality')]);Object.assign(state,{overview,facilities:facilities.items,sources,finance,quality});const route=readRoute();routeFilters(route);state.page=route.page;closeDrawer();renderPage();if(route.facility)await openSite(route.facility,{fromRoute:true,tab:route.tab});}catch(e){ROOT.innerHTML=`<section class="loading-card"><h2>Unable to load research data</h2><p class="subhead">${escapeHTML(e.message)}</p><p class="subhead">${window.PublicRiskAPI?'Check the published static dataset or selected JSON file.':'Initialize the database and import the analyst workbook, then refresh this page.'}</p></section>`;}}
async function init(){setupEvents();window.addEventListener('facilityrisk:dataset-changed',reloadDataset);await reloadDataset();}
init();