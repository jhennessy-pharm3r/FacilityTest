/* Authenticated private operational-interruption assumptions and evidence.
   No insurer payout, catastrophe frequency or premium is calculated. */
(()=>{
'use strict';
const esc=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=v=>v==null?'Not entered':Number(v).toLocaleString('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2});
let selected='',details=null,matches=[],search='',wired=false;
const byId=id=>document.getElementById(id);
const CAUSES=['flood','windstorm','wildfire','earthquake','utility_failure','supplier_disruption','civil_authority','geopolitical','cyber','operational','other'];
const DEPS=['grid_power','water','natural_gas','telecom','supplier','customer','transport','access','equipment','staffing','other'];
function optionList(values){return values.map(x=>'<option value="'+esc(x)+'">'+esc(x.replace(/_/g,' '))+'</option>').join('')}
async function query(path,options={}){
 const response=await fetch('/api/'+path,{cache:'no-store',...options});
 const payload=await response.json().catch(()=>({detail:'Invalid API response'}));
 if(!response.ok)throw Error(payload.detail||'Request failed: '+response.status);
 return payload;
}
function setStatus(value,error=false){const el=byId('bi-status');if(el){el.textContent=value;el.className='registry-status'+(error?' registry-error':'')}}
function render(){
 return '<div class="page-heading"><div><div class="eyebrow">PRIVATE INSURANCE RESEARCH · OPERATIONS</div>'+
 '<h1>Business interruption scenarios</h1><p class="subhead">Study actual site-specific dependencies and hypothetical outage/recovery assumptions. All amounts remain analyst estimates, not claims or confirmed coverage.</p></div></div>'+
 '<section class="panel"><div class="panel-body"><strong>Private input only.</strong><p>This workflow never infers financial loss from regulator registration, calculates insured payouts or marks an uninsured site as protected. Check assumptions and review actual policy wording separately.</p></div>'+
 '<form id="bi-search-form" class="registry-controls">'+
 '<input class="field registry-search" id="bi-search-query" placeholder="Find a researched facility" value="'+esc(search)+'" aria-label="Facility lookup"/>'+
 '<button class="btn primary" type="submit">Find facility</button></form>'+
 '<div id="bi-matches"></div><p class="registry-status" id="bi-status">Select a researched facility to view or enter downtime scenarios.</p></section>'+
 '<div id="bi-site"></div>';
}
function matchesHtml(){
 return matches.length?'<div class="registry-list">'+matches.map(f=>
 '<button class="registry-record" data-bi-facility="'+esc(f.id)+'"><strong>'+esc(f.name)+'</strong>'+
 '<p class="registry-record-sub">'+esc(f.company||'')+' · '+esc(f.address||'')+'</p></button>').join('')+'</div>':
 '<div class="empty">No researched facilities found. Use universal search or private facility intake to add an investigation.</div>';
}
function siteHtml(){
 if(!details)return '';
 const summary=details.scenarios.length?details.scenarios.map(row=>{
  const i=row.illustration;
  const others=i.additional_expense_components_usd;
  return '<article class="compact-item"><div class="label-row"><h3>'+esc(row.scenario_name)+'</h3><span class="pill orange">Analyst hypothetical</span></div>'+
   '<p>'+esc(row.interruption_cause.replace(/_/g,' '))+' · dependency: '+esc(row.affected_dependency.replace(/_/g,' '))+
   ' · revision '+row.revision+'</p>'+
   '<p class="note-line">'+esc(row.assumption_basis||'Assumption basis not supplied')+'</p>'+
   '<div class="label-row"><strong>Equivalent lost operating days: '+Number(i.equivalent_lost_operating_days).toLocaleString()+'</strong>'+
   '<strong>'+money(i.illustrative_lost_contribution_margin_usd)+'</strong></div>'+
   '<p class="note-line">Illustrative lost contribution margin, not an insured BI loss or payout</p>'+
   '<p class="detail">Extra expense: '+money(others.extra_expense)+' · Stock loss: '+money(others.spoilage_or_inventory)+
   ' · Physical repair: '+money(others.property_repair)+' — separately reported, not added to margin because costs may overlap.</p>'+
   '<p class="note-line">Contractual review: '+i.coverage_topics_to_review.map(esc).join(', ')+
   '. No attachment or actual payout is verified.</p></article>';
 }).join(''):'<div class="empty">No scenarios recorded for this facility; this is not evidence of resilience or lack of historical interruptions.</div>';
 const input=(name,label,opts='')=>'<label>'+esc(label)+'<input class="field" name="'+name+'" '+opts+'/></label>';
 return '<section class="panel"><div class="panel-header"><h2>Facility '+esc(details.facility_id)+'</h2></div>'+
 '<div class="panel-body"><strong>'+details.count+' hypothetical scenarios</strong>'+
 '<p class="note-line">Each is a planning assumption with unknown insurer recovery, not site-specific observed loss.</p></div>'+
 '<div class="item-stack">'+summary+'</div></section>'+
 '<section class="panel"><div class="panel-header"><h2>Create interruption stress scenario</h2></div>'+
 '<div class="panel-body"><form id="bi-scenario-form" class="wb-fields">'+
 input('scenario_name','Scenario label','required maxlength="200" placeholder="e.g. Grid outage plus recovery"')+
 '<label>Interruption cause<select class="select" name="interruption_cause">'+optionList(CAUSES)+'</select></label>'+
 '<label>Affected dependency<select class="select" name="affected_dependency">'+optionList(DEPS)+'</select></label>'+
 input('gross_outage_days','Full outage (days)','type="number" min="0" max="3650" step="0.01" required value="3"')+
 input('margin_at_risk_daily_usd','Contribution margin at risk / day (USD)','type="number" min="0" step="0.01" required value="10000"')+
 input('outage_mitigation_fraction','Outage mitigation fraction (0 to 1)','type="number" min="0" max="1" step="0.01" value="0"')+
 input('recovery_ramp_days','Additional restart/ramp days','type="number" min="0" max="3650" step="0.01" value="0"')+
 input('recovery_average_capacity','Average operating capacity during ramp (0 to 1)','type="number" min="0" max="1" step="0.01" value="1"')+
 input('extra_expense_usd','Additional extra expense (USD, separate component)','type="number" min="0" step="0.01"')+
 input('stock_spoilage_usd','Stock spoilage (USD, separate component)','type="number" min="0" step="0.01"')+
 input('property_repair_usd','Property repair (USD, separate component)','type="number" min="0" step="0.01"')+
 input('reference_url','Optional original source (HTTPS)','type="url" maxlength="1200"')+
 input('scenario_description','Description / what caused downtime','maxlength="2000"')+
 input('assumption_basis','Financial and restoration assumption basis','maxlength="2000" placeholder="Name source, management estimates and uncertainties"')+
 '<div class="wb-span"><p class="note-line">Scenario arithmetic: days × margin/day × unmitigated fraction, plus separate partial-capacity restart days. Do not sum spoilage, repair or extra expense as an insurer claim; review actual contract and any overlapping costs.</p>'+
 '<button class="btn primary" type="submit">Save private, unverified scenario</button></div>'+
 '</form></div></section>';
}
async function refresh(){
 if(!selected)return;
 setStatus('Retrieving facility-specific interruption scenarios...');
 try{
  details=await query('facilities/'+encodeURIComponent(selected)+'/interruption-scenarios');
  const area=byId('bi-site');if(area)area.innerHTML=siteHtml();
  setStatus('Selected facility: '+selected+'. All scenarios are assumptions, not insured claim amounts.');
 }catch(error){setStatus(error.message,true)}
}
function mount(){
 const root=byId('view-root');
 if(!root||window.PublicRiskAPI)return;
 if(!wired){
   wired=true;
   root.addEventListener('submit',async e=>{
     if(!byId('bi-status'))return;
     if(e.target.id==='bi-search-form'){
       e.preventDefault();
       search=byId('bi-search-query').value.trim();
       if(!search){setStatus('Enter a facility name or ID',true);return;}
       try{const result=await query('facilities?search='+encodeURIComponent(search)+'&limit=50');
         matches=result.items||[];const area=byId('bi-matches');if(area)area.innerHTML=matchesHtml();
         setStatus(result.total+' researched facilities match. Select the correct physical site.');
       }catch(error){setStatus(error.message,true)}
     }
     if(e.target.id==='bi-scenario-form'){
       e.preventDefault();if(!selected)return;
       const fields={};
       for(const input of e.target.querySelectorAll('[name]')){
         const value=input.value.trim();
         if(value)fields[input.name]=value;
       }
       try{
         await query('facilities/'+encodeURIComponent(selected)+'/interruption-scenarios',{
           method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(fields)});
         await refresh();
       }catch(error){setStatus(error.message,true)}
     }
   });
   root.addEventListener('click',async e=>{
     if(!byId('bi-status'))return;
     const t=e.target.closest('[data-bi-facility]');
     if(t){selected=t.dataset.biFacility;await refresh();}
   });
 }
 if(selected)refresh();
}
window.BIScenarioUI={render,mount};
})();