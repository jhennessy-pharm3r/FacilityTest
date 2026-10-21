"""Synchronous, permissioned facility research planning and source refresh.

A research plan is a durable checklist, not a promise of ongoing/background
monitoring. Live source actions require a separate explicit server opt-in and
the relevant verified property or regulator identifier.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid

from .db import one,items
from .ingest import utcnow
from .intelligence import audit,is_reviewed_site_coordinate

SCHEMA='''
CREATE TABLE IF NOT EXISTS research_runs (
 id TEXT PRIMARY KEY,
 facility_id TEXT NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
 created_at TEXT NOT NULL, created_by TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('planned','completed','partially_completed')),
 checklist_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_research_runs_site ON research_runs(facility_id,created_at);
CREATE TABLE IF NOT EXISTS research_attempts (
 id TEXT PRIMARY KEY, facility_id TEXT NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
 source_key TEXT NOT NULL, actor TEXT NOT NULL, attempted_at TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('ingested','source_unavailable','not_eligible','failed')),
 details_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_research_attempts_site ON research_attempts(facility_id,attempted_at);
'''

def initialize_research(conn):
    conn.executescript(SCHEMA)

def _region(site):
    s=(site['country'] or '').casefold()
    if s in ('us','usa','united states','united states of america','puerto rico'):return 'US'
    if s in ('ca','canada'):return 'CA'
    if s in ('ie','ireland'):return 'IE'
    return 'OTHER'

def checklist(conn,facility_id):
    site=one(conn,'SELECT * FROM facilities WHERE id=?',(facility_id,))
    if site is None:raise ValueError('Unknown facility')
    location=one(conn,'SELECT * FROM location_reviews WHERE facility_id=?',(facility_id,))
    reviewed_point=is_reviewed_site_coordinate(site,location)
    ids={r['namespace']:r['identifier'] for r in conn.execute("""
       SELECT namespace,identifier FROM identity_links
       WHERE facility_id=? AND status='verified'""",(facility_id,))}
    region=_region(site)
    records=items(conn,'SELECT source,status,COUNT(*) AS n FROM regulatory_observations WHERE facility_id=? GROUP BY source,status',(facility_id,))
    def task(code,title,state,requirement):
        return {'source_key':code,'title':title,'state':state,'required_next_step':requirement}
    result=[
        task('site_identity','Physical property and operator',
             'reviewed' if reviewed_point else 'blocked',
             'Independently verify physical parcel or building coordinates' if not reviewed_point else 'Refresh if property changes'),
        task('fda_fei','FDA FEI / manufacturer identity',
             'reviewed' if 'FDA_FEI' in ids else 'review_needed',
             'Confirm FEI with official firm records, not name alone'),
        task('environmental_registry','Environmental agency crosswalk',
             'reviewed' if region=='US' and 'EPA_FRS' in ids else 'review_needed',
             'Corroborate regulatory ID and physical-site address; use local source suggestions'),
        task('fema_flood','FEMA mapped flood exposure',
             'eligible' if region=='US' and reviewed_point else 'not_eligible',
             'Requires independently reviewed U.S. property point'),
        task('wri_water','WRI modeled water stress',
             'eligible' if reviewed_point else 'not_eligible',
             'Requires reviewed point; water stress is not actual utility interruption'),
        task('usgs_earthquake','USGS regional earthquake records',
             'eligible' if reviewed_point else 'not_eligible',
             'Requires reviewed point and user-specified observation dates'),
        task('epa_echo','EPA ECHO DFR regulatory detail',
             'eligible' if region=='US' and 'EPA_FRS' in ids else 'not_eligible',
             'Requires verified EPA FRS site identity'),
        task('severe_weather','NOAA / local storm-event sources',
             'manual_file' if region=='US' else 'jurisdiction_review',
             'Download current official source file and stage proximity only after location review'),
        task('sec_outcomes','SEC and public operational interruption evidence',
             'manual_review','Resolve disclosed site, event and source availability date'),
        task('engineering','Property protection and BI exposures',
             'manual_review','Obtain construction, sprinkler, utilities, downtime and insured values'),
        task('validation','Pre-event evidence and comparator controls',
             'manual_review','Require independently dated observations and documented event/no-event outcome')
    ]
    return {'facility_id':facility_id,'name':site['name'],
            'jurisdiction':region,'checks':result,
            'identity_pending_observations':records,
            'note':'This checklist does not assert that sources have been retrieved or sites verified.'}

def start_research(conn,facility_id,actor):
    plan=checklist(conn,facility_id)
    rid=uuid.uuid4().hex
    now=utcnow()
    with conn:
        conn.execute("""INSERT INTO research_runs
            (id,facility_id,created_at,created_by,status,checklist_json)
            VALUES(?,?,?,?,?,?)""",
            (rid,facility_id,now,actor,'planned',json.dumps(plan,ensure_ascii=False)))
        audit(conn,'research_plan_created',facility_id,actor,
              {'research_run_id':rid,'checked_sources':len(plan['checks'])})
    return {'research_run_id':rid,'created_at':now,'status':'planned',
            'plan':plan,'background_work_scheduled':False}

def research_history(conn,facility_id):
    if not one(conn,'SELECT id FROM facilities WHERE id=?',(facility_id,)):
        raise ValueError('Unknown facility')
    return {'current_checklist':checklist(conn,facility_id),
            'plans':items(conn,'''SELECT id,created_at,created_by,status
                  FROM research_runs WHERE facility_id=? ORDER BY created_at DESC,id DESC LIMIT 20''',(facility_id,)),
            'attempts':items(conn,'''SELECT id,source_key,actor,attempted_at,status,details_json
                  FROM research_attempts WHERE facility_id=? ORDER BY attempted_at DESC,id DESC LIMIT 50''',(facility_id,))}

class SourceNotEligible(ValueError):
    pass

LIVE_SOURCES=('fema_flood','wri_water','epa_echo','usgs_earthquake')

def run_source(conn,facility_id,source_key,actor,*,start='',end='',radius_km=150):
    """Run ONE explicit source now; record failures without inventing evidence."""
    if source_key not in LIVE_SOURCES:
        raise ValueError('Unknown or nonautomated research source')
    if os.environ.get('FACILITY_RISK_ENABLE_SOURCE_REQUESTS')!='1':
        raise ValueError('External source queries are disabled')
    plan=checklist(conn,facility_id)
    steps={t['source_key']:t for t in plan['checks']}
    check=steps[source_key]
    if check['state']!='eligible':
        raise SourceNotEligible('Source not eligible: '+check['required_next_step'])
    from .advanced_sources import fetch_fema,fetch_verified_echo
    from .connectors import fetch_usgs,fetch_aqueduct
    actions={'fema_flood':lambda:fetch_fema(conn,facility_id),
             'wri_water':lambda:fetch_aqueduct(conn,facility_id),
             'epa_echo':lambda:fetch_verified_echo(conn,facility_id),
             'usgs_earthquake':lambda:fetch_usgs(conn,facility_id,start,end,radius_km)}
    if source_key=='usgs_earthquake':
        if not (len(start)==10 and len(end)==10 and start<=end):
            raise ValueError('USGS requires YYYY-MM-DD start and end dates')
    try:
        result=actions[source_key]()
        status='ingested'
        detail={'result':result,'caveat':'Records are source observations, not insured losses'}
    except Exception as exc:
        status='source_unavailable' if isinstance(exc,(OSError,TimeoutError)) else 'failed'
        detail={'error_type':type(exc).__name__,'message':str(exc)[:300]}
    with conn:
        conn.execute("""INSERT INTO research_attempts
          (id,facility_id,source_key,actor,attempted_at,status,details_json)
          VALUES(?,?,?,?,?,?,?)""",
          (uuid.uuid4().hex,facility_id,source_key,actor,utcnow(),status,json.dumps(detail,default=str)))
        audit(conn,'research_source_attempt',facility_id,actor,
              {'source_key':source_key,'status':status})
    return {'facility_id':facility_id,'source':source_key,'status':status,**detail}
