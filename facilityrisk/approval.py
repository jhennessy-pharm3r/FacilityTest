"""Two-person source-identity review, not an insurer acceptance decision.

Never promote an identity until a second authenticated actor approves the
exact reviewer-submitted site, source record, location and evidence URL.
"""
from __future__ import annotations
import json
import math
import uuid
from urllib.parse import urlsplit
from .ingest import utcnow
from .intelligence import audit,review_location,verify_fei,decide_candidate

SCHEMA="""
CREATE TABLE IF NOT EXISTS review_approvals (
 id TEXT PRIMARY KEY,
 facility_id TEXT NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
 action TEXT NOT NULL CHECK(action IN ('location','fei','match_candidate')),
 payload_json TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected','invalidated')),
 requested_by TEXT NOT NULL,requested_at TEXT NOT NULL,
 decided_by TEXT,decided_at TEXT,decision_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_review_queue ON review_approvals(status,requested_at);
CREATE INDEX IF NOT EXISTS idx_review_facility ON review_approvals(facility_id,status);
"""

def initialize_approvals(conn):
    conn.executescript(SCHEMA)

def _https(value):
    try:
        p=urlsplit(value)
        return bool(p.scheme=='https' and p.hostname and not p.username and not p.password)
    except (TypeError,ValueError):return False

def create_proposal(conn,action,facility_id,payload,actor):
    if action not in ('location','fei','match_candidate'):raise ValueError('Unknown review action')
    if not isinstance(payload,dict):raise ValueError('Review details must be an object')
    if not actor or actor in ('service-account','local-development'):
        raise ValueError('An authenticated individual reviewer is required')
    url=payload.get('evidence_url')
    note=str(payload.get('note') or '').strip()
    if not _https(url):raise ValueError('HTTPS corroboration URL required')
    if not 12<=len(note)<=2000:raise ValueError('Detailed rationale required (12-2000 characters)')
    site=conn.execute('SELECT * FROM facilities WHERE id=?',(facility_id,)).fetchone()
    if not site:raise ValueError('Unknown facility')
    evidence={'evidence_url':url,'note':note}
    if action=='location':
        precision=payload.get('precision')
        if precision not in ('city','approximate','site_verified','property_polygon'):
            raise ValueError('Invalid location precision')
        evidence['precision']=precision
        if precision in ('site_verified','property_polygon'):
            try:lat=float(site['latitude']);lon=float(site['longitude'])
            except (ValueError,TypeError):raise ValueError('Physical site coordinates required') from None
            if not (math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180):
                raise ValueError('Invalid physical site point')
            evidence.update(latitude=lat,longitude=lon)
    elif action=='fei':
        if not site['fei']:raise ValueError('No observed facility FEI')
        evidence['fei']=site['fei']
    else:
        ident=str(payload.get('candidate_id') or '')
        record=conn.execute('SELECT * FROM match_candidates WHERE id=? AND facility_id=?',
                            (ident,facility_id)).fetchone()
        if not record:raise ValueError('Unknown candidate')
        decision=payload.get('decision')
        if decision not in ('accepted','rejected'):raise ValueError('Invalid candidate decision')
        evidence.update(candidate_id=ident,decision=decision,
                        namespace=record['namespace'],identifier=record['identifier'],
                        source_name=record['candidate_name'],
                        source_address=record['candidate_address'],
                        source_retrieved_at=record['retrieved_at'])
    uid=uuid.uuid4().hex
    with conn:
        conn.execute("""INSERT INTO review_approvals
           (id,facility_id,action,payload_json,status,requested_by,requested_at)
           VALUES (?,?,?,?,?,?,?)""",
           (uid,facility_id,action,json.dumps(evidence,sort_keys=True),
            'pending',actor,utcnow()))
        audit(conn,'independent_review_proposed',facility_id,actor,
              {'approval_id':uid,'action':action})
    return {'approval_id':uid,'status':'pending','facility_id':facility_id,
            'requested_by':actor,'promotion_performed':False}

def list_approvals(conn,status='pending',facility_id='',limit=100):
    if status not in ('pending','approved','rejected','invalidated','all'):
        raise ValueError('Unknown review status')
    criteria=[];values=[]
    if status!='all':criteria.append('status=?');values.append(status)
    if facility_id:criteria.append('facility_id=?');values.append(facility_id)
    where=(' WHERE '+' AND '.join(criteria)) if criteria else ''
    rows=conn.execute('SELECT * FROM review_approvals'+where+
                      ' ORDER BY requested_at DESC,id DESC LIMIT ?',
                      (*values,max(1,min(int(limit),200))))
    return {'items':[dict(r) for r in rows],
            'caveat':'Independent source-identity verification is not underwriting approval'}

def decide_approval(conn,approval_id,decision,actor,note):
    if decision not in ('approve','reject'):raise ValueError('Invalid approval decision')
    if not actor or actor in ('service-account','local-development'):
        raise ValueError('An independently authenticated approver is required')
    if len((note or '').strip())<12:raise ValueError('Detailed independent decision required')
    # Lock before reading pending state, otherwise two parallel approvers can race.
    conn.execute('BEGIN IMMEDIATE')
    try:
        request=conn.execute('SELECT * FROM review_approvals WHERE id=?',(approval_id,)).fetchone()
        if request is None:raise ValueError('Unknown review proposal')
        if request['status']!='pending':raise ValueError('Review proposal already decided')
        if request['requested_by']==actor:raise ValueError('A reviewer cannot approve their own proposal')
        p=json.loads(request['payload_json'])
        site=conn.execute('SELECT * FROM facilities WHERE id=?',(request['facility_id'],)).fetchone()
        if not site:raise ValueError('Facility no longer exists')
        status='approved' if decision=='approve' else 'rejected'
        if decision=='approve':
            if request['action']=='location' and p['precision'] in ('site_verified','property_polygon'):
                if site['latitude']!=p['latitude'] or site['longitude']!=p['longitude']:
                    status='invalidated'
            elif request['action']=='fei':
                if site['fei']!=p['fei']:status='invalidated'
            elif request['action']=='match_candidate':
                current=conn.execute('SELECT * FROM match_candidates WHERE id=? AND facility_id=?',
                        (p['candidate_id'],request['facility_id'])).fetchone()
                if (not current or current['namespace']!=p['namespace']
                    or current['identifier']!=p['identifier']
                    or current['candidate_name']!=p['source_name']
                    or current['candidate_address']!=p['source_address']
                    or current['retrieved_at']!=p['source_retrieved_at']):
                    status='invalidated'
            if status=='approved':
                if request['action']=='location':
                    review_location(conn,request['facility_id'],p['precision'],p['evidence_url'],
                                    request['requested_by'],p['note'],commit=False)
                elif request['action']=='fei':
                    verify_fei(conn,request['facility_id'],request['requested_by'],
                               p['evidence_url'],p['note'],commit=False)
                else:
                    decide_candidate(conn,p['candidate_id'],p['decision'],request['requested_by'],
                                     p['evidence_url'],p['note'],commit=False)
        cur=conn.execute("""UPDATE review_approvals SET status=?,decided_by=?,decided_at=?,decision_note=?
                            WHERE id=? AND status='pending'""",
                  (status,actor,utcnow(),note.strip()[:2000],approval_id))
        if cur.rowcount!=1:raise ValueError('Review decision was concurrently updated')
        audit(conn,'independent_review_'+status,request['facility_id'],actor,
              {'approval_id':approval_id,'requested_by':request['requested_by'],
               'source_review_action':request['action']})
        conn.commit()
        return {'approval_id':approval_id,'status':status,
                'requested_by':request['requested_by'],'decided_by':actor,
                'promotion_performed':status=='approved',
                'caveat':'Identity evidence was reviewed; insurance loss/risk not approved'}
    except Exception:
        conn.rollback()
        raise
