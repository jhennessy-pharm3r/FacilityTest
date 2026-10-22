/* Facility insurance reference: not a policy or insured coverage determination. */
(()=>{
'use strict';
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const DEFAULT=[
 ['property','Commercial property','Property damage','Covered physical loss at insured property'],
 ['flood','Flood / excess flood','Natural catastrophe','Covered flood at insured premises'],
 ['earthquake','Earthquake / Difference in Conditions','Natural catastrophe','Covered seismic loss'],
 ['windstorm','Windstorm / named storm','Natural catastrophe','Covered wind or hurricane damage'],
 ['wildfire','Wildfire','Natural catastrophe','Covered fire, smoke or ash damage'],
 ['bi','Business interruption','Operational interruption','Covered production loss attributable to qualifying damage'],
 ['extra_expense','Extra expense','Operational interruption','Covered necessary additional continuation costs'],
 ['utility','Utility service interruption','Operational interruption','Qualifying interruption of named utility services'],
 ['cbi','Contingent business interruption','Operational interruption','Covered damage at specified supplier or customer'],
 ['civil_authority','Civil authority / ingress-egress','Operational interruption','Qualifying access restrictions and loss triggers'],
 ['non_damage_bi','Specialty non-damage BI','Operational interruption','Expressly insured interruption without direct physical damage'],
 ['equipment','Equipment breakdown / spoilage','Equipment and inventory','Covered equipment failure or temperature-sensitive stock'],
 ['parametric_wind','Parametric hurricane / wind','Parametric','Contract index wind or hurricane threshold'],
 ['parametric_flood','Parametric flood','Parametric','Contract water-level or rainfall threshold'],
 ['parametric_quake','Parametric earthquake','Parametric','Contract earthquake shaking / intensity threshold'],
 ['parametric_outage','Parametric utility outage','Parametric','Verified contracted grid or service outage threshold'],
 ['parametric_wildfire','Parametric wildfire','Parametric','Independent verified fire perimeter or severity index'],
 ['political','Political violence / political risk','Specialty','Specified violence or expropriation event'],
 ['environmental','Environmental impairment liability','Liability','Expressly covered pollution liability event']
].map(([id,name,category,potential_trigger])=>({id,name,category,potential_trigger,
  review_requirements:'Read applicable policy or contract, triggers, geography, exclusions, limits and evidence.',verified_coverage:'unknown'}));
let data=DEFAULT,category='',query='',initialized=false;
const categories=['Property damage','Natural catastrophe','Operational interruption','Equipment and inventory','Parametric','Liability','Specialty'];
function renderCards(){
 const r=data.filter(x=>(!category||category===x.category)&&(!query||[x.name,x.potential_trigger,x.review_requirements].some(v=>String(v||'').toLowerCase().includes(query.toLowerCase()))));
 return '<div class="intel-case-grid">'+r.map(x=>
 '<article class="panel"><div class="panel-header"><div><h2>'+esc(x.name)+'</h2><span class="overline">'+esc(x.category)+'</span></div></div>'+
 '<div class="intel-card-body"><div class="detail">'+esc(x.potential_trigger)+'</div><p class="note-line">'+esc(x.review_requirements||'Contract review required')+'</p>'+
 '<div class="card-meta"><span class="pill orange">Coverage unknown</span><span class="small-muted">Subject to facility and contract assessment</span></div></div></article>').join('')+'</div>'+
 (r.length?'':'<div class="empty">No matching coverage categories.</div>');
}
function render(){
 return '<div class="page-heading"><div><div class="eyebrow">ALL FACILITIES · INSURANCE REFERENCE</div><h1>Insurance coverage & alternative options</h1><p class="subhead">Property, natural catastrophe, business interruption, utility service, contingent BI, and parametric structures for all industries. Availability does not prove a facility holds the coverage.</p></div></div>'+
 '<section class="panel"><div class="panel-body"><strong>Policy verification is required.</strong><p>These are potential coverage types, not policy findings. A payout requires satisfaction of each contract’s terms. Standard BI often depends on qualifying covered property damage; parametric payout terms and basis risk are separate.</p></div>'+
 '<div class="registry-controls"><input id="insurance-search" class="field registry-search" placeholder="Search insurance types..." value="'+esc(query)+'">'+
 '<select class="select" id="insurance-category"><option value="">All categories</option>'+
 categories.map(x=>'<option value="'+esc(x)+'"'+(category===x?' selected':'')+'>'+esc(x)+'</option>').join('')+'</select></div></section>'+
 '<div id="insurance-coverage-results">'+renderCards()+'</div>';
}
function mount(){
 const root=document.getElementById('view-root');
 if(!root)return;
 if(!initialized){
  initialized=true;
  root.addEventListener('input',e=>{
   if(e.target.id==='insurance-search'){query=e.target.value;const el=document.getElementById('insurance-coverage-results');if(el)el.innerHTML=renderCards();}
  });
  root.addEventListener('change',e=>{
   if(e.target.id==='insurance-category'){category=e.target.value;const el=document.getElementById('insurance-coverage-results');if(el)el.innerHTML=renderCards();}
  });
 }
 if(!window.PublicRiskAPI){
  fetch('/api/insurance/coverage-types').then(r=>{if(!r.ok)throw Error('Backend reference unavailable');return r.json();})
  .then(o=>{if(Array.isArray(o.coverages)&&o.coverages.length){data=o.coverages;
    const el=document.getElementById('insurance-coverage-results');if(el)el.innerHTML=renderCards();}})
  .catch(()=>{}); // Keep explicit bundled public reference if private endpoint is unavailable.
 }
}
window.InsuranceUI={render,mount};
})();
