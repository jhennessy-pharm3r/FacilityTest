/* FDA-wide facility catalog and unsourced investigation intake.
   No site is rated merely because it appears in an FDA registry. */
(() => {
 'use strict';
 const script=document.getElementById('registry-ui-script');
 const catalogURL=new URL('./registry/catalog.json',script?.src||document.baseURI);
 const irelandURL=new URL('./registry/ireland-leap.json',script?.src||document.baseURI);
 const canadaURL=new URL('./registry/canada-npri.json',script?.src||document.baseURI);
 const sourceSearch='https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRL/rl.cfm';
 const drugSearch='https://www.fda.gov/drugs/drug-approvals-and-databases/drug-establishments-current-registration-site-decrs';
 const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const fmt=n=>Number(n||0).toLocaleString('en-US');
 let catalogPromise=null,query='',sector='',source='',country='',page=0,result=[],selected=null,meta=null,error='';
 let liveOnly=false,manualVisible=false,sourceMessage='';
 const perPage=35;
 const cache=new Map();
 let debounce=null, searchGeneration=0;
 function normalize(v){return String(v||'').normalize('NFKD').toLowerCase();}

 function readRegistryRoute(){
   const p=new URL(window.location.href).searchParams;
   const index=Number(p.get('p')||'1');
   return {query:(p.get('q')||'').slice(0,200),sector:(p.get('sector')||'').slice(0,80),
     source:(p.get('source')||'').slice(0,160),country:(p.get('country')||'').slice(0,2).toUpperCase(),
     page:Number.isSafeInteger(index)&&index>=1&&index<=100000?index:1,
     record:(p.get('record')||'').slice(0,200)};
 }
 function writeRegistryRoute(method='push'){
   window.FacilityRiskRouter?.patch({page:'registry',q:query,sector,source,country,
     p:page>0?String(page+1):null,record:selected?.id||null},method);
 }
 async function restoreRoute(){
   const root=document.getElementById('registry-root');if(!root)return;
   const route=readRegistryRoute();
   query=route.query;sector=route.sector;source=route.source;country=route.country;
   for(const [id,value] of [['registry-query',query],['registry-sector',sector],
       ['registry-source',source],['registry-country',country]]){
     const input=document.getElementById(id);if(input)input.value=value;
   }
   clearTimeout(debounce);
   await search(route.page,route.record);
 }

 function catalog(){
   if(!catalogPromise){
     catalogPromise=(async()=>{
       const response=await fetch(catalogURL,{cache:'no-store'});
       if(!response.ok)throw Error('FDA catalog HTTP '+response.status);
       const d=await response.json();
       if(d?.schema_version!=='1.0'||!Array.isArray(d.rows)||!Array.isArray(d.fields))
         throw Error('Unsupported FDA catalog format');
       try{
         const second=await fetch(irelandURL,{cache:'no-store'});
         if(!second.ok)throw Error('Ireland EPA HTTP '+second.status);
         const ie=await second.json();
         if(ie?.schema_version!=='1.0'||!Array.isArray(ie.rows)||
            JSON.stringify(ie.fields)!==JSON.stringify(d.fields))
             throw Error('Ireland EPA catalog schema mismatch');
         d.rows=d.rows.concat(ie.rows);
         d.sources={...d.sources,...ie.sources};
         const counts={...(d.summary?.country_counts||{})};
         for(const [code,n] of Object.entries(ie.summary?.country_counts||{}))
           counts[code]=(counts[code]||0)+Number(n||0);
         d.summary={...d.summary,country_counts:counts,
           countries:Object.keys(counts).length,distinct_source_entities:d.rows.length};
         d.ireland_generated_at=ie.generated_at;
       }catch(err){
         d.sources={...d.sources,ireland_leap:{status:'unavailable',
           reason:String(err.message||err),
           url:'https://data.epa.ie/leap/api/v1/LicenceProfile/list'}};
       }
       try {
         const response=await fetch(canadaURL,{cache:'no-store'});
         if(!response.ok)throw Error('Canada NPRI HTTP '+response.status);
         const ca=await response.json();
         if(ca?.schema_version!=='1.0'||!Array.isArray(ca.rows)||
            JSON.stringify(ca.fields)!==JSON.stringify(d.fields))
           throw Error('Canadian NPRI catalog schema mismatch');
         const seen=new Set(d.rows.map(row=>row[0]));
         for(const row of ca.rows){
           if(seen.has(row[0]))throw Error('Duplicate identity key between independent catalogs');
           seen.add(row[0]);
         }
         d.rows=d.rows.concat(ca.rows);
         d.sources={...d.sources,...ca.sources};
         const counts={...(d.summary?.country_counts||{})};
         for(const [code,n] of Object.entries(ca.summary?.country_counts||{}))
           counts[code]=(counts[code]||0)+Number(n||0);
         d.summary={...d.summary,country_counts:counts,
            countries:Object.keys(counts).length,
            distinct_source_entities:d.rows.length};
         d.canada_generated_at=ca.generated_at;
       }catch(err){
         d.sources={...d.sources,canada_npri:{
           status:'unavailable',reason:String(err.message||err),
           url:'https://maps-cartes.ec.gc.ca/arcgis/rest/services/STB_DGST/NPRI/MapServer/0'}};
       }
       meta=d;return d;
     })().catch(err=>{catalogPromise=null;throw err;});
   }
   return catalogPromise;
 }
  function createSite(row,fields){return Object.fromEntries(fields.map((key,i)=>[key,row[i]]));}
 function match(row,fields,words){
   const parts=['name','company','address','city','state','country','fei','registration_number','source','activities'];
   const values=parts.map(k=>normalize(row[fields.indexOf(k)]));
   return words.every(w=>values.some(v=>v.includes(w)));
 }
 function sourceText(c){
   const labels={fda_device:'Medical device',fda_drug:'Pharmaceutical',ireland_leap:'Ireland EPA licences',canada_npri:'Canada NPRI reporters'};
   return Object.entries(c.sources||{}).map(([key,src])=>
      `${labels[key]||key}: ${src.status||'unknown'}${src.reason?' ('+src.reason+')':''}`).join(' · ');
 }
  function render(){
   return `<div class="page-heading"><div><div class="eyebrow">GLOBAL ESTABLISHMENT DISCOVERY</div><h1>All registered facilities</h1><p class="subhead">Search FDA establishments, Ireland EPA licences and Canada's NPRI reporting facilities by company, site, FEI, source ID or location.</p></div></div>
     <div class="registry-lead"><div><strong>Search official regulatory identities</strong><span>FDA registrations, Irish EPA licences and Canada NPRI reports are separate regulatory populations. Source records are not verified manufacturing properties or insurance risk ratings.</span></div><a href="${sourceSearch}" target="_blank" rel="noopener noreferrer">FDA device registry ↗</a></div>
     <section class="panel registry-panel">
       <div class="registry-controls">
         <input id="registry-query" class="field registry-search" placeholder="Example: Baxter, Pfizer, Medtronic, 3002808212 or Galway" aria-label="Search facility and licence identities" value="${esc(query)}" autocomplete="off">
         <select id="registry-sector" class="select" aria-label="Product sector"><option value="">All sectors</option><option value="Medical device" ${sector==='Medical device'?'selected':''}>Medical devices</option><option value="Pharmaceutical" ${sector==='Pharmaceutical'?'selected':''}>Pharmaceutical</option><option value="Environmental licence" ${sector==='Environmental licence'?'selected':''}>Environmental licences</option><option value="Environmental reporting" ${sector==='Environmental reporting'?'selected':''}>Environmental reporting</option></select>
         <select id="registry-source" class="select" aria-label="Regulatory source"><option value="">All official sources</option>${[['FDA device registration / listing','FDA device'],['FDA drug establishment (DECRS)','FDA drug'],['Ireland EPA LEAP','Ireland EPA licences'],['Canada NPRI','Canada NPRI reporters']].map(([value,label])=>`<option value="${esc(value)}" ${source===value?'selected':''}>${esc(label)}</option>`).join('')}</select>
         <input id="registry-country" class="field registry-country" maxlength="2" placeholder="Country (e.g. US)" aria-label="Filter by two-letter ISO country code" value="${esc(country)}">
         <button class="btn primary" id="registry-search-button">Search</button>
       </div>
       <div class="registry-status" id="registry-status">Opening full facility catalog…</div>
       <div id="registry-results"><div class="empty">Loading available FDA, Irish EPA and Canadian NPRI records…</div></div>
     </section>
     <section class="panel registry-manual-panel">
       <div class="panel-header"><div><h2>Facility not in the registry?</h2><span class="overline">You can start an investigation for any named facility. Its identity and hazard records remain unverified.</span></div><button class="btn tiny" id="registry-manual-toggle">${manualVisible?'Hide':'Create research entry'}</button></div>
       <div id="registry-manual-form" class="registry-manual" ${manualVisible?'':'hidden'}>
        <div class="registry-manual-grid"><label>Facility / site name<input id="registry-manual-name" class="field" maxlength="160" placeholder="Enter physical facility name"></label><label>Company / operator<input id="registry-manual-company" class="field" maxlength="160" placeholder="Legal operator if known"></label><label>Country<input id="registry-manual-country" class="field" maxlength="80" placeholder="Country"></label><label>City<input id="registry-manual-city" class="field" maxlength="120" placeholder="City"></label><label>Street address<input id="registry-manual-address" class="field" maxlength="240" placeholder="Address, if known"></label></div><p class="registry-caveat">Manual records stay in this browser session. The app will not infer a verified coordinate, company ownership, or risk status from a name.</p><button class="btn primary" id="registry-add-manual">Create unverified investigation</button>
       </div>
     </section>`;
 }
 function updateStatus(){const el=document.getElementById('registry-status');if(!el)return;
  if(error){el.textContent=error;el.classList.add('registry-error');return;}
  el.classList.remove('registry-error');
  if(!meta){el.textContent='Opening establishment catalog…';return;}
  const count=meta.summary?.distinct_source_entities??meta.rows?.length??0;
  const d=meta.generated_at?new Date(meta.generated_at).toLocaleDateString('en-US'):'Not yet populated';
  const drug=meta.summary?.field_coverage_by_sector?.Pharmaceutical;
  const missing=drug?` · Pharma: ${fmt(drug.with_reported_address)}/${fmt(drug.source_identities)} with reported address; ${fmt(drug.with_structured_country)} with a recognized country (${fmt(drug.with_source_country_field||0)} official country fields, ${fmt(drug.with_explicit_address_country||0)} explicit country suffixes)`:'';
  el.textContent=`${fmt(count)} separate regulatory source identities · ${fmt(meta.summary?.countries)} country codes observed · FDA catalog: ${d} · ${sourceText(meta)}${missing}. Missing or ambiguous country must never default to U.S. location; registration is not a verified plant or risk score.`;
 }
 function sourceLink(r){
   if(r.source==='Ireland EPA LEAP' && /^[A-Z][A-Z0-9-]{2,40}$/.test(r.registration_number||''))return 'https://leap.epa.ie/licence-profile/'+encodeURIComponent(r.registration_number);
   if(r.source==='Canada NPRI' && /^\d+$/.test(r.registration_number||'')){
     const where=encodeURIComponent('NpriID='+r.registration_number);
     return 'https://maps-cartes.ec.gc.ca/arcgis/rest/services/STB_DGST/NPRI/MapServer/0/query?where='+where+'&outFields=*&returnGeometry=false&f=pjson';
   }
   if(r.sector==='Pharmaceutical')return drugSearch;
   if(r.fei) return `https://api.fda.gov/device/registrationlisting.json?search=registration.fei_number:${encodeURIComponent(r.fei)}&limit=1`;
   if(r.registration_number)return `https://api.fda.gov/device/registrationlisting.json?search=registration.registration_number:${encodeURIComponent(r.registration_number)}&limit=1`;
   return sourceSearch;
 }
 function rowCard(r){return `<button class="registry-record" data-reg-id="${esc(r.id)}" type="button">
    <div class="registry-record-head"><strong>${esc(r.name)}</strong><span class="pill">${esc(r.sector)}</span></div>
    <p class="registry-record-sub">${esc(r.company||'Operator not recorded')} · ${esc([r.city,r.state,r.country].filter(Boolean).join(', ')||'Location not recorded')}</p>
    <div class="registry-record-meta"><span>${r.source==='Canada NPRI'?'NPRI reporter ID: '+esc(r.registration_number):r.source==='Ireland EPA LEAP'?'EPA licence: '+esc(r.registration_number):r.fei?'FDA FEI observed: '+esc(r.fei):'FDA FEI not asserted'}</span><span>${esc(r.activities||'Establishment activity unspecified')}</span><span class="registry-record-link">Inspect →</span></div>
   </button>`;}
 function resultsHTML(){
   if(error)return `<div class="empty">${esc(error)}</div>`;
   if(!result.length)return `<div class="empty">${meta?.rows?.length?'No matching identities in the available regulatory source catalogs.':'The downloadable registry has not been populated.'} Absence is not evidence the facility does not exist. Try another name, official lookup, or create a research entry.</div>`;
   return `<div class="registry-count">${fmt(result.length)} matched source identities · showing ${fmt(page*perPage+1)}–${fmt(Math.min(result.length,(page+1)*perPage))}</div><div class="registry-list">${result.slice(page*perPage,(page+1)*perPage).map(rowCard).join('')}</div><div class="registry-pagination"><button class="btn tiny" id="registry-prev" ${page===0?'disabled':''}>← Previous</button><span>Page ${page+1} of ${Math.ceil(result.length/perPage)}</span><button class="btn tiny" id="registry-next" ${(page+1)*perPage>=result.length?'disabled':''}>Next →</button></div>`;
 }
 async function search(requestedPage=1,record=''){
   const root=document.getElementById('registry-results');if(!root)return;
   const generation=++searchGeneration;
   if(query.trim().length===1){result=[];page=0;root.innerHTML='<div class="empty">Use at least two characters to search, or clear the field to browse every entry.</div>';return;}
   error='';root.innerHTML='<div class="empty">Opening official source records…</div>';
   try {
     const d=await catalog();
     if(generation!==searchGeneration)return;
     const words=normalize(query).split(/\s+/).filter(Boolean),ids=[],rows=d.rows,fields=d.fields;
     for(let i=0;i<rows.length;i++){
       const x=rows[i];if(sector&&x[fields.indexOf('sector')]!==sector)continue;
       if(source&&x[fields.indexOf('source')]!==source)continue;
       if(country&&normalize(x[fields.indexOf('country')])!==normalize(country))continue;
       if(match(x,fields,words))ids.push(i);
     }
     result=ids.map(i=>createSite(rows[i],fields));
     result.sort((a,b)=>{
       const q=normalize(query);
       const rankSource=x=>x.source==='FDA device registration / listing'?0:x.source==='FDA drug establishment (DECRS)'?1:x.source==='Ireland EPA LEAP'?2:3;
       if(!q)return rankSource(a)-rankSource(b)||a.name.localeCompare(b.name);
       const rank=x=>normalize(x.fei)===q?0:normalize(x.registration_number)===q?0:normalize(x.name).startsWith(q)?1:normalize(x.company).startsWith(q)?2:3;
       return rank(a)-rank(b)||rankSource(a)-rankSource(b)||a.name.localeCompare(b.name);
     });
    page=Math.min(Math.max(0,requestedPage-1),Math.max(0,Math.ceil(result.length/perPage)-1));
    selected=null;
    const detail=document.getElementById('registry-detail-container');if(detail)detail.innerHTML='';
    root.innerHTML=resultsHTML();updateStatus();
    if(record)showDetail(record,false);
     if(!rows.length&&query.trim().length>=2)await liveFallback();
   }catch(e){error='Catalog not yet available: '+e.message+'. Official live lookup is being attempted.';updateStatus();await liveFallback();}
 }
 async function liveFallback(){
   const el=document.getElementById('registry-results');if(!el)return;
   const term=query.trim();if(term.length<2)return;
   const search=term.match(/^\d{7,10}$/)?`registration.fei_number:${term}`:`registration.name:"${term.replace(/["\\]/g,'')}"`;
   const u=new URL('https://api.fda.gov/device/registrationlisting.json');u.searchParams.set('search',search);u.searchParams.set('limit','35');
   try{
     const controller=new AbortController();const stop=setTimeout(()=>controller.abort(),13000);
     let r;try{r=await fetch(u,{signal:controller.signal});}finally{clearTimeout(stop);}
     if(!r.ok)throw Error('FDA returned HTTP '+r.status);
     const d=await r.json();const found=new Map();
     for(const raw of d.results||[]){const o=raw.registration||{};if(!o.name)continue;
       const fei=String(o.fei_number||'');const id='device-api-'+(fei||o.registration_number||o.name);
       found.set(id,{id,name:o.name,company:o.owner_operator?.firm_name||o.name,city:o.city,state:o.state_code,country:o.iso_country_code,fei,
        registration_number:o.registration_number,activities:(raw.establishment_type||[]).join('; '),sector:'Medical device',address:o.address_line_1||'',
        source:'FDA device registration API (live result)',source_records:1});}
     result=[...found.values()].filter(x=>(!sector||sector==='Medical device')&&(!country||normalize(x.country)===normalize(country)));
     page=0;error='';sourceMessage='Live FDA query: only the first 35 device-registration records, not the full catalog. Drug establishments unavailable in this fallback.';
     el.innerHTML=`<p class="registry-status">${esc(sourceMessage)}</p>${resultsHTML()}`;
   }catch(err){el.innerHTML=`<div class="empty">The full catalog is not ready, and direct FDA lookup could not complete (${esc(err.message)}). <a target="_blank" rel="noopener noreferrer" href="${esc(sourceSearch)}">Search the official FDA database</a> or create a manual investigation entry below.</div>`;}
 }
 function detailHTML(r){const conflict=(meta?.identity_conflicts||[]).find(x=>x.id===r.id);
  const conflictWarning=conflict?`<div class="registry-risk-warning"><strong>Possible site-identity conflict.</strong> Official source values differ: ${esc(Object.entries(conflict.conflicting_fields).map(([k,v])=>k+": "+v.join(" / ")).join(" · "))}. Review the physical address and operator before assuming one site.</div>`:"";
  return `<section class="panel registry-detail"><div class="panel-header"><div><h2>${esc(r.name)}</h2><span class="overline">${esc(r.sector)} · ${esc(r.source)} source identity (not independently site-matched)</span></div><button class="btn tiny" id="registry-close-detail">Close</button></div>
   <div class="registry-detail-body"><div class="registry-detail-grid">${[
     ['Reported operator',r.company],['Registered address',[r.address,r.city,r.state,r.country].filter(Boolean).join(', ')],
     ['Observed FDA FEI',r.fei],[r.source==='Canada NPRI'?'Canada NPRI ID':r.source==='Ireland EPA LEAP'?'Irish EPA licence profile':r.sector==='Pharmaceutical'?'Other source ID / DUNS':'Registration number',r.registration_number],['Recorded operations',r.activities],
     ['Expiry / validity field',r.expiry_year],['Source listing records',r.source_records],['Environmental and physical hazard score','Not assessed']
   ].map(([k,v])=>`<div><small>${esc(k)}</small><b>${esc(v||'Not recorded')}</b></div>`).join('')}</div>
     ${conflictWarning}
     <div class="registry-risk-warning">Registration or licensing does not verify the property boundary, active manufacturing status, environmental compliance, hazard exposure, or insurance loss likelihood. These require independent source matching and location review.</div>
     <div class="registry-actions"><button class="btn primary" id="registry-assess">Assess insurance exposure →</button><a class="btn" target="_blank" rel="noopener noreferrer" href="${esc(sourceLink(r))}">View official source ↗</a><button class="btn primary" id="registry-track" data-reg-track="${esc(r.id)}">Add to research workspace</button></div>
    </div></section>`;}
 function showDetail(id,scroll=true){selected=result.find(r=>r.id===id)||null;const root=document.getElementById('registry-detail-container');if(!root)return;
   root.innerHTML=selected?detailHTML(selected):(id?'<div class="registry-risk-warning">This source identity is unavailable within the currently published catalog and filters. Missing does not mean low risk.</div>':'');
   if(selected&&scroll)root.scrollIntoView({block:'nearest',behavior:'smooth'});
 }
 async function track(data){
   if(window.PublicRiskAPI?.addFacility){
     const id=await window.PublicRiskAPI.addFacility(data);
     alert('Added as an unverified research entry to this browser session. No automatic risk rating or site match was created.');
     return id;
   }
   if(data.source==='Ireland EPA LEAP' || data.source==='Canada NPRI'){
     const r=await fetch('/api/facilities/intake',{method:'POST',
       headers:{'Content-Type':'application/json'},
       body:JSON.stringify({name:data.name,company:data.company,country:data.country,
           city:data.city,state:data.state,sector:data.sector,source_url:sourceLink(data)})});
     if(!r.ok)throw Error('Research intake unavailable: '+(await r.text()).slice(0,180));
     alert('Regulatory source observation opened as an unverified research entry. No plant identity or risk status has been confirmed.');
     return (await r.json()).facility_id;
   }
   if(data.id?.startsWith('manual-')){
     const r=await fetch('/api/facilities/intake',{method:'POST',
       headers:{'Content-Type':'application/json'},
       body:JSON.stringify({name:data.name,company:data.company,country:data.country,
         city:data.city,address:data.address,sector:data.sector})});
     if(!r.ok)throw Error('Manual intake unavailable: '+(await r.text()).slice(0,180));
     alert('Unverified site saved to the private research workspace. No risk score was assigned.');
     return (await r.json()).facility_id;
   }
   const r=await fetch('/api/registry/'+encodeURIComponent(data.id)+'/track',{method:'POST'});
   if(!r.ok){let msg=await r.text();throw Error('Tracking not enabled on the private server: '+msg.slice(0,150));}
   alert('Created an unverified research workspace entry.');
   return (await r.json()).facility_id;
 }
 async function addManual(){const val=id=>(document.getElementById(id)?.value||'').trim();const name=val('registry-manual-name');if(name.length<3){alert('A physical facility name is required.');return;}
   const country=val('registry-manual-country'),city=val('registry-manual-city'),company=val('registry-manual-company')||name,address=val('registry-manual-address');
   const data={id:'manual-'+String(Date.now()),name,company,city,country,address,sector:'Unspecified',fei:'',activities:'Not assessed',source:'Manual investigation request (unverified)',registration_number:''};
   try{await track(data);}catch(e){alert(e.message);}
 }
 async function mount(){
   const root=document.getElementById('registry-root');if(!root)return;
   root.insertAdjacentHTML('beforeend','<div id="registry-detail-container"></div>');
   root.addEventListener('click',async e=>{
     const id=e.target.closest('[data-reg-id]')?.dataset.regId;
     if(id){showDetail(id);if(selected)writeRegistryRoute();return;}
     if(e.target.closest('#registry-search-button')){query=(document.getElementById('registry-query')?.value||'').trim();sector=document.getElementById('registry-sector')?.value||'';source=document.getElementById('registry-source')?.value||'';country=(document.getElementById('registry-country')?.value||'').trim().toUpperCase();page=0;selected=null;writeRegistryRoute();await search();return;}
     if(e.target.closest('#registry-prev')){page=Math.max(0,page-1);selected=null;document.getElementById('registry-detail-container').innerHTML='';document.getElementById('registry-results').innerHTML=resultsHTML();writeRegistryRoute();return;}
     if(e.target.closest('#registry-next')){page=Math.min(Math.ceil(result.length/perPage)-1,page+1);selected=null;document.getElementById('registry-detail-container').innerHTML='';document.getElementById('registry-results').innerHTML=resultsHTML();writeRegistryRoute();return;}
     if(e.target.closest('#registry-close-detail')){selected=null;document.getElementById('registry-detail-container').innerHTML='';writeRegistryRoute();return;}
     if(e.target.closest('#registry-assess')&&selected){
       window.dispatchEvent(new CustomEvent('facilityrisk:assess-site',{detail:{...selected,source_url:sourceLink(selected)}}));return;
     }
     if(e.target.closest('#registry-track')&&selected){try{await track(selected);}catch(e){alert(e.message);}return;}
     if(e.target.closest('#registry-manual-toggle')){manualVisible=!manualVisible;const x=document.getElementById('registry-manual-form');x.hidden=!manualVisible;e.target.textContent=manualVisible?'Hide':'Create research entry';return;}
     if(e.target.closest('#registry-add-manual')){await addManual();return;}
   });
   root.addEventListener('keydown',async e=>{if(e.key==='Enter'&&e.target.id==='registry-query'){e.preventDefault();document.getElementById('registry-search-button')?.click();}});
   root.addEventListener('input',e=>{if(e.target.id!=='registry-query')return;
     clearTimeout(debounce);debounce=setTimeout(()=>{if(root.isConnected)root.querySelector('#registry-search-button')?.click();},600);
   });
   try{await catalog();updateStatus();await restoreRoute();}
   catch(e){error='Full FDA catalog download has not completed: '+e.message;updateStatus();}
 }
 const pages={registry:true};
 window.RegistryUI={render:()=>`<div id="registry-root">${render()}</div>`,mount,restoreRoute,pages};
})();