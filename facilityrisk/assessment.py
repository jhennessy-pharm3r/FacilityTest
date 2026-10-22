"""Source-grounded facility assessment. Never imply a calibrated loss score.

This module deliberately separates observed regulatory facts, modeled regional
conditions, proximity records and independently documented operational events.
It is safe to render a useful assessment when evidence is missing.
"""
from __future__ import annotations

import csv
import io
import re
from urllib.parse import quote
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.parse import urlparse

from .db import items,one
from .intelligence import get_intelligence

DOMAINS={
    'property_damage':'Property damage',
    'business_interruption':'Business interruption',
    'environmental_liability':'Environmental liability',
    'supply_chain':'Supply chain',
    'resilience':'Resilience and protection'
}

def _url(value):
    try:
        p=urlparse(str(value or '').strip())
        return str(value).strip() if p.scheme=='https' and p.hostname and not p.username else ''
    except ValueError:
        return ''

def _report_time():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def build_assessment(conn,facility_id):
    """Produce an inspectable report, NOT an underwriting risk score."""
    facility=one(conn,'SELECT * FROM facilities WHERE id=?',(facility_id,))
    if facility is None:raise ValueError('Unknown facility')
    detail=get_intelligence(conn,facility_id)
    identifiers=detail['identifiers']
    verified_identifiers=[row for row in identifiers if row['status']=='verified']
    source_evidence=items(conn,'''SELECT id,source,program,date_raw,record_type,
       finding,value_text,source_url,evidence_scope,limitations,
       availability_date,match_quality,risk_domain FROM evidence
       WHERE facility_id=? ORDER BY source, id LIMIT 250''',(facility_id,))
    observations=items(conn,'''SELECT id,source,source_id,observed_date,observation,status,
       source_url,retrieved_at FROM regulatory_observations
       WHERE facility_id=? ORDER BY observed_date DESC,id''',(facility_id,))
    events=detail['incidents']
    sec=items(conn,'''SELECT id,company,facility_label,finding,filing_date,
       filing_form,filing_url,financial_impact,supply_impact,insurance_recovery,
       caveats,attribution,event_group FROM sec_findings
       WHERE facility_id=? ORDER BY filing_date DESC,id''',(facility_id,))
    nearby=items(conn,'''SELECT source_key,status,COUNT(*) AS records FROM external_event_candidates
       WHERE facility_id=? GROUP BY source_key,status ORDER BY source_key,status''',(facility_id,))
    regional_hazards=detail['hazard_checks']
    current_hazards=[h for h in regional_hazards if h.get('valid_for_current_site_point')]
    stale_hazards=[h for h in regional_hazards if not h.get('valid_for_current_site_point')]
    loc=detail['location']
    point_verified=bool(loc and loc.get('review_valid_for_current_coordinates'))
    profile=detail['profile']
    source_evidence_total=one(conn,'SELECT COUNT(*) AS n FROM evidence WHERE facility_id=?',(facility_id,))['n']
    available_date_count=one(conn,'''SELECT COUNT(*) AS n FROM evidence
                                  WHERE facility_id=? AND availability_date IS NOT NULL
                                  AND trim(availability_date)<>?''',(facility_id,''))['n']
    pending_crosswalks=sum(x['decision']=='pending' for x in detail['candidates'])
    has_fei=bool(facility['fei'])
    coverage={
       'physical_site':{'status':'verified' if point_verified else 'unassessed',
          'reason':'Current coordinates independently reviewed' if point_verified else
                   'Physical property coordinates missing, approximate or stale'},
       'regulatory_identity':{'status':'verified' if verified_identifiers else 'unassessed',
          'reason':str(len(verified_identifiers))+' reviewed source identifiers; '+str(pending_crosswalks)+' outstanding crosswalk candidates'},
       'environmental':{'status':'source_observations' if any('environment' in
                        (e['risk_domain'] or '').lower() for e in source_evidence) else 'unassessed',
          'reason':'Source records may include regulatory observations; independently assess each program and date'},
       'natural_hazards':{'status':'screened' if current_hazards and point_verified else 'unassessed',
          'reason':str(len(current_hazards))+' current property-point screenings; '+
                  str(len(stale_hazards))+' stale or legacy screenings require refresh. '+
                  'Mapped exposure is not insured property damage'},
       'operations_and_bi':{'status':'research_profile' if profile else 'unassessed',
          'reason':'Operations, protection and downtime exposures are not insured values unless documented'},
       'historical_outcomes':{'status':'retrospective_events' if events else 'unassessed',
          'reason':'Known cases are retrospective, not predictive validation; absence of cases is not absence of losses'},
       'pre_event_visibility':{'status':'partially_documented' if available_date_count else 'unassessed',
          'reason':str(available_date_count)+' of '+str(source_evidence_total)+' evidence rows have separately verified public availability dates'}
    }
    sections=[]
    for key,title in DOMAINS.items():
        note=(profile or {}).get(key)
        sections.append({'key':key,'title':title,
                         'assessment':note or 'Not assessed',
                         'source_scope':profile['source_scope'] if profile else '',
                         'status':'analyst_text' if note else 'unassessed'})
    action_items=[]
    if not point_verified: action_items.append('Verify the exact physical property point before local hazard screening')
    if not verified_identifiers:action_items.append('Corroborate FEI or applicable official site identifiers')
    if pending_crosswalks:action_items.append('Resolve pending cross-agency site matching candidates')
    if observations:action_items.append('Review regulatory observations with unconfirmed FEI-to-site attribution')
    if not profile:action_items.append('Collect construction, fire protection, water, power, BI values and recovery plans')
    if stale_hazards:action_items.append('Refresh or explicitly retire hazard overlays tied to an earlier or unreviewed site point')
    if not events:action_items.append('Research documented disruptions and comparable non-event periods')
    if available_date_count<source_evidence_total:action_items.append('Verify source publication dates before any historical prediction tests')
    return {
      'report_type':'facility_source_evidence_assessment',
      'generated_at':_report_time(),
      'facility':facility,
      'evaluation':'unranked_insufficient_calibration',
      'risk_score':None,
      'risk_probability':None,
      'facility_identity':{'observed_fei':facility['fei'],
                          'verified_identifiers':verified_identifiers,
                          'observed_identifiers':[r for r in identifiers if r['status']!='verified'],
                          'site_coordinate_verified':point_verified,
                          'site_review':loc,'pending_crosswalks':pending_crosswalks},
      'coverage':coverage,
      'sections':sections,
      'hazards':regional_hazards,
      'evidence':source_evidence,
      'evidence_total':source_evidence_total,
      'evidence_displayed':len(source_evidence),
      'evidence_export_limited':len(source_evidence)<source_evidence_total,
      'regulatory_observations':observations,
      'nearby_events_review_queue':nearby,
      'documented_events':events,
      'sec_disclosures':sec,
      'recommended_actions':action_items,
      'interpretation':[
          'No actuarially calibrated facility loss score or insurance pricing can be inferred.',
          'Missing information is unassessed and must not be recorded as low exposure.',
          'Regulatory registration or compliance classification is not property loss.',
          'Nearby events and modeled regional hazards do not prove facility impact.',
          'Stale or legacy hazard screenings are historical context, never the current property classification.',
          'Historical and SEC facts are retrospective until pre-event public availability is validated.',
          'SEC filing values and recovered amounts must not be added across repeated disclosures.'
      ]
    }

EVIDENCE_EXPORT_COLUMNS=(
    'id','facility_id','source','program','date_raw','record_type','finding',
    'value_text','record_ref','evidence_scope','match_quality','risk_domain',
    'source_url','limitations','origin','last_imported','availability_date',
    'spatial_distance_km'
)

def safe_csv_cell(value):
    """Neutralize spreadsheet formula injection while preserving raw text."""
    string=str(value if value is not None else '')
    if string.lstrip(' \t\r\n\ufeff').startswith(('=','+','-','@')):
        return "'"+string
    return string

def iter_evidence_csv(facility_id):
    """Read the complete private facility evidence in bounded database batches.

    Opens its own connection: response-stream generators outlive the request's
    dependency connection in some FastAPI versions. No temporary CSV is
    written to GitHub Pages, a public disk or an Actions artifact.
    """
    from .db import connect
    from .db import initialize
    connection=connect()
    try:
        # Schema has been initialized by the corresponding validated API call.
        buffer=io.StringIO()
        writer=csv.writer(buffer,lineterminator='\r\n')
        writer.writerow(EVIDENCE_EXPORT_COLUMNS)
        yield '\ufeff'+buffer.getvalue()
        cursor=connection.execute(
            'SELECT '+','.join(EVIDENCE_EXPORT_COLUMNS)+
            ' FROM evidence WHERE facility_id=? ORDER BY source,id',(facility_id,))
        while True:
            rows=cursor.fetchmany(250)
            if not rows:break
            buffer=io.StringIO();writer=csv.writer(buffer,lineterminator='\r\n')
            for row in rows:
                writer.writerow([safe_csv_cell(value) for value in row])
            yield buffer.getvalue()
    finally:
        connection.close()


def render_assessment_html(report,*,private_backend=False):
    """Escaped, printable, source-linked private HTML; no remote assets."""
    e=lambda v:escape(str(v if v is not None else ''),quote=True)
    site=report['facility']
    def link(url,caption='Source'):
        safe=_url(url)
        return '<a rel="noopener noreferrer" href="'+e(safe)+'">'+e(caption)+'</a>' if safe else 'Not supplied'
    def rows(items,func):
        return ''.join(func(item) for item in items) or '<tr><td colspan="4">Not assessed or no linked records</td></tr>'
    coverage=rows(report['coverage'].items(),
                  lambda kv:'<tr><td>'+e(kv[0].replace('_',' ').title())+'</td><td>'+e(kv[1]['status'])+
                  '</td><td colspan="2">'+e(kv[1]['reason'])+'</td></tr>')
    sections=''.join('<section><h2>'+e(s['title'])+'</h2><p>'+e(s['assessment'])+'</p>'+
                     ('<small>Context: '+e(s['source_scope'])+'</small>' if s['source_scope'] else '')+
                     '</section>' for s in report['sections'])
    evidence=rows(report['evidence'],lambda x:'<tr><td>'+e(x['source'])+'</td><td>'+
                  e(x['date_raw'] or 'Date unclassified')+'</td><td>'+
                  e((x['record_type'] or '')+': '+(x['finding'] or ''))+'</td><td>'+
                  link(x['source_url'])+'</td></tr>')
    hazards=rows(report['hazards'],lambda x:'<tr><td>'+e(x['peril'])+'</td><td>'+
                 e(x['status'])+'</td><td>'+e(x['description'] or '')+'</td><td>'+
                 link(x['source_url'])+'</td></tr>')
    actions=''.join('<li>'+e(a)+'</li>' for a in report['recommended_actions']) or '<li>No additional actions listed</li>'
    cautions=''.join('<li>'+e(x)+'</li>' for x in report['interpretation'])
    return ('''<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Facility Evidence Assessment</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{font-family:Arial,sans-serif;color:#22343b;margin:32px auto;max-width:1000px;padding:0 20px}
h1{margin-bottom:4px}h2{border-bottom:1px solid #cfd9d8;padding:9px 0;font-size:18px}
small,.muted{color:#526668}header{border-top:6px solid #517d7a;padding-top:18px}
table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:10px;text-align:left;
border-bottom:1px solid #dee5e4;vertical-align:top}th{background:#edf4f2}
p{line-height:1.6}.tag{font-weight:700;color:#8b4b3a}.columns{display:grid;grid-template-columns:1fr 1fr;gap:22px}
a{color:#245c61}section{break-inside:avoid}ul{line-height:1.65}
@media print{body{max-width:none;margin:0;padding:0}a{color:#22343b}.columns{display:block}}
</style></head><body><header><small>PHARM3R · PRIVATE RESEARCH</small><h1>Facility Evidence Assessment</h1>''' +
'<p><strong>'+e(site['name'])+'</strong> — '+e(site['company'] or '')+'</p>'+
'<p>'+e(site['address'] or '')+' | '+e(site['country'] or 'Country not established')+'</p>'+
'<p class="muted">Generated '+e(report['generated_at'])+' UTC · '+e(report['evaluation'])+
' · No loss probability or premium rating</p></header>'+
'<h2>Evidence coverage</h2><table><thead><tr><th>Dimension</th><th>Status</th><th colspan="2">Basis</th></tr></thead><tbody>'+coverage+'</tbody></table>'+
'<div class="columns">'+sections+'</div>'+
'<h2>Physical hazard screening</h2><table><tr><th>Peril</th><th>Status</th><th>Description</th><th>Reference</th></tr>'+hazards+'</table>'+
'<h2>Source-linked findings ('+e(report['evidence_total'])+')</h2>'+
('<p><a href="/api/facilities/'+quote(str(site['id']),safe='')+
 '/evidence.csv">Download complete private evidence CSV</a></p>'
 if private_backend else '')+
('<p class="muted">Only '+e(report['evidence_displayed'])+' of '+e(report['evidence_total'])+
' findings appear in this report preview. Export the complete evidence table for full review.</p>'
 if report['evidence_export_limited'] else '')+
'<table><tr><th>Source</th><th>Raw date</th><th>Finding</th><th>Evidence</th></tr>'+evidence+'</table>'+
'<p>Unverified regulatory observations: '+e(len(report['regulatory_observations']))+
'. Nearby-event candidates are excluded from confirmed site evidence.</p>'+
'<h2>Remaining research</h2><ul>'+actions+'</ul>'+
'<h2>Interpretation and limitations</h2><ul>'+cautions+'</ul>'+
'<footer><small>This source assessment is not an insurance rating, safety certification or liability determination.</small></footer>'+
'</body></html>')

def export_assessment(conn,facility_id,output):
    report=build_assessment(conn,facility_id)
    file=Path(output).expanduser().resolve()
    if file.suffix.lower() not in ('.html','.htm'):
        raise ValueError('Use an .html output file to keep the report printable')
    file.parent.mkdir(parents=True,exist_ok=True)
    file.write_text(render_assessment_html(report),encoding='utf-8')
    return {'status':'exported_private_assessment','facility_id':facility_id,
            'path':str(file),'evidence_count':report['evidence_total'],
            'risk_score':None,'bytes':file.stat().st_size}
