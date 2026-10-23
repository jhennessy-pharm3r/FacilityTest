/* Cross-industry, browser-only underwriting scenario workbench.
   A selected peril is an analyst hypothesis, not a measured geohazard.
   Reported policy statuses are NEVER asserted as verified insurance cover.
   No client inputs are transmitted or stored by this module. */
(()=>{
'use strict';
const PERILS=[
  {id:'flood',label:'Flood / storm surge',detail:'River, flash or coastal flooding',covers:['flood','bi','extra_expense','parametric_flood'],question:'Obtain flood zone/depth, floor elevations and flood endorsement wording.'},
  {id:'wind',label:'Hurricane / windstorm',detail:'Wind, cyclone, tornado and roof damage',covers:['windstorm','bi','extra_expense','parametric_wind'],question:'Review named-storm deductibles, wind sublimits and opening protection.'},
  {id:'quake',label:'Earthquake',detail:'Ground shaking and earthquake exclusions',covers:['earthquake','bi','extra_expense','parametric_quake'],question:'Review seismic design, equipment anchoring, earthquake deductible and DIC.'},
  {id:'fire',label:'Wildfire',detail:'Wildfire, smoke, access and ash',covers:['wildfire','bi','civil_authority','parametric_wildfire'],question:'Review wildfire defensible space, smoke/ash terms and access restrictions.'},
  {id:'storm',label:'Severe storm / hail',detail:'Hail, tornado, lightning and heavy snow',covers:['property','windstorm','bi'],question:'Review roof age, hail deductibles, wind / hail exclusions and past losses.'},
  {id:'freeze',label:'Freeze / cold weather',detail:'Freeze-up, pipe damage and extreme winter weather',covers:['property','equipment','bi'],question:'Review winterization, freeze protection, equipment and water-damage conditions.'},
  {id:'heat',label:'Extreme heat / drought',detail:'Cooling, dry weather and water shortage',covers:['equipment','non_damage_bi'],question:'Document cooling demand, water resilience and whether non-damage triggers are expressly insured.'},
  {id:'landslide',label:'Landslide / earth movement',detail:'Slope stability and ground failure',covers:['property','earthquake','bi'],question:'Check earth-movement exclusion, geotechnical evidence and any dedicated endorsement.'},
  {id:'industrial',label:'Fire / explosion / pollution',detail:'Process-safety and environmental events',covers:['property','equipment','environmental','bi'],question:'Review fire suppression, hazardous inventory, blast separation and pollution exclusions.'}
];
const DEPENDENCIES=[
  {id:'power',label:'Electricity / grid',covers:['utility','extra_expense','parametric_outage'],question:'Identify serving utility, backup capacity and off-premises service interruption wording.'},
  {id:'water',label:'Water / wastewater',covers:['utility','extra_expense','non_damage_bi'],question:'Record water demand, alternate supplies, pressure/quality constraints and service endorsements.'},
  {id:'data',label:'Data / telecommunications',covers:['utility','non_damage_bi'],question:'Review communications continuity and whether cyber interruption requires a separate form.'},
  {id:'supplier',label:'Critical supplier / customer',covers:['cbi','extra_expense'],question:'Identify dependencies, alternative capacity, supplier territories and contingent BI clauses.'},
  {id:'access',label:'Road / port / transport access',covers:['civil_authority','extra_expense'],question:'Review ingress/egress, civil-authority distance conditions and logistics alternatives.'},
  {id:'temperature',label:'Temperature-sensitive inventory',covers:['equipment','extra_expense','bi'],question:'Document spoilage stock values, refrigeration, backup power and rejection/revalidation terms.'}
];
const PRODUCTS=[
  ['property','Commercial property','Physical damage','Covered loss to insured physical property','Named perils / exclusions, replacement value, deductibles and location schedule'],
  ['flood','Flood / excess flood','Catastrophe','Qualifying flood or storm surge','Flood wording, water-surface definition, zone, excess layers and sublimits'],
  ['windstorm','Windstorm / named storm','Catastrophe','Qualifying wind, tornado or cyclone damage','Named-storm deductibles, hail restrictions and storm definition'],
  ['earthquake','Earthquake / DIC','Catastrophe','Qualifying quake-related physical loss','Earth movement exclusions, percentage deductible and DIC attachment'],
  ['wildfire','Wildfire and smoke','Catastrophe','Qualifying covered fire / smoke damage','Fire peril, smoke/ash sublimits, property restoration'],
  ['bi','Business interruption','Interruption','Qualifying interruption attributable to insured damage','Material-damage requirement, indemnity period, time deductible, actual loss'],
  ['extra_expense','Extra expense','Interruption','Covered increased operating costs to continue business','Limits, necessity and restoration period'],
  ['utility','Utility service interruption','Interruption','Qualifying off-premises physical damage or explicit non-damage extension','Scheduled utilities, overhead lines, distance limit and waiting period'],
  ['cbi','Contingent BI','Interruption','Specified peril at qualifying supplier/customer','Supplier tier, insured peril, territorial scope, named/unnamed suppliers'],
  ['civil_authority','Civil authority / ingress-egress','Interruption','Contract-defined access restrictions','Physical damage condition, access radius, waiting period and time limit'],
  ['non_damage_bi','Specialty non-damage BI','Interruption','Expressly defined non-damage event','Named insured event, sublimit, waiting period, trigger and exclusions'],
  ['equipment','Equipment breakdown / spoilage','Equipment','Covered accidental breakdown, stock spoilage or related loss','Insured equipment, contamination, backup and temperature-control language'],
  ['parametric_flood','Parametric flood','Parametric','Contract-defined flood depth, rainfall or modeled threshold','Independent index, payout ladder, insured interest requirements and basis risk'],
  ['parametric_wind','Parametric hurricane / wind','Parametric','Contract-defined observed or modeled wind threshold','Measurement model, geographic point, trigger and payout schedule'],
  ['parametric_quake','Parametric earthquake','Parametric','Contract-defined peak acceleration or shaking intensity','Index provider, polygon, attachment and basis risk'],
  ['parametric_outage','Parametric service outage','Parametric','Contract-defined independently verified outage duration','Serving utility, time trigger, source, exclusions and independent validation'],
  ['parametric_wildfire','Parametric wildfire','Parametric','Contract-defined fire footprint or intensity threshold','Reference polygon, satellite/model source, payout schedule'],
  ['environmental','Environmental impairment liability','Liability','Specified pollution or contamination condition','Cleanup, gradual/sudden exclusions, retroactive date and off-site liability']
].map(([id,name,category,trigger,questions])=>({id,name,category,trigger,questions}));
const TYPES=new Map(PRODUCTS.map(p=>[p.id,p]));
const SOURCE_RESEARCH={
  flood:['fema_nfhl'],wind:[],quake:[],fire:['usfs_whp2023_six_national_tiffs','usfs_whp_aggregates','usfs_whp'],
  storm:[],freeze:['eia861'],heat:['eia861'],landslide:[],
  industrial:['uscg_nrc','csb','epa_rmp_public','epa_tri'],
  power:['eia861','pnnl_outages','odin_county'],water:['epa_echo'],
  data:['odin_feeds'],supplier:['baxter_bi'],access:['uscg_nrc'],
  temperature:['eia861']
};
const SOURCE_SHORT={
  fema_nfhl:'FEMA flood polygon samples',usfs_whp:'USDA wildfire pixels',
  usfs_whp_aggregates:'USDA wildfire regional summaries',
  usfs_whp2023_six_national_tiffs:'WHP2023 full native 270m raster source (CI only)',
  eia861:'EIA electric reliability',pnnl_outages:'DOE/PNNL county outages',
  odin_county:'ORNL ODIN outage snapshot',odin_feeds:'ORNL feed status',
  epa_echo:'EPA ECHO',epa_tri:'EPA TRI',epa_rmp_public:'Public EPA RMP',
  uscg_nrc:'USCG release notifications',csb:'CSB incidents',
  baxter_bi:'Baxter operational interruption publications'
};
function researchTasks(){
  return [...PERILS.filter(x=>state.perils.has(x.id)),...DEPENDENCIES.filter(x=>state.deps.has(x.id))].map(x=>({
    id:x.id,scenario:x.label,source_ids:SOURCE_RESEARCH[x.id]||[],
    site_evidence_status:'not_verified',research_question:x.question
  }));
}
function sourceResearchHTML(){
  const items=researchTasks();
  if(!items.length)return '<p class="wb-source-help">Choose an exposure or dependency to see which ingested source classes can help and what still requires property-specific verification.</p>';
  return '<div class="wb-source-tasks">'+items.map(row=>{
    const refs=row.source_ids.map(id=>'<a class="si-link si-jump" data-si-source="'+esc(id)+'" href="?page=sources&record='+encodeURIComponent(id)+'">'+esc(SOURCE_SHORT[id]||id)+' →</a>').join(' · ');
    return '<div class="wb-source-task"><strong>'+esc(row.scenario)+'</strong>'+
      '<div>'+(refs||'<span>No directly applicable verified source cohort yet</span>')+'</div>'+
      '<small>Verify site applicability; source/CI data do not establish this insured exposure.</small></div>';
  }).join('')+'</div>';
}

const STATUS=[
 ['unknown','Not yet reviewed'],
 ['reported','Reported in place — unverified'],
 ['wording','Policy wording needs review'],
 ['excluded','Reported excluded / not purchased']
];
let state={
  facility:'',industry:'',location:'',reference:'',days:'',daily:'',perils:new Set(),deps:new Set(),coverage:{},sourceIdentity:null
};
let wired=false;
const esc=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function money(x){
  return new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(x);
}
function relevant(){
  const reasons=new Map();
  for(const def of [...PERILS,...DEPENDENCIES]){
    if(!(state.perils.has(def.id)||state.deps.has(def.id)))continue;
    for(const id of def.covers){
      if(!reasons.has(id))reasons.set(id,[]);
      reasons.get(id).push(def.label);
    }
  }
  return PRODUCTS.filter(x=>reasons.has(x.id)).map(x=>({...x,reasons:reasons.get(x.id)}));
}
function exposure(){
  const days=Number(state.days),daily=Number(state.daily);
  if(state.days===''||state.daily===''||!Number.isFinite(days)||!Number.isFinite(daily)||days<0||daily<0)return null;
  return {days,daily,grossScenarioValue:days*daily};
}
function record(){
  const selected=[...PERILS.filter(x=>state.perils.has(x.id)),...DEPENDENCIES.filter(x=>state.deps.has(x.id))];
  const products=relevant();
  const values=exposure();
  return {
    assessment_type:'facility_exposure_and_contract_review_workbook',
    schema_version:'1.0',
    generated_at:new Date().toISOString(),
    facility:{name:state.facility.trim()||'Unspecified facility',industry:state.industry.trim()||'Unspecified',location:state.location.trim()||'Not provided'},
    scope:'User-entered scenarios; no facility coordinate, hazard map, policy or claim verified',
    source_observation:state.sourceIdentity,
    scenarios:selected.map(x=>({id:x.id,name:x.label,source:'analyst_selected_not_observed'})),
    financial_illustration:values?{downtime_days:values.days,contribution_margin_at_risk_per_day_usd:values.daily,
      gross_downtime_illustration_usd:values.grossScenarioValue,
      caveat:'Illustration only, not insured loss, BI adjustment, recoverable amount, deductible or insurer payout'}:null,
    potential_coverages:products.map(x=>({id:x.id,name:x.name,category:x.category,consider_for:x.reasons,
      requirement:x.questions,user_reported_status:state.coverage[x.id]||'unknown',
      verified_coverage:'unknown',verification_required:true})),
    assessor_reference:state.reference.trim(),
    unresolved_questions:selected.map(x=>x.question),
    source_research_tasks:researchTasks(),
    limitations:[
      'Selected exposures are hypothetical research topics, not observed or verified site hazards.',
      'User-entered insurance status is not verified policy coverage.',
      'Unknown, missing or unassessed information does not mean low risk or no exposure.',
      'Typical physical damage conditions, exclusions, limits, waiting periods and local insurable interest vary by contract.',
      'Parametric policies may have basis risk and payout and loss validation conditions.',
      'No actuarial score, claim prediction, premium quote or underwriting acceptance conclusion is calculated.',
      'This browser-only worksheet is kept in session memory; download exports are initiated solely by the user.'
    ]
  };
}
function checkItem(x,kind){
  const selected=(kind==='perils'?state.perils:state.deps).has(x.id);
  return '<label class="wb-check '+(selected?'active':'')+'"><input type="checkbox" data-wb-kind="'+kind+'" value="'+esc(x.id)+'" '+(selected?'checked':'')+'>'+
    '<span class="wb-check-body"><strong>'+esc(x.label)+'</strong><small>'+esc(x.detail||'Operational dependency')+'</small></span>'+
    '<span class="wb-check-mark" aria-hidden="true">'+(selected?'✓':'+')+'</span></label>';
}
function planHTML(){
  const items=relevant();
  const reported=items.filter(x=>(state.coverage[x.id]||'unknown')==='reported').length;
  const gaps=items.filter(x=>(state.coverage[x.id]||'unknown')==='excluded').length;
  const unknown=items.length-reported-gaps;
  const dollars=exposure();
  const msg=items.length?items.length+' coverage types to review against actual policy wording':'Choose one or more risk scenarios to build the review.';
  const questions=[...PERILS.filter(x=>state.perils.has(x.id)),...DEPENDENCIES.filter(x=>state.deps.has(x.id))].map(x=>x.question);
  return '<div class="wb-stats">'+
    '<div><span>Scenarios</span><strong>'+String(state.perils.size+state.deps.size)+'</strong><small>Chosen for assessment</small></div>'+
    '<div><span>Coverage topics</span><strong>'+items.length+'</strong><small>Not coverage findings</small></div>'+
    '<div><span>Reported exclusions</span><strong>'+gaps+'</strong><small>Unverified user entries</small></div></div>'+
    '<p class="wb-summary">'+esc(msg)+'. '+(items.length?'Of those, '+reported+' reported in place and '+unknown+' unresolved / needing wording review.':'')+'</p>'+
    (dollars?'<div class="wb-financial"><span>Illustrative contribution margin at risk</span><strong>'+money(dollars.grossScenarioValue)+'</strong><small>'+dollars.days+' day(s) × '+money(dollars.daily)+'/day. Not an insured BI loss or payment.</small></div>':'<div class="wb-financial wb-muted"><span>Financial illustration</span><strong>Not entered</strong><small>Requires expected outage days and contribution margin/day.</small></div>')+
    '<div class="wb-microtitle">What an underwriter would still need</div>'+
    '<ul class="wb-questions">'+(questions.length?questions.map(q=>'<li>'+esc(q)+'</li>').join(''):'<li>Site coordinates or address and applicable hazard evidence</li><li>Engineering, asset values, supply dependencies and actual policy documents</li>')+'</ul>'+ 
    '<div class="wb-microtitle">Official-source research to follow up</div>'+sourceResearchHTML();
}
function tableHTML(){
  const arr=relevant();
  if(!arr.length)return '<div class="wb-empty">Select natural hazards or operational dependencies to generate a targeted list of coverage types and review questions.</div>';
  return '<div class="wb-review-list">'+arr.map(x=>{
    const status=state.coverage[x.id]||'unknown';
    return '<article class="wb-review-row"><div class="wb-review-top"><div><span class="wb-category">'+esc(x.category)+'</span><h3>'+esc(x.name)+'</h3></div><div class="wb-user-status"><label for="wb-coverage-'+esc(x.id)+'">User-reported policy status</label>'+
      '<select id="wb-coverage-'+esc(x.id)+'" data-wb-coverage="'+esc(x.id)+'">'+STATUS.map(y=>
        '<option value="'+y[0]+'" '+(y[0]===status?'selected':'')+'>'+esc(y[1])+'</option>').join('')+
      '</select></div></div><p><strong>Why review:</strong> '+esc(x.reasons.join(' · '))+'</p>'+
      '<p><strong>Potential trigger:</strong> '+esc(x.trigger)+'</p>'+
      '<p class="wb-review-note"><strong>Verify:</strong> '+esc(x.questions)+'</p></article>';
  }).join('')+'</div>';
}
function render(){
  const ch=PERILS.map(x=>checkItem(x,'perils')).join('');
  const deps=DEPENDENCIES.map(x=>checkItem(x,'deps')).join('');
  return '<div class="wb-page">'+
  '<div class="wb-hero"><div><span class="wb-eyebrow">INSURANCE INTELLIGENCE / ASSESSMENT WORKSPACE</span>'+
  '<h1>Facility exposure & coverage workbench</h1>'+
  '<p>Start with any property, in any industry. Select the exposures to investigate, inspect potentially relevant coverage structures and document unanswered underwriting questions.</p>'+
  '<div class="wb-hero-links"><button class="btn primary" data-page="'+(window.PublicRiskAPI?'registry':'universal')+'">'+(window.PublicRiskAPI?'Browse published source identities →':'Discover all-industry facilities →')+'</button>'+
  '<button class="btn" data-page="insurance">Coverage reference</button></div></div>'+
  '<div class="wb-hero-mark"><span>01</span><strong>Identify</strong><span>02</span><strong>Screen</strong><span>03</span><strong>Verify</strong></div></div>'+
  '<div class="wb-disclaimer" role="note"><strong>Research worksheet — not a facility risk rating.</strong> Perils are selected by the analyst, not detected from an address. No coverage is confirmed without examining the actual insurance policy. Inputs remain in this browser session unless you export them. Do not enter confidential client or policy documents into the public preview.</div>'+
  '<div class="wb-layout"><div class="wb-left">'+
    '<section class="panel wb-panel"><div class="wb-panel-head"><span class="wb-step">1</span><div><h2>Identify the location</h2><p>Any facility type; registration and FEI are not required.</p></div></div>'+
    '<div class="wb-fields"><label>Facility name <input data-wb-field="facility" maxlength="200" placeholder="Facility or property name" value="'+esc(state.facility)+'"></label>'+
    '<label>Industry / use <input data-wb-field="industry" maxlength="160" placeholder="Any industry (e.g. logistics, laboratory, food processing)" value="'+esc(state.industry)+'"></label>'+
    '<label class="wb-span">Address / jurisdiction <input data-wb-field="location" maxlength="250" placeholder="Physical address or region; not automatically verified" value="'+esc(state.location)+'"></label></div></section>'+
    '<section class="panel wb-panel"><div class="wb-panel-head"><span class="wb-step">2</span><div><h2>Select natural and industrial hazards</h2><p>Investigate these scenarios; selections are not automatically detected exposures.</p></div></div>'+
    '<div class="wb-check-grid">'+ch+'</div></section>'+
    '<section class="panel wb-panel"><div class="wb-panel-head"><span class="wb-step">3</span><div><h2>Identify operational dependencies</h2><p>These may generate interruption without damage to the main facility.</p></div></div>'+
    '<div class="wb-check-grid">'+deps+'</div></section>'+
    '<section class="panel wb-panel"><div class="wb-panel-head"><span class="wb-step">4</span><div><h2>Optional downtime illustration</h2><p>Gross contribution margin illustration only; not an insurance claim or payout.</p></div></div>'+
    '<div class="wb-fields"><label>Outage days <input data-wb-field="days" type="number" min="0" max="3650" step="0.5" placeholder="e.g. 10" value="'+esc(state.days)+'"></label>'+
    '<label>Contribution margin at risk / day (USD) <input data-wb-field="daily" type="number" min="0" max="10000000000" step="0.01" placeholder="e.g. 10000" value="'+esc(state.daily)+'"></label>'+
    '<label class="wb-span">Source / assessor notes <textarea data-wb-field="reference" maxlength="1200" rows="2" placeholder="Source URLs, policy identifiers or items needing evidence review">'+esc(state.reference)+'</textarea></label></div></section></div>'+
  '<div class="wb-right"><section class="panel wb-summary-card"><div class="wb-panel-head"><span class="wb-step accent">●</span><div><h2>Current assessment</h2><p>Evidence status is independent of scenario selection.</p></div></div>'+
    '<div id="wb-summary">'+planHTML()+'</div></section>'+
    '<section class="panel wb-actions"><h2>Assessment output</h2><p>Review the suggested coverage structures, then export your research questions to JSON. Nothing is uploaded by this page.</p>'+
    '<div class="wb-export-buttons"><button class="btn primary" id="wb-export">Export assessment JSON</button>'+
    '<button class="btn" id="wb-copy">Copy review brief</button><button class="btn wb-reset" id="wb-reset">Clear worksheet</button></div>'+
    '<p id="wb-feedback" role="status" aria-live="polite" class="wb-feedback"></p></section></div></div>'+
  '<section class="panel wb-coverage-section"><div class="wb-panel-head"><span class="wb-step accent">5</span><div><h2>Coverage structures to review</h2><p>Every status below is an unverified user entry. A product being available does not establish that the insured holds it.</p></div></div>'+
  '<div id="wb-coverage-review">'+tableHTML()+'</div></section>'+
  '<div class="wb-bottom-note">To determine actual coverage, review declarations, endorsements, exclusions, sublimits, attachment points, waiting periods and claims conditions. Parametric policies can have basis risk and separate payout definitions. No risk score, quote, claim or verified gap is implied.</div>'+
  '</div>';
}
function update(){
  const summary=document.getElementById('wb-summary');
  const table=document.getElementById('wb-coverage-review');
  if(summary)summary.innerHTML=planHTML();
  if(table)table.innerHTML=tableHTML();
}
function note(s){
 const el=document.getElementById('wb-feedback');if(el)el.textContent=s;
}
function brief(){
 const obj=record();
 const lines=['FACILITY EXPOSURE & COVERAGE REVIEW (UNVERIFIED)',
  'Facility: '+obj.facility.name+' | Industry: '+obj.facility.industry+' | Location: '+obj.facility.location,
  'Selected scenarios (not verified hazards): '+(obj.scenarios.map(s=>s.name).join(', ')||'None'),
  'Potential coverages to review:'];
 for(const row of obj.potential_coverages)lines.push('- '+row.name+' | '+row.user_reported_status+' | Verify: '+row.requirement);
 for(const task of obj.source_research_tasks)lines.push('Source research for '+task.scenario+': '+(task.source_ids.join(', ')||'No validated cohort')+'; site match unverified.');
 if(obj.financial_illustration)lines.push('Illustrative gross downtime only: '+money(obj.financial_illustration.gross_downtime_illustration_usd));
 lines.push('Evidence supplied: '+(obj.assessor_reference||'None'),
 'All statuses are user-entered and unverified; not a policy, quote, claim payment or insurer rating.');
 return lines.join('\n');
}
function download(){
 const obj=record();const blob=new Blob([JSON.stringify(obj,null,2)],{type:'application/json'});
 const url=URL.createObjectURL(blob);
 const a=document.createElement('a');a.href=url;a.download='facility-exposure-review.json';document.body.append(a);a.click();a.remove();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
 note('Assessment JSON downloaded to your device; no data was submitted.');
}
function mount(){
 const root=document.getElementById('view-root');if(!root||wired)return;
 wired=true;
 root.addEventListener('input',e=>{
  const k=e.target.dataset.wbField;
  if(!k||!Object.prototype.hasOwnProperty.call(state,k))return;
  let val=String(e.target.value);
  if((k==='days'||k==='daily')&&val!==''&&(!Number.isFinite(Number(val))||Number(val)<0||Number(val)>10000000000)){
   note('Financial input must be a non-negative numeric amount.');return;
  }
  state[k]=val;
  if(k==='days'||k==='daily'){const summary=document.getElementById('wb-summary');if(summary)summary.innerHTML=planHTML();}
 });
 root.addEventListener('change',e=>{
  if(e.target.dataset.wbKind){
   const set=e.target.dataset.wbKind==='perils'?state.perils:state.deps;
   if(e.target.checked)set.add(e.target.value);else set.delete(e.target.value);
   e.target.closest('.wb-check')?.classList.toggle('active',e.target.checked);
   const mark=e.target.closest('.wb-check')?.querySelector('.wb-check-mark');if(mark)mark.textContent=e.target.checked?'✓':'+';
   update();
  }
  if(e.target.dataset.wbCoverage){
   if(STATUS.some(x=>x[0]===e.target.value))state.coverage[e.target.dataset.wbCoverage]=e.target.value;
   const summary=document.getElementById('wb-summary');if(summary)summary.innerHTML=planHTML();
  }
 });
 root.addEventListener('click',async e=>{
   if(e.target.id==='wb-export')download();
   if(e.target.id==='wb-copy'){try{await navigator.clipboard.writeText(brief());note('Assessment review brief copied to clipboard.');}catch{note('Clipboard permission unavailable; use Export assessment JSON.');}}
   if(e.target.id==='wb-reset'){
     state={facility:'',industry:'',location:'',reference:'',days:'',daily:'',perils:new Set(),deps:new Set(),coverage:{},sourceIdentity:null};
     root.innerHTML=render();window.SourceInsights?.mount('workbench',root);note('Worksheet cleared from this browser session.');
   }
 });
}
function beginFromSource(item){
  if(!item||typeof item!=='object')return;
  // Starting on a new source identity clears earlier perils and reported
  // coverages: exposure/insurance assumptions must NEVER migrate to another site.
  const s=item.source_identities&&item.source_identities.length?item.source_identities[0]:{};
  state={
    facility:String(item.name||'').slice(0,200),
    industry:String(item.sector||item.industry||'').slice(0,160),
    location:[item.address,item.city,item.state,item.country].filter(Boolean).join(', ').slice(0,250),
    reference:String(item.source_url||s.source_url||'').slice(0,1200),
    days:'',daily:'',perils:new Set(),deps:new Set(),coverage:{},
    sourceIdentity:{
      source:String(item.source||s.source_key||'Unspecified source').slice(0,160),
      source_id:String(item.registration_number||item.fei||s.source_identifier||item.id||'').slice(0,200),
      source_url:String(item.source_url||s.source_url||'').slice(0,500),
      physical_property_verified:false
    }
  };
}
window.WorkbenchUI={render,mount,assessment:()=>record(),beginFromSource};
})();
