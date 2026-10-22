"""Private, auditable insurance policy and coverage-term review.

Never expose this data through GitHub Pages. A submitted document hash/reference
is evidence claimed by a reviewer, not independent proof that a policy was read.
No premium, probability, loss or parametric payout is computed.
"""
from __future__ import annotations
import json
import math
import re
import uuid
from datetime import date, datetime, timezone
from urllib.parse import urlsplit

from .insurance import taxonomy
from .intelligence import audit

SCHEMA = """
CREATE TABLE IF NOT EXISTS insurance_policies (
 id TEXT PRIMARY KEY,
 facility_id TEXT NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
 insurer TEXT NOT NULL, policy_reference TEXT NOT NULL,
 start_date TEXT NOT NULL, end_date TEXT NOT NULL,
 location_schedule_reference TEXT NOT NULL,
 currency TEXT NOT NULL DEFAULT 'USD',
 total_insured_value REAL,
 created_by TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(facility_id,policy_reference)
);
CREATE INDEX IF NOT EXISTS idx_insurance_policy_facility ON insurance_policies(facility_id);
CREATE TABLE IF NOT EXISTS insurance_terms (
 id TEXT PRIMARY KEY,
 policy_id TEXT NOT NULL REFERENCES insurance_policies(id) ON DELETE CASCADE,
 coverage_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'unverified'
   CHECK(status IN ('unverified','verified_covered','verified_conditional','verified_excluded')),
 trigger_description TEXT NOT NULL DEFAULT '',
 limits REAL, deductible REAL, waiting_hours REAL,
 indemnity_days REAL, sublimit REAL,
 exclusions TEXT NOT NULL DEFAULT '',
 endorsements TEXT NOT NULL DEFAULT '',
 parametric_index TEXT NOT NULL DEFAULT '',
 parametric_threshold TEXT NOT NULL DEFAULT '',
 basis_risk TEXT NOT NULL DEFAULT '',
 revision INTEGER NOT NULL DEFAULT 1,
 changed_by TEXT NOT NULL, changed_at TEXT NOT NULL,
 reviewed_by TEXT, reviewed_at TEXT,
 source_document_reference TEXT, source_document_sha256 TEXT,
 UNIQUE(policy_id,coverage_id)
);
CREATE TABLE IF NOT EXISTS insurance_term_reviews (
 id TEXT PRIMARY KEY,
 term_id TEXT NOT NULL REFERENCES insurance_terms(id) ON DELETE CASCADE,
 proposed_status TEXT NOT NULL CHECK(proposed_status IN
   ('verified_covered','verified_conditional','verified_excluded')),
 term_revision INTEGER NOT NULL,
 document_reference TEXT NOT NULL, document_sha256 TEXT NOT NULL,
 rationale TEXT NOT NULL,
 requested_by TEXT NOT NULL, requested_at TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN
   ('pending','approved','rejected','invalidated')),
 decided_by TEXT, decided_at TEXT, decision_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_insurance_review_queue ON insurance_term_reviews(status,requested_at);
"""

VERIFIED = frozenset({'verified_covered','verified_conditional','verified_excluded'})
COVERAGE_IDS = frozenset(x['id'] for x in taxonomy())
MAX_MONEY = 1e15


def initialize_insurance_reviews(conn):
    conn.executescript(SCHEMA)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _actor(actor):
    if not isinstance(actor,str) or not re.fullmatch(r'[A-Za-z0-9._-]{3,64}',actor) or actor in (
        'local-development','service-account'):
        raise ValueError('An individually authenticated actor is required')
    return actor


def _text(value,limit=2000,required=False):
    if not isinstance(value,str):
        raise ValueError('Expected text input')
    value=value.strip()
    if len(value)>limit or (required and not value):
        raise ValueError('Missing or overlong text input')
    return value


def _amount(value):
    if value is None or value=='':return None
    if isinstance(value,bool):raise ValueError('Numeric value required')
    try:result=float(value)
    except (ValueError,TypeError):raise ValueError('Numeric value required') from None
    if not math.isfinite(result) or result<0 or result>MAX_MONEY:
        raise ValueError('Financial/time value outside accepted bounds')
    return result


def _date(value):
    value=_text(value,10,required=True)
    try:parsed=date.fromisoformat(value)
    except ValueError:raise ValueError('Dates must be ISO YYYY-MM-DD') from None
    if parsed.isoformat()!=value:raise ValueError('Dates must be ISO YYYY-MM-DD')
    return value


def _known(conn,query,args,msg):
    row=conn.execute(query,args).fetchone()
    if not row:raise ValueError(msg)
    return row


def create_policy(conn,facility_id,details,actor):
    """Policy metadata only; never upload policy text or confidential attachments."""
    actor=_actor(actor)
    if not isinstance(details,dict):raise ValueError('Policy metadata must be an object')
    _known(conn,'SELECT id FROM facilities WHERE id=?',(facility_id,),'Unknown facility')
    insurer=_text(details.get('insurer'),160,True)
    ref=_text(details.get('policy_reference'),140,True)
    location=_text(details.get('location_schedule_reference'),400,True)
    start,end=_date(details.get('start_date')),_date(details.get('end_date'))
    if end<start:raise ValueError('End date precedes start date')
    currency=_text(details.get('currency','USD'),3,True).upper()
    if not re.fullmatch(r'[A-Z]{3}',currency):raise ValueError('ISO currency code required')
    amount=_amount(details.get('total_insured_value'))
    policy_id=uuid.uuid4().hex
    try:
        with conn:
            conn.execute("""INSERT INTO insurance_policies(id,facility_id,insurer,policy_reference,
              start_date,end_date,location_schedule_reference,currency,total_insured_value,created_by,created_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
              (policy_id,facility_id,insurer,ref,start,end,location,currency,amount,actor,_now()))
            audit(conn,'policy_reference_created',facility_id,actor,
                  {'policy_id':policy_id,'period':[start,end]})
    except __import__('sqlite3').IntegrityError as exc:
        raise ValueError('Duplicate policy reference at this facility') from exc
    return {'policy_id':policy_id,'status':'metadata_only','verified_coverage':False}


def save_term(conn,policy_id,fields,actor):
    """Every edit invalidates prior verification, even when a revision is visually minor."""
    actor=_actor(actor)
    if not isinstance(fields,dict):raise ValueError('Coverage details must be an object')
    policy=_known(conn,'SELECT * FROM insurance_policies WHERE id=?',(policy_id,),'Unknown policy')
    key=_text(fields.get('coverage_id'),80,True)
    if key not in COVERAGE_IDS:raise ValueError('Unknown insurance coverage category')
    descriptions={}
    for name,limit in (
       ('trigger_description',1200),('exclusions',2000),('endorsements',2000),
       ('parametric_index',500),('parametric_threshold',500),('basis_risk',1000)):
        descriptions[name]=_text(fields.get(name,''),limit)
    values={name:_amount(fields.get(name)) for name in
         ('limits','deductible','waiting_hours','indemnity_days','sublimit')}
    existing=conn.execute('SELECT * FROM insurance_terms WHERE policy_id=? AND coverage_id=?',
                          (policy_id,key)).fetchone()
    uid=existing['id'] if existing else uuid.uuid4().hex
    revision=(existing['revision']+1) if existing else 1
    with conn:
        conn.execute("""INSERT INTO insurance_terms(id,policy_id,coverage_id,status,
           trigger_description,limits,deductible,waiting_hours,indemnity_days,sublimit,
           exclusions,endorsements,parametric_index,parametric_threshold,basis_risk,
           revision,changed_by,changed_at,reviewed_by,reviewed_at,
           source_document_reference,source_document_sha256)
           VALUES(?,?,?,'unverified',?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,NULL,NULL)
           ON CONFLICT(policy_id,coverage_id) DO UPDATE SET
            status='unverified',trigger_description=excluded.trigger_description,
            limits=excluded.limits,deductible=excluded.deductible,
            waiting_hours=excluded.waiting_hours,indemnity_days=excluded.indemnity_days,
            sublimit=excluded.sublimit,exclusions=excluded.exclusions,
            endorsements=excluded.endorsements,parametric_index=excluded.parametric_index,
            parametric_threshold=excluded.parametric_threshold,basis_risk=excluded.basis_risk,
            revision=excluded.revision,changed_by=excluded.changed_by,
            changed_at=excluded.changed_at,reviewed_by=NULL,reviewed_at=NULL,
            source_document_reference=NULL,source_document_sha256=NULL""",
           (uid,policy_id,key,descriptions['trigger_description'],
            values['limits'],values['deductible'],values['waiting_hours'],
            values['indemnity_days'],values['sublimit'],
            descriptions['exclusions'],descriptions['endorsements'],
            descriptions['parametric_index'],descriptions['parametric_threshold'],
            descriptions['basis_risk'],revision,actor,_now()))
        audit(conn,'policy_term_changed',policy['facility_id'],actor,
              {'term_id':uid,'revision':revision,'verified_coverage':False})
    return {'term_id':uid,'revision':revision,'status':'unverified'}


def propose_term_review(conn,term_id,details,actor):
    actor=_actor(actor)
    if not isinstance(details,dict):raise ValueError('Review proposal must be an object')
    row=_known(conn,'''SELECT t.*,p.facility_id FROM insurance_terms t
        JOIN insurance_policies p ON p.id=t.policy_id WHERE t.id=?''',(term_id,),
        'Unknown policy coverage term')
    status=details.get('proposed_status')
    if status not in VERIFIED:raise ValueError('Unsupported verified status')
    reference=_text(details.get('document_reference'),400,True)
    digest=_text(details.get('document_sha256'),64,True).lower()
    if not re.fullmatch(r'[0-9a-f]{64}',digest):
        raise ValueError('SHA-256 of reviewed document is required')
    rationale=_text(details.get('rationale'),2000,True)
    if len(rationale)<20:raise ValueError('Document review rationale is too short')
    uid=uuid.uuid4().hex
    with conn:
        conn.execute("""INSERT INTO insurance_term_reviews
           (id,term_id,proposed_status,term_revision,document_reference,document_sha256,
            rationale,requested_by,requested_at) VALUES(?,?,?,?,?,?,?,?,?)""",
            (uid,term_id,status,row['revision'],reference,digest,rationale,actor,_now()))
        audit(conn,'policy_coverage_review_proposed',row['facility_id'],actor,
              {'review_id':uid,'term_id':term_id,'proposed_status':status})
    return {'review_id':uid,'status':'pending','promoted':False}


def list_reviews(conn,status='pending',facility_id='',limit=100):
    if status not in ('pending','approved','rejected','invalidated','all'):
        raise ValueError('Unknown proposal status')
    clauses=[];args=[]
    if status!='all':clauses.append('r.status=?');args.append(status)
    if facility_id:clauses.append('p.facility_id=?');args.append(facility_id)
    rows=conn.execute("""SELECT r.*,t.coverage_id,p.facility_id,p.insurer,
           p.policy_reference FROM insurance_term_reviews r
           JOIN insurance_terms t ON t.id=r.term_id
           JOIN insurance_policies p ON p.id=t.policy_id """+
           ('WHERE '+' AND '.join(clauses) if clauses else '')+
           ' ORDER BY r.requested_at DESC,r.id DESC LIMIT ?',(*args,max(1,min(int(limit),200))))
    return {'items':[dict(x) for x in rows],
      'scope':'Private document-reference review; no claim or loss adjustment'}


def decide_term_review(conn,review_id,decision,actor,note):
    actor=_actor(actor)
    if decision not in ('approve','reject'):raise ValueError('Unknown review decision')
    note=_text(note,2000,True)
    if len(note)<12:raise ValueError('Independent decision rationale required')
    conn.execute('BEGIN IMMEDIATE')
    try:
        row=_known(conn,'''SELECT r.*,t.revision,t.policy_id,p.facility_id FROM insurance_term_reviews r
              JOIN insurance_terms t ON t.id=r.term_id
              JOIN insurance_policies p ON p.id=t.policy_id WHERE r.id=?''',
              (review_id,),'Unknown review request')
        if row['status']!='pending':raise ValueError('Review already decided')
        if row['requested_by']==actor:raise ValueError('A reviewer cannot approve their own proposal')
        next_status='approved' if decision=='approve' else 'rejected'
        if decision=='approve':
            if row['term_revision']!=row['revision']:
                next_status='invalidated'
            else:
                conn.execute("""UPDATE insurance_terms SET status=?,reviewed_by=?,reviewed_at=?,
                    source_document_reference=?,source_document_sha256=? WHERE id=?""",
                    (row['proposed_status'],actor,_now(),row['document_reference'],
                     row['document_sha256'],row['term_id']))
        conn.execute("""UPDATE insurance_term_reviews SET status=?,decided_by=?,
              decided_at=?,decision_note=? WHERE id=? AND status='pending'""",
             (next_status,actor,_now(),note,review_id))
        audit(conn,'policy_coverage_review_'+next_status,row['facility_id'],actor,
              {'review_id':review_id,'term_id':row['term_id'],
               'source_revision':row['term_revision']})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {'review_id':review_id,'status':next_status,
       'verified_status_promoted':next_status=='approved'}


def facility_policy_snapshot(conn,facility_id):
    _known(conn,'SELECT id FROM facilities WHERE id=?',(facility_id,),'Unknown facility')
    policies=[dict(x) for x in conn.execute("""SELECT * FROM insurance_policies
           WHERE facility_id=? ORDER BY end_date DESC,id""",(facility_id,))]
    today=date.today().isoformat()
    for p in policies:
        p['policy_period_status']=('future' if p['start_date']>today else
                 'expired' if p['end_date']<today else 'current')
        p['terms']=[dict(x) for x in conn.execute(
            'SELECT * FROM insurance_terms WHERE policy_id=? ORDER BY coverage_id',(p['id'],))]
        for t in p['terms']:
            t['effective_review_status']=(t['status'] if p['policy_period_status']=='current'
                else 'historical_or_future_'+t['status'])
    return {'facility_id':facility_id,'policies':policies,
       'document_reviewed_current_terms_count':sum(1 for p in policies
           if p['policy_period_status']=='current' for t in p['terms']
           if t['status'] in VERIFIED),
       'verified_current_coverage_count':sum(1 for p in policies
           if p['policy_period_status']=='current' for t in p['terms']
           if t['status'] in ('verified_covered','verified_conditional')),
       'verified_excluded_current_terms_count':sum(1 for p in policies
           if p['policy_period_status']=='current' for t in p['terms']
           if t['status']=='verified_excluded'),
       'interpretation':'Reviewed wording is conditional on the insured location and exact contract; no claim or payout is inferred'}


def compare_hazards_and_coverage(conn,facility_id):
    """Crosswalk current point-reviewed hazard *screenings* to documented terms."""
    from .intelligence import get_intelligence
    snapshot=facility_policy_snapshot(conn,facility_id)
    intel=get_intelligence(conn,facility_id)
    location=intel['location'] if intel else None
    reviewed=bool(location and location.get('review_valid_for_current_coordinates'))
    mapping={
      'flood':['flood','parametric_flood'], 'wind':['windstorm','parametric_wind'],
      'hurricane':['windstorm','parametric_wind'], 'earthquake':['earthquake','parametric_quake'],
      'wildfire':['wildfire','parametric_wildfire'], 'water':['utility','non_damage_bi']}
    terms={}
    for p in snapshot['policies']:
        if p['policy_period_status']!='current':continue
        for t in p['terms']:
            terms.setdefault(t['coverage_id'],[]).append({
                'policy_id':p['id'],'policy_reference':p['policy_reference'],
                'status':t['status'],'revision':t['revision'],
                'document_sha256':t['source_document_sha256']})
    rows=[]
    for h in intel['hazard_checks'] if intel else []:
        if not h['valid_for_current_site_point'] or not reviewed:continue
        peril=str(h['peril']).lower()
        applicable=next((v for k,v in mapping.items() if k in peril),[])
        rows.append({'peril':h['peril'],'hazard_status':h['status'],
          'hazard_source':h['source'],'hazard_source_url':h['source_url'],
          'hazard_context':h['description'],
          'related_coverage':[{ 'coverage_id':k,'terms':terms.get(k,[]),
             'verification_status':'document_reviewed' if any(
                 a['status'] in VERIFIED for a in terms.get(k,[])) else 'unknown_or_unverified'}
              for k in applicable]})
    return {'facility_id':facility_id,'site_coordinate_verified':reviewed,
       'current_screened_perils':rows,'policy_count':len(snapshot['policies']),
       'warning':'Hazard classification, insured contract coverage and payout are different. Empty results mean unassessed, not safe.',
       'risk_score':None,'insured_loss_estimate':None}
