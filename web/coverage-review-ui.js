/* Private-only review of facility insurance policies and location-verified hazards.
   No attachment uploads, no policy text on Pages, and no inferred payout. */
(()=>{
'use strict';
const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
let matches=[],facilityId='',data=null,review=null,queue=null,loading=false,bound=false,searchTerm='';
const $=id=>document.getElementById(id);
async function req(path,opts={}){
 const r=await fetch('/api/'+path,{cache:'no-store',...opts});
 const response=await r.json().catch(()=>({detail:'Invalid server response'}));
 if(!r.ok)throw Error(response.detail||'Request failed: '+r.status);
 return response;
}
function msg(message,error=false){const t=$('cr-status');if(t){t.textContent=message;t.className=error?'registry-status registry-error':'registry-status';}}
function render(){
 return '<div class="page-heading"><div><div class="eyebrow">PRIVATE REVIEW / INSURANCE TERMS</div><h1>Policy & coverage evidence</h1>'+
 '<p class="subhead">Match independently reviewed property hazards against documented coverage terms. This private workspace is not a risk rating or claims decision.</p></div></div>'+
 '<div class="panel"><div class="panel-body"><strong>Individual reviewer accounts required for edits.</strong>'+
 '<p class="note-line">Source-document references and SHA-256 fingerprints are stored, not policy files. Policy wording, exclusions and proof of coverage require independent review. Do not enter confidential materials into the public Pages site.</p></div>'+
 '<div class="registry-controls"><input class="field registry-search" id="cr-search" placeholder="Search any researched facility" value="'+E(searchTerm)+'"/>'+
 '<button class="btn primary" id="cr-find">Find facility</button></div><div id="cr-match"></div></div>'+
 '<p id="cr-status" class="registry-status">Select a private researched facility to review policies.</p>'+
 '<div id="cr-detail"></div>';
}
function matchesHTML(){
 return matches.length?'<div class="registry-list">'+matches.map(x=>
   '<button class="registry-record" data-cr-site="'+E(x.id)+'"><strong>'+E(x.name)+'</strong>'+
   '<p class="registry-record-sub">'+E(x.company||'')+' · '+E(x.address||'')+' · '+E(x.country||'')+'</p></button>').join('')+
   '</div>':'<div class="empty">No private research facilities matched. First add the site to the private workspace using Facility Search.</div>';
}
const fields={policy_reference:'Policy reference',insurer:'Insurer',start_date:'Inception date',
 end_date:'Expiry date',location_schedule_reference:'Scheduled insured location reference',
 currency:'Currency (ISO)',total_insured_value:'Total insured value'};
function policyForm(){
 const f=(key,type='text',required=true,placeholder='')=>'<label>'+E(fields[key])+
  '<input class="field" data-cr-policy="'+key+'" type="'+type+'" maxlength="400" '+(required?'required':'')+
  ' placeholder="'+E(placeholder)+'"/></label>';
 return '<section class="panel"><div class="panel-header"><h2>Register policy metadata</h2></div>'+
 '<div class="panel-body"><p>Only authorized reviewers may create policy metadata. No insurer confirmation is implied.</p>'+
 '<form id="cr-policy-form" class="wb-fields">'+f('insurer')+f('policy_reference')+
 f('start_date','date')+f('end_date','date')+f('location_schedule_reference')+
 f('currency','text',true,'USD')+f('total_insured_value','number',false)+
 '<button class="btn primary" type="submit">Create unverified policy record</button></form></div></section>';
}
function coverageSelect(){
 const ids=['property','flood','earthquake','windstorm','wildfire','bi','extra_expense','utility',
 'cbi','civil_authority','non_damage_bi','equipment','parametric_wind','parametric_flood',
 'parametric_quake','parametric_outage','parametric_wildfire','environmental','political'];
 return ids.map(x=>'<option value="'+x+'">'+E(x.replace(/_/g,' '))+'</option>').join('');
}
function detailHTML(){
 if(!data)return '';
 let p='<section class="panel"><div class="panel-header"><h2>'+E(data.facility_id)+'</h2></div>'+
 '<div class="panel-body"><p><strong>'+data.document_reviewed_current_terms_count+
 '</strong> current policy terms independently reviewed. This count is not proof of payout or insurability.</p></div></section>';
 p+=policyForm();
 p+='<section class="panel"><div class="panel-header"><h2>Recorded policies and coverage terms</h2></div><div class="panel-body">';
 if(!data.policies.length)p+='<p class="note-line">No policy schedule is recorded. All coverage remains unknown.</p>';
 for(const policy of data.policies){
   p+='<article class="compact-item"><h3>'+E(policy.insurer)+' · '+E(policy.policy_reference)+'</h3>'+
      '<p>'+E(policy.start_date)+' — '+E(policy.end_date)+' · '+E(policy.policy_period_status)+
      ' · '+E(policy.location_schedule_reference)+'</p>';
   for(const term of policy.terms){
     p+='<div class="qa-line"><strong>'+E(term.coverage_id)+'</strong><span>'+
         E(term.effective_review_status)+' · revision '+E(term.revision)+'</span></div>'+
         '<p class="note-line">Limit: '+E(term.limits??'Unknown')+' · Deductible: '+E(term.deductible??'Unknown')+
         ' · Waiting hours: '+E(term.waiting_hours??'Unknown')+'</p>';
     if(term.status==='unverified')p+='<button class="btn tiny" data-cr-propose="'+E(term.id)+'">Propose independent review</button>';
   }
   p+='<form class="cr-term-form wb-fields" data-cr-policy-id="'+E(policy.id)+'">'+
      '<label>Coverage type<select class="select" name="coverage_id">'+coverageSelect()+'</select></label>'+
      '<label>Limit<input class="field" name="limits" type="number" min="0" step="any"/></label>'+
      '<label>Deductible<input class="field" name="deductible" type="number" min="0" step="any"/></label>'+
      '<label>Waiting hours<input class="field" name="waiting_hours" type="number" min="0" step="any"/></label>'+
      '<label class="wb-span">Policy trigger<input class="field" name="trigger_description" maxlength="1200"/></label>'+
      '<label class="wb-span">Exclusions<input class="field" name="exclusions" maxlength="2000"/></label>'+
      '<label class="wb-span">Endorsements<input class="field" name="endorsements" maxlength="2000"/></label>'+
      '<label>Parametric index provider<input class="field" name="parametric_index" maxlength="500"/></label>'+
      '<label>Parametric threshold / ladder<input class="field" name="parametric_threshold" maxlength="500"/></label>'+
      '<label class="wb-span">Parametric basis risk<input class="field" name="basis_risk" maxlength="1000"/></label>'+
      '<button class="btn" type="submit">Save unverified term / invalidate previous approval</button></form></article>';
 }
 p+='</div></section>';
 p+='<section class="panel"><div class="panel-header"><h2>Verified point hazard / policy crosswalk</h2></div>'+
 '<div class="panel-body"><p>'+E(review?.warning||'Screenings not yet available.')+'</p>';
 if(!review?.site_coordinate_verified)p+='<div class="empty">A currently reviewed physical-property coordinate is required before interpreting hazard screenings.</div>';
 for(const hazard of review?.current_screened_perils||[]){
   p+='<article class="compact-item"><h3>'+E(hazard.peril)+' · '+E(hazard.hazard_status)+'</h3>'+
   '<p>'+E(hazard.hazard_context)+'</p>'+
   hazard.related_coverage.map(x=>'<p><strong>'+E(x.coverage_id)+'</strong> · '+E(x.verification_status)+
      ' ('+x.terms.length+' current policy entries)</p>').join('')+'</article>';
 }
 p+='</div></section>';
 p+='<section class="panel"><div class="panel-header"><h2>Independent policy review queue</h2></div><div class="panel-body">';
 for(const row of queue?.items||[]){
    p+='<article class="compact-item"><h3>'+E(row.coverage_id)+' — '+E(row.proposed_status)+'</h3>'+
       '<p>Requested by '+E(row.requested_by)+' · Document '+E(row.document_reference)+
       ' · term revision '+E(row.term_revision)+'</p>'+
       '<button class="btn tiny" data-cr-decide="'+E(row.id)+'" data-decision="approve">Approve</button> '+
       '<button class="btn tiny" data-cr-decide="'+E(row.id)+'" data-decision="reject">Reject</button></article>';
 }
 p+=(queue?.items?.length?'':'<p>No pending requests for this facility.</p>')+'</div></section>';
 return p;
}
async function refresh(){
 if(!facilityId)return;
 loading=true;msg('Loading private policy evidence...');
 try{[data,review,queue]=await Promise.all([
  req('facilities/'+encodeURIComponent(facilityId)+'/policies'),
  req('facilities/'+encodeURIComponent(facilityId)+'/coverage-crosswalk'),
  req('policy-reviews?facility_id='+encodeURIComponent(facilityId))]);
  const el=$('cr-detail');if(el)el.innerHTML=detailHTML();
  msg('Current facility: '+facilityId+' · Coverage remains unknown unless individually reviewed.');
 }catch(e){msg(e.message,true)}finally{loading=false;}
}
function cleanForm(form,selector){
 const o={};for(const node of form.querySelectorAll(selector)){
   const k=node.name||node.dataset.crPolicy;const v=node.value.trim();if(v)o[k]=v;
 }return o;
}
async function find(){
 searchTerm=$('cr-search')?.value?.trim()||'';if(!searchTerm){msg('Enter a facility name or ID.',true);return;}
 try{const d=await req('facilities?search='+encodeURIComponent(searchTerm)+'&limit=50');
   matches=d.items;const el=$('cr-match');if(el)el.innerHTML=matchesHTML();
   msg(d.total+' matching private research facilities.');
 }catch(e){msg(e.message,true)}
}
function mount(){
 const root=$('view-root');if(!root)return;
 if(!bound){bound=true;
 root.addEventListener('click',async ev=>{
  if(!$('cr-status'))return;
  const t=ev.target;
  if(t.closest('#cr-find')){await find();return;}
  const site=t.closest('[data-cr-site]');if(site){facilityId=site.dataset.crSite;await refresh();return;}
  const proposal=t.closest('[data-cr-propose]');if(proposal){
   const proposed_status=prompt('Review status: verified_covered, verified_conditional, verified_excluded');
   if(!proposed_status)return;
   const document_reference=prompt('Secure document reference (no policy text):');if(!document_reference)return;
   const document_sha256=prompt('Reviewed document SHA-256 (64 hex characters):');if(!document_sha256)return;
   const rationale=prompt('Document section and coverage rationale (20+ characters):');if(!rationale)return;
   try{await req('policy-terms/'+encodeURIComponent(proposal.dataset.crPropose)+'/propose-review',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({proposed_status,document_reference,document_sha256,rationale})});
      await refresh();}catch(e){msg(e.message,true)}
   return;
  }
  const decision=t.closest('[data-cr-decide]');if(decision){
   const note=prompt('Independent review rationale (12+ characters):');if(!note)return;
   try{await req('policy-reviews/'+encodeURIComponent(decision.dataset.crDecide)+'/decide',{
     method:'POST',headers:{'Content-Type':'application/json'},
     body:JSON.stringify({decision:decision.dataset.decision,note})});
     await refresh();}catch(e){msg(e.message,true)}
  }
 });
 root.addEventListener('submit',async ev=>{
   if(!$('cr-status'))return;
   const form=ev.target;if(form.id!=='cr-policy-form'&&!form.classList.contains('cr-term-form'))return;
   ev.preventDefault();if(loading)return;
   try{
      let endpoint,payload;
      if(form.id==='cr-policy-form'){
        endpoint='facilities/'+encodeURIComponent(facilityId)+'/policies';
        payload=cleanForm(form,'[data-cr-policy]');
      }else{
        endpoint='policies/'+encodeURIComponent(form.dataset.crPolicyId)+'/terms';
        payload=cleanForm(form,'[name]');
      }
      await req(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      await refresh();
   }catch(e){msg(e.message,true)}
 });
 }
}
window.CoverageReviewUI={render,mount};
})();