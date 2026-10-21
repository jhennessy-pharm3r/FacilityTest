"""Curated public primary-source case studies, distinct from analyst evidence."""
from __future__ import annotations
import json
from pathlib import Path
from .ingest import stable_id,utcnow
from .intelligence import make_underwriting_profile

PATH=Path(__file__).resolve().parents[1]/'web'/'case-studies.json'


def seed_cases(conn):
    data=json.loads(PATH.read_text(encoding='utf-8'))
    count=0
    for case in data['cases']:
        f=conn.execute('SELECT id FROM facilities WHERE id=?',(case['local_facility_id'],)).fetchone()
        if not f:continue
        fid=f['id']
        conn.execute('''INSERT INTO historical_events
        (id,facility_id,title,peril,incident_date,operational_outcome,production_effect,financial_effect,
         resilience_effect,pre_event_evidence_status,attribution_note,source_url,updated_at)
         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
         title=excluded.title,financial_effect=excluded.financial_effect,
         pre_event_evidence_status=excluded.pre_event_evidence_status,updated_at=excluded.updated_at''',
         (case['id'],fid,case['title'],case['peril'],case['incident_date'],case['outcome'],
          case['summary'],case['financial_effect'],case['resilience'],case['pre_event_evidence_status'],
          'Public issuer/agency evidence, not an insured loss run',case['milestones'][0]['source_url'],utcnow()))
        for m in case['milestones']:
            mid=stable_id('milestone',case['id'],m['date'],m['source_url'])
            conn.execute('''INSERT INTO event_milestones
               (id,event_id,event_date,publication_date,stage,fact,source_url,timing,interpretation_note)
               VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET fact=excluded.fact,
               interpretation_note=excluded.interpretation_note''',
               (mid,case['id'],m['date'],m['publication_date'],m['stage'],m['fact'],m['source_url'],m['timing'],m['note']))
        make_underwriting_profile(conn,fid,case['underwriting'],actor='public-source-case-seed',
            source_scope='Primary-source retrospective case study, NOT individual insurance coverage',
            source_url=case['milestones'][0]['source_url'])
        count+=1
    conn.commit()
    return {'cases_seeded':count,'milestones':conn.execute('SELECT COUNT(*) FROM event_milestones').fetchone()[0]}
