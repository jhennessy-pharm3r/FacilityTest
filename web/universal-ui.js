/* Private indexed all-industry search. Source identities are NOT verified properties. */
(()=>{
'use strict';
const esc=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const https=u=>typeof u==='string'&&/^https:\/\/[^\s/]+/i.test(u)?u:'';
let q='',country='',industry='',source='',page=0,selected=null,wired=false,sourceInitialized=false;
function render(){
return '<div class="page-heading"><div><div class="eyebrow">ALL INDUSTRIES / SOURCE-REPORTED FACILITIES</div><h1>Universal facility discovery</h1>'+
 '<p class="subhead">Search cross-industry source identities before investigating insurance exposure. An EPA, FDA, NPRI or place record is not automatically a verified building or insured property.</p></div></div>'+
(window.PublicRiskAPI
 ? '<section class="panel"><div class="panel-body"><strong>Complete all-industry search requires the private backend with its full source index.</strong><p>This public preview hosts a smaller FDA, Ireland EPA and Canada NPRI registry. The nationwide EPA FRS index is not hosted on GitHub Pages. No absence-of-risk conclusion can be drawn from the smaller preview.</p><button class="btn primary" data-page="registry">Browse available public source identities</button></div></section>'
 : '<section class="panel"><div class="panel-header"><h2>Find facility source identities</h2></div><div class="panel-body"><p class="note-line">Search names, companies, source identifiers and jurisdictions. Select a source/industry to narrow the universe; every match remains unassessed until the actual physical site is reviewed.</p></div>'+
 '<form id="uf-form" class="registry-controls" autocomplete="off">'+
 '<input id="uf-q" class="field registry-search" value="'+esc(q)+'" placeholder="Facility name, company, source ID or location" aria-label="Facility search terms"/>'+
 '<input id="uf-country" class="field" value="'+esc(country)+'" maxlength="8" placeholder="Country ISO (optional)" aria-label="Country ISO filter"/>'+
 '<input id="uf-industry" class="field" value="'+esc(industry)+'" maxlength="120" placeholder="Industry / NAICS exact code" aria-label="Industry or NAICS exact filter"/>'+
 '<select id="uf-source" class="select" aria-label="Source data catalog"><option value="">Private workspace sources</option></select>'+
 '<button class="btn primary" type="submit">Search all indexed sources</button><button class="btn" id="uf-clear" type="button">Clear</button></form>'+
 '<div id="uf-status" class="registry-status" role="status">Checking private indexed records...</div>'+
 '<div id="uf-results"></div><div id="uf-detail"></div></section>');
}
function optionText(value){return String(value||'').replace(/_/g,' ')}
function fillSources(stats){
 const s=document.getElementById('uf-source');if(!s)return;
 s.innerHTML='<option value="">Private workspace source identities</option>'+
  (stats.sources||[]).map(row=>'<option value="'+esc(row.source_key)+'"'+
   (source===row.source_key?' selected':'')+'>'+
   esc(row.source_key==='EPA_FRS'&&row.storage==='readonly_national_index'?'EPA FRS national source index':optionText(row.source_key))+
   ' ('+Number(row.records||0).toLocaleString()+')</option>').join('');
}
async function load(){
 const results=document.getElementById('uf-results');if(!results)return;
 const status=document.getElementById('uf-status');
 if(status)status.textContent='Searching the private source index...';
 try{
 const s=await fetch('/api/universal-facilities/stats',{cache:'no-store'});
 if(!s.ok)throw Error('Private facility statistics unavailable or require authentication');
 const stats=await s.json();
 if(!sourceInitialized){
   sourceInitialized=true;
   if(!source&&['ready_full','ready_partial'].includes(stats.national_index?.state)){
     source='EPA_FRS';
   }
 }
 fillSources(stats);
 const params=new URLSearchParams({q,country,industry,source,limit:'50',offset:String(page*50)});
 const r=await fetch('/api/universal-facilities?'+params,{cache:'no-store'});
 if(!r.ok)throw Error('Selected source index is not mounted, validated or accessible');
 const data=await r.json();
 selected=null;const detail=document.getElementById('uf-detail');if(detail)detail.innerHTML='';
 const national=data.index==='EPA_FRS'&&stats.national_index;
 if(status)status.textContent=Number(data.total||0).toLocaleString()+
  ' matching source-site candidates · '+
  Number(national?stats.national_index.site_candidates:stats.site_candidates||0).toLocaleString()+
  (national?' EPA national reporting identities':' workspace source-site candidates')+
  ' · Snapshot scope: '+(national?'EPA FRS U.S. reported sites':'imported private workspace sources')+
  '. Records are neither a complete world facility census nor insured/geocode-verified properties.';
 const rows=(data.items||[]).map(x=>
  '<article class="registry-record" style="display:block"><div class="label-row"><strong>'+
  esc(x.name)+'</strong><span class="small-muted">'+esc(x.coordinate_quality||'unassessed')+'</span></div>'+
  '<p class="registry-record-sub">'+esc(x.company||'Operator not established')+' · '+
  esc([x.address,x.city,x.state,x.country].filter(Boolean).join(', ')||'Location not reported')+'</p>'+
  '<p class="note-line">Sector: '+esc(x.industry||'Unclassified')+' · '+
  Number(x.source_identity_count||0)+' linked source record(s); independent property verification required</p>'+
  '<button class="btn tiny" data-uf-id="'+esc(x.id)+'">Inspect provenance &amp; assess</button></article>').join('');
 results.innerHTML=(rows?'<div class="registry-list">'+rows+'</div>':
  '<div class="empty">No matching source records. This does not imply there is no facility: add it through private facility intake if appropriate.</div>')+
  '<div class="registry-pagination"><button id="uf-prev" class="btn tiny" '+
  (page?'':'disabled')+'>Previous</button><span>Page '+(page+1)+' · '+
  Number(data.total||0).toLocaleString()+' matching source-site candidates</span>'+
  '<button id="uf-next" class="btn tiny" '+((page+1)*50>=data.total?'disabled':'')+'>Next</button></div>';
 }catch(error){
   if(status)status.textContent='Private index unavailable; no claim about worldwide facility coverage can be made.';
   results.innerHTML='<div class="empty">'+esc(error.message)+'. Check your authenticated backend, import provenance and current source cohort.</div>';
 }
}
async function inspect(id){
 const el=document.getElementById('uf-detail');if(!el)return;
 try{
 const res=await fetch('/api/universal-facilities/'+encodeURIComponent(id),{cache:'no-store'});
 if(!res.ok)throw Error('Selected source-site identity is not accessible');
 const data=await res.json();selected=data;
 const provenance=(data.source_identities||[]).map(x=>{
   const safe=https(x.source_url);
   return '<li><strong>'+esc(x.source_key)+'</strong> / '+esc(x.source_identifier)+
     ' · vintage '+esc(x.vintage||'not reported')+
     ' · last ingested '+esc(x.last_imported||'unknown')+
     (safe?' · <a href="'+esc(safe)+'" target="_blank" rel="noopener noreferrer">Publisher source</a>':'')+'</li>';
 }).join('');
 el.innerHTML='<section class="panel"><div class="panel-header"><h2>'+esc(data.site.name)+'</h2></div>'+
  '<div class="panel-body"><p>Source-reported sector: '+esc(data.site.industry||'Unknown')+'</p>'+
  '<p>Coordinate evidence: '+esc(data.site.coordinate_quality||'not verified')+
  ' · Risk status: '+esc(data.risk_status||'unassessed')+
  ' · Insurance coverage: '+esc(data.insured_coverage_status||'unknown')+'</p>'+
  '<p class="note-line">Registration or place coordinates are not independently verified property points. Hazard layers, underwriting scores and policy protection are not inferred.</p>'+
  '<h3>Original source identifiers</h3><ul>'+provenance+'</ul>'+
  '<div class="registry-actions"><button class="btn" id="uf-assess">Start insurance exposure workbench</button>'+
  '<button class="btn primary" id="uf-track">Add to private research workspace</button></div>'+
  '<div id="uf-track-status" class="registry-status"></div></div></section>';
 el.scrollIntoView({behavior:'smooth',block:'nearest'});
 }catch(e){el.textContent=e.message;}
}
function mount(){
 const root=document.getElementById('view-root');if(window.PublicRiskAPI||!root)return;
 if(!wired){
   wired=true;
   root.addEventListener('submit',async e=>{
     if(e.target?.id!=='uf-form')return;
     e.preventDefault();
     q=document.getElementById('uf-q').value.trim();
     country=document.getElementById('uf-country').value.trim().toUpperCase();
     industry=document.getElementById('uf-industry').value.trim();
     source=document.getElementById('uf-source').value.trim();
     page=0;await load();
   });
   root.addEventListener('click',async e=>{
     const t=e.target;if(!t)return;
     if(t.id==='uf-clear'){
       q=country=industry=source='';page=0;
       for(const id of ['uf-q','uf-country','uf-industry']){const inp=document.getElementById(id);if(inp)inp.value='';}
       const dropdown=document.getElementById('uf-source');if(dropdown)dropdown.value='';
       await load();return;
     }
     if(t.id==='uf-prev'){page=Math.max(0,page-1);await load();return;}
     if(t.id==='uf-next'){page+=1;await load();return;}
     if(t.dataset.ufId){await inspect(t.dataset.ufId);return;}
     if(t.id==='uf-assess'&&selected){
       window.dispatchEvent(new CustomEvent('facilityrisk:assess-site',{detail:{
         ...selected.site,source_identities:selected.source_identities,
         physical_property_verified:false,insured_coverage_status:'unknown'}}));return;
     }
     if(t.id==='uf-track'&&selected){
       try{
        const res=await fetch('/api/universal-facilities/'+encodeURIComponent(selected.site.id)+'/track',{method:'POST'});
        const payload=await res.json().catch(()=>({}));
        if(!res.ok)throw Error(payload.detail||'Authorized private research writes required');
        const message=document.getElementById('uf-track-status');
        if(message)message.textContent='Private research entry '+esc(payload.facility_id||'created')+
          (payload.already_tracked?' already exists.':' created. Open Research cases to review identity.');
        t.disabled=true;t.textContent='Tracked in private workspace';
       }catch(err){
        const message=document.getElementById('uf-track-status');
        if(message)message.textContent=err.message;
       }
     }
   });
 }
 load();
}
window.UniversalUI={render,mount};
})();