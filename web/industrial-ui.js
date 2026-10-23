/* Authenticated private industrial source explorer.
 * Not included in GitHub Pages. Only source observations/case references,
 * never original free-text or inferred insured-property matches.
 */
(() => {
  'use strict';
  const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g,c=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
  const readable = x => Number(x ?? 0).toLocaleString('en-US');
  const sourceName = k => k==='csb' ? 'CSB · September 2026 release' :
    k.replace('nrc_','USCG NRC · reporting year ');
  function safeURL(value){
    try {
      const u = new URL(value);
      return u.protocol==='https:'&&['nrc.uscg.mil','www.csb.gov'].includes(u.hostname)?u.href:null;
    }catch{return null;}
  }
  function setMessage(target,msg){if(target)target.textContent=msg;}
  function cell(tr,value){
    const td=document.createElement('td');
    td.textContent=String(value ?? 'Unknown');
    tr.appendChild(td);
    return td;
  }
  function tableRows(target,items,fields){
    target.replaceChildren();
    if(!items.length){
      const tr=document.createElement('tr');
      const td=document.createElement('td');
      td.colSpan=fields.length;
      td.textContent='No observations in this installed publisher source matching these filters. This does not establish zero incidents.';
      tr.appendChild(td);target.appendChild(tr);
      return;
    }
    for(const item of items){
      const tr=document.createElement('tr');
      for(const k of fields){
        if(k==='source_url'){
          const td=document.createElement('td');
          const url=safeURL(item[k]);
          if(url){
            const a=document.createElement('a');
            a.href=url;a.target='_blank';a.rel='noopener noreferrer';
            a.textContent='Original agency source ↗';
            td.appendChild(a);
          }else td.textContent='Publisher URL unavailable';
          tr.appendChild(td);
        }else cell(tr,item[k]);
      }
      target.appendChild(tr);
    }
  }
  function mount(root,mounted,api){
    if(!root || !mounted)return;
    const incidents=mounted.industrial_incidents || {};
    const enforcement=mounted.phmsa_wms_enforcement || {};
    const incidentReady=['ready_private','ready_private_partial'].includes(incidents.state);
    const missingNrc=Array.isArray(incidents.missing_nrc_source_years)?incidents.missing_nrc_source_years:[];
    const enforcementReady=enforcement.state==='ready_private';
    const namespaces=incidentReady?Object.keys(incidents.source_counts||{}):[];
    namespaces.sort((a,b)=>a==='csb'?-1:b==='csb'?1:b.localeCompare(a));
    if(!incidents.state&&!enforcement.state)return;
    const parent=document.createElement('section');
    parent.className='panel industrial-private-explorer';
    parent.innerHTML=`
      <div class="panel-header"><div>
        <h2>Private industrial incident evidence</h2>
        <span class="overline">Authenticated source-only indexes · no automatic insured-site attribution</span>
      </div></div>
      <div class="intel-card-body">
        <p class="industrial-disclaimer">Official NRC notifications and CSB releases are unverified reporting observations, not confirmed accidents or paid insurance losses. PHMSA enforcement cases have a different unit of record and are not included in incident counts. Never use missing records as evidence of low risk.</p>
        <div class="industrial-metrics">
          <div><strong>${incidentReady?readable(incidents.indexed_source_records):'Not mounted'}</strong><span>NRC + CSB source observations</span></div>
          <div><strong>${enforcementReady?readable(enforcement.indexed_source_records):'Not mounted'}</strong><span>PHMSA enforcement case rows</span></div>
          <div><strong>${incidentReady?readable(incidents.review_only_pairs):'Not measured'}</strong><span>Cross-agency candidates for human review</span></div>
        </div>
        <p class="small-muted">Index readiness only; physical insured facilities verified: 0. Production verification is separate. Source vintages are not accident years.</p>
        ${missingNrc.length?'<p class="industrial-disclaimer" role="status"><strong>Partial NRC source coverage:</strong> '+esc(missingNrc.join(', '))+' not available in this installed release. Do not treat absent years as zero incidents or complete national history.</p>':''}
      </div>
      <div class="industrial-query-grid">
        <section class="industrial-query-panel">
          <h3>Regulatory incident notifications</h3>
          <form id="industrial-events-form" class="industrial-controls">
            <label>Reporting cohort <select id="industrial-source-select" aria-label="Incident source cohort"></select></label>
            <label>As-reported state <input id="industrial-state" aria-label="Source-reported state filter" maxlength="80" placeholder="e.g. TX" /></label>
            <label>Occurred after <input id="industrial-since" type="date" aria-label="Event occurrence date lower bound" /></label>
            <button type="submit" class="btn tiny">Query source</button>
          </form>
          <p class="small-muted" id="industrial-events-message" role="status"></p>
          <div class="table-wrap"><table>
            <thead><tr><th>Native report ID</th><th>Reported incident date</th><th>City</th><th>State</th><th>Evidence</th><th>Publisher</th></tr></thead>
            <tbody id="industrial-events-rows"></tbody></table></div>
          <div class="industrial-page-controls"><button type="button" class="btn tiny" id="industrial-prev">Previous</button><span id="industrial-page-count"></span><button type="button" class="btn tiny" id="industrial-next">Next</button></div>
        </section>
        <section class="industrial-query-panel">
          <h3>PHMSA enforcement case index</h3>
          <form id="industrial-wms-form" class="industrial-controls">
            <label>Operator ID <input id="industrial-operator" aria-label="PHMSA native Operator ID" maxlength="30" placeholder="Native operator ID" /></label>
            <button type="submit" class="btn tiny">Search cases</button>
          </form>
          <p class="small-muted" id="industrial-wms-message" role="status"></p>
          <div class="table-wrap"><table>
            <thead><tr><th>Case number</th><th>Opened</th><th>Operator ID</th><th>Status</th><th>Report reference</th></tr></thead>
            <tbody id="industrial-wms-rows"></tbody></table></div>
        </section>
      </div>
    `;
    // Put interactive evidence immediately after the private index readiness
    // scorecard, before long publisher connectivity inventories.
    const summaryCard=root.querySelector('section.intel-card');
    if(summaryCard && summaryCard.parentElement===root){
      summaryCard.insertAdjacentElement('afterend',parent);
    }else{
      root.prepend(parent);
    }
    const $ = selector=>parent.querySelector(selector);
    const selector=$('#industrial-source-select');
    for(const namespace of namespaces){
      const option=document.createElement('option');
      option.value=namespace;option.textContent=sourceName(namespace);
      selector.appendChild(option);
    }
    let offset=0,total=0,busy=false,latestRequest=0;
    const pageSize=25;
    const previous=$('#industrial-prev');
    const next=$('#industrial-next');
    function updatePager(){
      previous.disabled=busy||offset===0||!incidentReady;
      next.disabled=busy||offset+pageSize>=total||!incidentReady;
      setMessage($('#industrial-page-count'),total?
        `${readable(offset+1)}–${readable(Math.min(offset+pageSize,total))} of ${readable(total)}`:
        'No source rows shown');
    }
    async function fetchObservations(){
      if(!incidentReady){setMessage($('#industrial-events-message'),
        'No verified NRC/CSB index is mounted on this private backend.');return;}
      // A user may change reporting cohort while the initial async CSB
      // lookup is still running. Always start the new request, but ignore
      // the stale result: otherwise a CSB count appears mislabeled NRC.
      const requestNumber=++latestRequest;
      const requestSource=selector.value;
      busy=true;updatePager();
      setMessage($('#industrial-events-message'),'Loading read-only source observations…');
      const params=new URLSearchParams({source:requestSource,limit:String(pageSize),offset:String(offset)});
      if($('#industrial-state').value.trim())params.set('state',$('#industrial-state').value.trim());
      if($('#industrial-since').value)params.set('since',$('#industrial-since').value);
      try{
        const data=await api('industrial/observations?'+params);
        if(!parent.isConnected || requestNumber!==latestRequest)return;
        total=data.total||0;
        tableRows($('#industrial-events-rows'),data.items||[],
          ['publisher_native_id','incident_date','city','state','evidence_status','source_url']);
        setMessage($('#industrial-events-message'),
          `${sourceName(requestSource)} · ${readable(total)} source rows in this mounted release. No insured-site or loss match.`);
      }catch(e){
        if(parent.isConnected && requestNumber===latestRequest){total=0;$('#industrial-events-rows').replaceChildren();
          setMessage($('#industrial-events-message'),`Source query unavailable: ${e.message}. Do not infer zero risk.`);}
      }finally{if(requestNumber===latestRequest){busy=false;updatePager();}}
    }
    $('#industrial-events-form').addEventListener('submit',ev=>{
      ev.preventDefault();offset=0;fetchObservations();
    });
    previous.addEventListener('click',()=>{offset=Math.max(0,offset-pageSize);fetchObservations();});
    next.addEventListener('click',()=>{if(offset+pageSize<total){offset+=pageSize;fetchObservations();}});
    $('#industrial-wms-form').addEventListener('submit',async ev=>{
      ev.preventDefault();
      if(!enforcementReady){setMessage($('#industrial-wms-message'),
        'The PHMSA enforcement-case index is not mounted. This does not establish zero pipeline incidents.');return;}
      const operator=$('#industrial-operator').value.trim();
      const params=new URLSearchParams({limit:'25',offset:'0'});
      if(operator)params.set('operator_id',operator);
      setMessage($('#industrial-wms-message'),'Loading native PHMSA case references…');
      try{
        const result=await api('industrial/phmsa-enforcement?'+params);
        if(!parent.isConnected)return;
        const enriched=(result.items||[]).map(row=>({
          ...row,
          report_reference:row.report_type&&row.report_number?
            row.report_type+' / '+row.report_number:'No typed report reference'
        }));
        tableRows($('#industrial-wms-rows'),enriched,
          ['case_number','opened_date','operator_id','case_status','report_reference']);
        setMessage($('#industrial-wms-message'),
          `${readable(result.total)} enforcement case rows. They are NOT a census of PHMSA reportable pipeline accidents.`);
      }catch(e){
        if(parent.isConnected)setMessage($('#industrial-wms-message'),
          `Enforcement source query unavailable: ${e.message}. This is not proof of zero incidents.`);
      }
    });
    if(!incidentReady){selector.disabled=true;$('#industrial-events-form').querySelector('button').disabled=true;}
    updatePager();
    if(incidentReady)fetchObservations();
  }
  window.IndustrialUI={mount};
})();
