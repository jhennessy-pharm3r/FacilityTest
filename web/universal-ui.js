/* Universal facility discovery, backed by private indexed API. */
(()=>{
'use strict';
const esc = v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let q='',page=0,selected=null,wired=false;
function render(){
return '<div class="page-heading"><div><div class="eyebrow">ALL INDUSTRIES / ALL FACILITIES</div><h1>Universal facility discovery</h1><p class="subhead">Independent official and place source identities, not verified insured properties.</p></div></div>'+
(window.PublicRiskAPI
 ? '<section class="panel"><div class="panel-body"><strong>Universal search requires the private backend.</strong><p>The public site currently hosts FDA, Ireland EPA and Canada NPRI registrations only. It does not host global place records or client data.</p><button class="btn primary" data-page="registry">Browse available public identities</button></div></section>'
 : '<section class="panel"><div class="registry-controls"><input id="uf-q" class="field registry-search" value="'+esc(q)+'" placeholder="Any site, company, industry or location"><input id="uf-country" class="field" placeholder="Country ISO"><button class="btn primary" id="uf-search">Search</button></div><div id="uf-status" class="registry-status">Checking indexed records...</div><div id="uf-results"></div></section>');
}
async function load(){
const root=document.getElementById('uf-results');if(!root)return;
const p=new URLSearchParams({q,country:document.getElementById('uf-country')?.value||'',limit:'50',offset:String(page*50)});
try {
const [r,s]=await Promise.all([fetch('/api/universal-facilities?'+p),fetch('/api/universal-facilities/stats')]);
if(!r.ok||!s.ok)throw Error('Private facility registry unavailable');
const d=await r.json(),stats=await s.json();
document.getElementById('uf-status').textContent=stats.site_candidates.toLocaleString()+' source-site candidates; '+stats.source_identities.toLocaleString()+' source identities; '+d.total.toLocaleString()+' matches. Physical property and insurance status unverified.';
root.innerHTML='<div class="registry-list">'+d.items.map(x=>
  '<article class="registry-record" style="display:block"><strong>'+esc(x.name)+'</strong> · '+esc(x.industry||'Unclassified')+
  '<p class="registry-record-sub">'+esc(x.company)+' · '+esc([x.city,x.state,x.country].filter(Boolean).join(', '))+
  '</p><button class="btn tiny" data-uf-id="'+esc(x.id)+'">Inspect source identity</button></article>').join('')+
  '</div><div id="uf-detail"></div><div class="registry-pagination"><button id="uf-prev" class="btn tiny" '+(page?'':'disabled')+'>Previous</button><span>'+d.total.toLocaleString()+' matching identities</span><button id="uf-next" class="btn tiny" '+((page+1)*50>=d.total?'disabled':'')+'>Next</button></div>';
}catch(e){root.innerHTML='<div class="empty">'+esc(e.message)+'. Import authorized source records to enable all-industry search.</div>';}
}
async function inspect(id){
const el=document.getElementById('uf-detail');if(!el)return;
try{
const r=await fetch('/api/universal-facilities/'+encodeURIComponent(id));if(!r.ok)throw Error('Source record not found');
const d=await r.json();selected=d;
el.innerHTML='<section class="panel"><div class="panel-body"><h2>'+esc(d.site.name)+'</h2><p>Property verification: '+esc(d.site.coordinate_quality)+' · Insurance coverage: Unknown</p>'+
 d.source_identities.map(x=>'<p>'+esc(x.source_key)+' / '+esc(x.source_identifier)+' · <a href="'+esc(x.source_url)+'" rel="noopener noreferrer" target="_blank">Publisher</a></p>').join('')+
 '<div class="registry-actions"><button class="btn" id="uf-assess">Assess insurance exposure</button><button class="btn primary" id="uf-track">Add to private research workspace</button></div></div></section>';
}catch(e){el.textContent=e.message;}
}
function mount(){
const root=document.getElementById('view-root');if(window.PublicRiskAPI||!root)return;
if(!wired){wired=true;root.addEventListener('click',async e=>{
if(e.target.id==='uf-search'){q=document.getElementById('uf-q').value.trim();page=0;await load();}
if(e.target.id==='uf-prev'){page=Math.max(0,page-1);await load();}
if(e.target.id==='uf-next'){page+=1;await load();}
if(e.target.dataset.ufId)await inspect(e.target.dataset.ufId);
if(e.target.id==='uf-assess'&&selected){
  window.dispatchEvent(new CustomEvent('facilityrisk:assess-site',{detail:{...selected.site,source_identities:selected.source_identities}}));return;
}
if(e.target.id==='uf-track'&&selected){
try {
const r=await fetch('/api/universal-facilities/'+encodeURIComponent(selected.site.id)+'/track',{method:'POST'});
if(!r.ok)throw Error('Authenticated research writes required');
e.target.textContent='Research entry created';
}catch(ex){alert(ex.message);}
}
});}
load();
}
window.UniversalUI={render,mount};
})();
