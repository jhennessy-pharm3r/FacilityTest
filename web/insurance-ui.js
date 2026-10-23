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
const COVERAGE_SOURCES={
  property:['fema_nfhl','usfs_whp_aggregates'],flood:['fema_nfhl'],
  earthquake:[],windstorm:[],wildfire:['usfs_whp2023_six_national_tiffs','usfs_whp_aggregates','usfs_whp'],
  bi:['baxter_bi','ornl_eaglei_2025','pnnl_outages'],extra_expense:['baxter_bi'],
  utility:['eia861','ornl_eaglei_2025','pnnl_outages','odin_county'],cbi:['baxter_bi'],
  civil_authority:[],non_damage_bi:['odin_county','baxter_bi'],
  equipment:['eia861'],parametric_wind:[],parametric_flood:['fema_nfhl'],
  parametric_quake:[],parametric_outage:['odin_county','eia861','ornl_eaglei_2025'],
  parametric_wildfire:['usfs_whp2023_six_national_tiffs','usfs_whp_aggregates'],political:[],
  environmental:['epa_echo','epa_rcra','epa_tri','epa_rmp_public']
};
const SOURCE_NAMES={
  fema_nfhl:'FEMA flood source (sample only)',usfs_whp:'USFS 270m wildfire sample',
  usfs_whp_aggregates:'USDA regional wildfire summaries',
  usfs_whp2023_six_national_tiffs:'WHP2023 six original georeferenced files (CI only)',baxter_bi:'Baxter disruption publications',
  pnnl_outages:'DOE/PNNL county outage history',ornl_eaglei_2025:'ORNL EAGLE-I 2025 readings; no insured outage validation',eia861:'EIA electric reliability',
  odin_county:'ORNL ODIN outage snapshot',epa_echo:'EPA ECHO',epa_rcra:'EPA RCRA',
  epa_tri:'EPA TRI reports',epa_rmp_public:'EPA public RMP program'
};
function linkedEvidence(id){
  const sources=COVERAGE_SOURCES[id]||[];
  return '<div class="si-coverage-support"><strong>Evidence to research, not a coverage determination</strong>'+
    '<div>'+ (sources.length?sources.map(key=>
      '<a class="si-jump" data-si-source="'+esc(key)+'" href="?page=sources&record='+encodeURIComponent(key)+'">'+esc(SOURCE_NAMES[key]||key)+' ↗</a>').join(' · '):
      '<span>No directly linked validated source cohort in this preview; request the appropriate independent peril, policy or engineering evidence.</span>')+
    '</div><small>Source-index records have not been independently mapped to this insured property. Contract terms control coverage.</small></div>';
}

let data=DEFAULT,category='',query='',initialized=false;
const categories=['Property damage','Natural catastrophe','Operational interruption','Equipment and inventory','Parametric','Liability','Specialty'];
function renderCards(){
 const r=data.filter(x=>(!category||category===x.category)&&(!query||[x.name,x.potential_trigger,x.review_requirements].some(v=>String(v||'').toLowerCase().includes(query.toLowerCase()))));
 return '<div class="intel-case-grid">'+r.map(x=>
 '<article class="panel"><div class="panel-header"><div><h2>'+esc(x.name)+'</h2><span class="overline">'+esc(x.category)+'</span></div></div>'+
 '<div class="intel-card-body"><div class="detail">'+esc(x.potential_trigger)+'</div><p class="note-line">'+esc(x.review_requirements||'Contract review required')+'</p>'+
 '<div class="card-meta"><span class="pill orange">Coverage unknown</span><span class="small-muted">Subject to facility and contract assessment</span></div>'+linkedEvidence(x.id)+'</div></article>').join('')+'</div>'+
 (r.length?'':'<div class="empty">No matching coverage categories.</div>');
}
function render(){
 return '<div class="page-heading"><div><div class="eyebrow">ALL FACILITIES · INSURANCE REFERENCE</div><h1>Insurance coverage & alternative options</h1><p class="subhead">Property, natural catastrophe, business interruption, utility service, contingent BI, and parametric structures for all industries. Availability does not prove a facility holds the coverage.</p></div></div>'+
 '<div class="wb-coverage-cta"><div><strong>Turn these options into an assessment</strong><p>Pick real scenarios to review for any facility. Coverage remains unverified until policy documents are examined.</p></div><button class="btn primary" data-page="workbench">Open assessment workbench →</button></div>'+ 
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
