/* Private EPA regulator evidence — original source IDs, never physical insured-site matching. */
(() => {
  'use strict';
  const esc = value => String(value == null ? '' : value).replace(/[&<>"']/g,
    ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const sources = {echo:'EPA ECHO registry',rcra:'EPA RCRAInfo',tri:'EPA TRI Basic',rmp_public:'Public EPA RMP interests'};
  let status = null;
  let selected = 'echo';
  let generation = 0;
  let active = false;
  const fmt = value => Number.isSafeInteger(value) ? value.toLocaleString('en-US') : 'Not verified';
  function render() {
    status = null; selected = 'echo'; active = true; generation++;
    return `<div class="epa-evidence-page">
      <div class="page-heading"><div><div class="eyebrow">OFFICIAL SOURCE REVIEW</div>
        <h1>EPA regulatory evidence</h1>
        <p class="subhead">Exact original authority identifiers across all U.S. facility types and industries. Source records are not verified insured properties, incidents or losses.</p>
      </div></div>
      <div class="section-note neutral"><span>ⓘ</span><span>Data requires a verified, private read-only source mount and authenticated API. GitHub Pages does not serve national indexes. No match means unassessed, not low risk.</span></div>
      <section class="panel"><div class="panel-header"><div><h2>Private source readiness</h2>
        <span class="overline">Live, validated source mount only — never staged or deployed counts inferred from repository metadata</span></div>
        <button type="button" class="btn" id="epa-refresh">Refresh readiness</button></div>
        <div id="epa-mount-status" class="epa-mount-grid"><div class="loading-card">Checking private source mounts…</div></div>
      </section>
      <section class="panel"><div class="panel-header"><div><h2>Exact regulator-ID lookup</h2>
        <span class="overline">Original program identity only · 25 observations per request · read-only</span></div></div>
        <form id="epa-query" class="epa-query" autocomplete="off">
          <label for="epa-source">Regulator dataset<select id="epa-source" name="source">
            ${Object.entries(sources).map(([id,label])=>`<option value="${id}">${esc(label)}</option>`).join('')}
          </select></label>
          <label for="epa-native-id">Exact native source identifier<input type="text" id="epa-native-id" name="native_id" maxlength="160" required placeholder="Original regulator identifier"></label>
          <label id="epa-activity-label" class="epa-extra" hidden for="epa-activity">RCRA activity location (two letters)<input type="text" name="activity_location" id="epa-activity" pattern="[a-zA-Z]{2}" maxlength="2" placeholder="e.g. TX"></label>
          <label id="epa-year-label" class="epa-extra" hidden for="epa-year">TRI reporting year<select name="year" id="epa-year">${Array.from({length:38},(_,i)=>2024-i).map(y=>`<option value="${y}">${y}</option>`).join('')}</select></label>
          <button id="epa-search" class="btn primary" type="submit" disabled>Query exact ID</button>
        </form><div id="epa-query-result" aria-live="polite"></div>
      </section>
    </div>`;
  }
  function root() { return document.querySelector('.epa-evidence-page'); }
  function ready(source) { return status?.sources?.[source]?.state === 'mounted_source_only'; }
  function paintStatus() {
    if (!root()) return;
    const box = document.querySelector('#epa-mount-status');
    if (!status) {
      box.innerHTML = '<p class="small-muted">Source availability not verified. No data or risk inference is possible.</p>';return;
    }
    box.innerHTML = Object.entries(sources).map(([id,label])=>{
      const item = status.sources?.[id] || {state:'unavailable'};
      const connected=item.state==='mounted_source_only';
      const years=item.loaded_source_reporting_years;
      return `<div class="epa-mount-item"><div class="epa-mount-title">${esc(label)}</div>
        <strong>${connected?fmt(item.indexed_source_rows):'—'}</strong>
        <span class="epa-state">${esc(connected?'Verified private mount':item.state==='not_configured'?'Not installed':'Index unavailable')}</span>
        <small>${esc(connected?(id==='tri'?String(years?.length||0)+' reporting years · not unique sites':'Source rows, not physical sites'):'No live indexed coverage confirmed')}</small></div>`;
    }).join('');
    const submit=document.querySelector('#epa-search');
    if(submit)submit.disabled=!ready(selected);
  }
  function setSource(source) {
    // An in-flight lookup belongs to the previous source and must not be shown after selection changes.
    generation++;
    selected=sources[source]?source:'echo';
    const act=document.querySelector('#epa-activity-label'),year=document.querySelector('#epa-year-label');
    if(act)act.hidden=selected!=='rcra';
    if(year)year.hidden=selected!=='tri';
    const input=document.querySelector('#epa-native-id');
    if(input)input.value='';
    const result=document.querySelector('#epa-query-result');
    if(result)result.textContent='';
    paintStatus();
  }
  async function refresh() {
    if (!root()) return;
    const requestId=++generation;
    const box=document.querySelector('#epa-mount-status');
    if (window.PublicRiskAPI) {
      status=null;
      box.innerHTML='<div class="epa-unavailable">GitHub Pages is a static research preview. Open the authenticated private Facility Risk service to query a verified EPA source index. No EPA records are deployed to this preview.</div>';
      document.querySelector('#epa-search').disabled=true;
      return;
    }
    if(box)box.textContent='Checking authenticated, SHA-validated source mounts…';
    try {
      const response=await fetch('/api/epa/lane-b/status',{headers:{Accept:'application/json'},cache:'no-store'});
      if(requestId!==generation||!root())return;
      if(!response.ok)throw new Error(response.status===503?'EPA source API is disabled until the private indexes are installed and approved':response.status===401?'Private authentication required':'Private EPA readiness check failed (HTTP '+response.status+')');
      status=await response.json();
      if(requestId!==generation||!root())return;
      paintStatus();
    } catch (error) {
      if(requestId!==generation||!root())return;
      status=null;
      box.innerHTML=`<div class="epa-unavailable">${esc(error.message)}. No national source coverage is confirmed.</div>`;
      document.querySelector('#epa-search').disabled=true;
    }
  }
  function valuesRows(obj) {
    return Object.entries(obj||{}).filter(([,v])=>v!==null&&v!==undefined&&v!=='').slice(0,12)
      .map(([key,val])=>`<div class="epa-evidence-field"><span>${esc(key.replace(/_/g,' '))}</span><strong>${esc(String(typeof val==='object'?JSON.stringify(val):val).slice(0,220))}</strong></div>`).join('');
  }
  function paintResult(data) {
    const out=document.querySelector('#epa-query-result');
    if(!out)return;
    const count=data.observations_available;
    if(!count) {
      out.innerHTML='<div class="epa-unavailable">No matching record in this mounted source and identifier. This does not verify absence of hazards, pollution, compliance issues, facilities, or insurance losses.</div>';
      return;
    }
    const rows=data.rows||data.records||[];
    out.innerHTML=`<div class="epa-result-intro"><strong>${fmt(count)} source observation(s) for this exact ID</strong>
      <span>Unreviewed physical-property association · Not a verified incident or insured loss</span></div>
      ${rows.slice(0,25).map(r=>`<article class="epa-observation">
        <div class="epa-obs-head"><strong>${esc(r.regulatory_observation_kind||'Public EPA program interest')}</strong>
        <span>${esc(r.date||r.source_table||'Date not verified')}</span></div>
        <div class="epa-evidence-grid">${valuesRows(r.source_reported_findings||{
          source_registry_id:r.registry_id,public_program_id:r.program_id,
          latitude:r.latitude,longitude:r.longitude})}</div>
        <p>Native source identity: <code>${esc(r.source_identifier||r.program_id||'—')}</code>
        · Source row SHA256: <code>${esc(String(r.source_record_sha256||r.raw_sha256||'—').slice(0,64))}</code></p>
      </article>`).join('')}
      <p class="small-muted">Showing at most 25 original-regulator observations. No automatic facility match, clean-risk conclusion, or insurance loss attribution.</p>`;
  }
  async function search(form) {
    if(!root())return;
    const data=new FormData(form);
    const source=String(data.get('source')||'');
    const native=String(data.get('native_id')||'').trim();
    if(!sources[source]||!ready(source)||!native)return;
    const params=new URLSearchParams({native_id:native,limit:'25'});
    if(source==='rcra'){
      const code=String(data.get('activity_location')||'').trim().toUpperCase();
      if(!/^[A-Z]{2}$/.test(code)){document.querySelector('#epa-query-result').textContent='RCRA requires a two-letter activity location from the original record.';return;}
      params.set('activity_location',code);
    }
    if(source==='tri')params.set('year',String(data.get('year')||''));
    const out=document.querySelector('#epa-query-result');
    out.textContent='Checking exact regulator identifier in immutable private source index…';
    const requestId=++generation;
    try {
      const response=await fetch('/api/epa/lane-b/'+encodeURIComponent(source)+'/identity?'+params.toString(),
        {headers:{Accept:'application/json'},cache:'no-store'});
      if(requestId!==generation||!root())return;
      if(!response.ok)throw new Error(response.status===503?'Private source index unavailable':response.status===422?'Invalid source identifier or reporting period':'Lookup failed (HTTP '+response.status+')');
      const result=await response.json();
      if(requestId!==generation||!root())return;
      paintResult(result);
    }catch(error){if(requestId!==generation||!root())return;
      out.innerHTML=`<div class="epa-unavailable">${esc(error.message)}. Coverage cannot be concluded.</div>`;
    }
  }
  document.addEventListener('click',event=>{
    if(event.target.closest('#epa-refresh'))refresh();
  });
  document.addEventListener('change',event=>{
    if(event.target.matches('#epa-source'))setSource(event.target.value);
  });
  document.addEventListener('submit',event=>{
    if(event.target.matches('#epa-query')){event.preventDefault();search(event.target);}
  });
  window.EPAEvidenceUI={render,mount:refresh};
})();