"""Facility physical asset hierarchy with audited identity-only review.

A registry identity, a campus, a building, an insured unit and a parcel are
different concepts. Corroborating an asset's identity NEVER approves its
coordinates for hazard classification and never attaches insurance coverage.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import re
import sqlite3
import uuid
from urllib.parse import urlsplit

from .intelligence import audit

ASSET_TYPES=frozenset({'campus','building','leased_unit','parcel','warehouse','utility_node','other'})
REVIEW_STATUS=frozenset({'identity_corroborated','rejected'})
SNAPSHOT_FIELDS=('facility_id','parent_asset_id','asset_type','name','address','country',
                 'reported_operator','reported_parent','latitude','longitude',
                 'source_url','source_record_ref','revision','status')

SCHEMA="""
CREATE TABLE IF NOT EXISTS facility_assets (
 id TEXT PRIMARY KEY,
 facility_id TEXT NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
 parent_asset_id TEXT REFERENCES facility_assets(id),
 asset_type TEXT NOT NULL CHECK(asset_type IN
   ('campus','building','leased_unit','parcel','warehouse','utility_node','other')),
 name TEXT NOT NULL,
 address TEXT NOT NULL DEFAULT '',
 country TEXT NOT NULL DEFAULT '',
 reported_operator TEXT NOT NULL DEFAULT '',
 reported_parent TEXT NOT NULL DEFAULT '',
 latitude REAL,longitude REAL,
 coordinate_quality TEXT NOT NULL DEFAULT 'source_observed_unverified',
 source_url TEXT NOT NULL DEFAULT '',
 source_record_ref TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'candidate' CHECK(status IN
   ('candidate','identity_corroborated','rejected')),
 revision INTEGER NOT NULL DEFAULT 1,
 created_by TEXT NOT NULL,created_at TEXT NOT NULL,
 changed_by TEXT NOT NULL,changed_at TEXT NOT NULL,
 reviewed_by TEXT,reviewed_at TEXT,
 CHECK(latitude IS NULL OR (latitude BETWEEN -90 AND 90)),
 CHECK(longitude IS NULL OR (longitude BETWEEN -180 AND 180)),
 CHECK((latitude IS NULL AND longitude IS NULL) OR
       (latitude IS NOT NULL AND longitude IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_facility_assets_site ON facility_assets(facility_id,parent_asset_id);
CREATE INDEX IF NOT EXISTS idx_facility_assets_review_status ON facility_assets(status);
CREATE TABLE IF NOT EXISTS facility_asset_reviews (
 id TEXT PRIMARY KEY,
 asset_id TEXT NOT NULL REFERENCES facility_assets(id) ON DELETE CASCADE,
 proposed_status TEXT NOT NULL CHECK(proposed_status IN ('identity_corroborated','rejected')),
 revision INTEGER NOT NULL,
 source_snapshot_sha256 TEXT NOT NULL,
 review_evidence_url TEXT NOT NULL,
 rationale TEXT NOT NULL,
 requested_by TEXT NOT NULL,requested_at TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN
   ('pending','approved','rejected','invalidated')),
 decided_by TEXT,decided_at TEXT,decision_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_asset_review_queue ON facility_asset_reviews(status,requested_at);
"""

def initialize_assets(conn):
    conn.executescript(SCHEMA)

def _time():
    return datetime.now(timezone.utc).isoformat()

def _person(actor):
    if not isinstance(actor,str) or not re.fullmatch(r'[A-Za-z0-9._-]{3,64}',actor) or actor in (
        'local-development','service-account'):
        raise ValueError('Distinct authenticated personal account required')
    return actor

def _text(value,length=250,required=False):
    if not isinstance(value,str):
        raise ValueError('Expected text input')
    value=' '.join(value.split())
    if len(value)>length or (required and not value):
        raise ValueError('Missing or overlong text field')
    return value

def _https(value,required=False):
    value=_text(value,1200,required)
    if not value:return ''
    try:u=urlsplit(value)
    except ValueError:raise ValueError('Malformed evidence reference URL') from None
    if u.scheme!='https' or not u.hostname or u.username or u.password:
        raise ValueError('HTTPS publisher or corroborating document URL required')
    return value

def _geo(value,lo,hi):
    if value is None or value=='':return None
    if isinstance(value,bool):raise ValueError('Numeric coordinate required')
    try:n=float(value)
    except (ValueError,TypeError):raise ValueError('Numeric coordinate required') from None
    if not math.isfinite(n) or not lo<=n<=hi:
        raise ValueError('Invalid source-reported geographic coordinate')
    return n

def _candidate(fields):
    if not isinstance(fields,dict):raise ValueError('Expected physical asset object')
    t=_text(fields.get('asset_type'),40,True)
    if t not in ASSET_TYPES:raise ValueError('Unknown physical asset type')
    country=_text(fields.get('country',''),2).upper()
    if country and not re.fullmatch(r'[A-Z]{2}',country):
        raise ValueError('Country must be an explicit two-letter ISO code or empty')
    lat=_geo(fields.get('latitude'),-90,90)
    lon=_geo(fields.get('longitude'),-180,180)
    if (lat is None)!=(lon is None):raise ValueError('Coordinates must be a complete point or absent')
    return {'asset_type':t,'name':_text(fields.get('name'),250,True),
       'address':_text(fields.get('address',''),350),'country':country,
       'reported_operator':_text(fields.get('reported_operator',''),250),
       'reported_parent':_text(fields.get('reported_parent',''),250),
       'latitude':lat,'longitude':lon,
       'source_url':_https(fields.get('source_url','')),
       'source_record_ref':_text(fields.get('source_record_ref',''),160)}

def _required(conn,query,args,message):
    row=conn.execute(query,args).fetchone()
    if not row:raise ValueError(message)
    return row

def _fingerprint(row):
    d={k:row[k] for k in SNAPSHOT_FIELDS}
    return sha256(json.dumps(d,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()

def _same_facility_parent(conn,facility_id,parent):
    if not parent:return None
    _required(conn,'SELECT id FROM facility_assets WHERE id=? AND facility_id=?',
              (parent,facility_id),'Parent asset must belong to the same investigated facility')
    return parent

def create_asset(conn,facility_id,details,actor):
    actor=_person(actor)
    _required(conn,'SELECT id FROM facilities WHERE id=?',(facility_id,),'Unknown research facility')
    fields=_candidate(details)
    parent=_same_facility_parent(conn,facility_id,_text(details.get('parent_asset_id',''),64))
    ident=uuid.uuid4().hex;now=_time()
    with conn:
        conn.execute("""INSERT INTO facility_assets(id,facility_id,parent_asset_id,
            asset_type,name,address,country,reported_operator,reported_parent,
            latitude,longitude,coordinate_quality,source_url,source_record_ref,
            status,revision,created_by,created_at,changed_by,changed_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,'source_observed_unverified',?,?,'candidate',1,?,?,?,?)""",
            (ident,facility_id,parent,fields['asset_type'],fields['name'],fields['address'],
             fields['country'],fields['reported_operator'],fields['reported_parent'],
             fields['latitude'],fields['longitude'],fields['source_url'],
             fields['source_record_ref'],actor,now,actor,now))
        audit(conn,'physical_asset_candidate_created',facility_id,actor,{
            'asset_id':ident,'asset_type':fields['asset_type'],'source_ref':fields['source_record_ref']})
    return {'asset_id':ident,'status':'candidate','coordinate_verified':False}

def revise_asset(conn,asset_id,details,actor):
    actor=_person(actor)
    if not isinstance(details,dict):raise ValueError('Expected physical asset revision')
    row=_required(conn,'SELECT * FROM facility_assets WHERE id=?',(asset_id,),'Unknown physical asset')
    fields=_candidate({k:details.get(k,row[k]) for k in
             ('asset_type','name','address','country','reported_operator','reported_parent',
              'latitude','longitude','source_url','source_record_ref')})
    # Parent relationship cannot silently change; create a new asset for a
    # different campus/building or use a separately approved linkage workflow.
    if 'parent_asset_id' in details:
        raise ValueError('Parent asset is immutable; new linkage requires separate review')
    with conn:
        conn.execute("""UPDATE facility_assets SET asset_type=?,name=?,address=?,country=?,
            reported_operator=?,reported_parent=?,latitude=?,longitude=?,
            source_url=?,source_record_ref=?,status='candidate',
            reviewed_by=NULL,reviewed_at=NULL,revision=revision+1,
            changed_by=?,changed_at=? WHERE id=?""",
            (fields['asset_type'],fields['name'],fields['address'],fields['country'],
             fields['reported_operator'],fields['reported_parent'],fields['latitude'],
             fields['longitude'],fields['source_url'],fields['source_record_ref'],
             actor,_time(),asset_id))
        audit(conn,'physical_asset_candidate_revised',row['facility_id'],actor,
              {'asset_id':asset_id,'old_revision':row['revision'],'review_invalidated':True})
    return {'asset_id':asset_id,'revision':row['revision']+1,'status':'candidate',
            'coordinate_verified':False}

def facility_assets(conn,facility_id):
    _required(conn,'SELECT id FROM facilities WHERE id=?',(facility_id,),'Unknown research facility')
    rows=[dict(x) for x in conn.execute("""SELECT * FROM facility_assets
           WHERE facility_id=? ORDER BY parent_asset_id IS NOT NULL,asset_type,name,id""",
           (facility_id,))]
    return {'facility_id':facility_id,'assets':rows,'total_assets':len(rows),
       'identity_corroborated_assets':sum(x['status']=='identity_corroborated' for x in rows),
       'reviewed_property_coordinates':0,
       'warning':'Asset identity corroboration is not a verified property geocode, ownership proof, or insurance coverage'}

def propose_asset_review(conn,asset_id,details,actor):
    actor=_person(actor)
    if not isinstance(details,dict):raise ValueError('Expected review proposal')
    status=details.get('proposed_status')
    if status not in REVIEW_STATUS:raise ValueError('Invalid identity review outcome')
    url=_https(details.get('review_evidence_url'),True)
    rationale=_text(details.get('rationale'),2000,True)
    if len(rationale)<20:raise ValueError('A detailed source/physical-identity rationale is required')
    row=_required(conn,'SELECT * FROM facility_assets WHERE id=?',(asset_id,),'Unknown physical asset')
    if row['status']=='rejected' and status!='rejected':
        raise ValueError('Revise a rejected candidate before reconsidering identity')
    proposal=uuid.uuid4().hex
    with conn:
        conn.execute("""INSERT INTO facility_asset_reviews
          (id,asset_id,proposed_status,revision,source_snapshot_sha256,
           review_evidence_url,rationale,requested_by,requested_at)
          VALUES(?,?,?,?,?,?,?,?,?)""",
          (proposal,asset_id,status,row['revision'],_fingerprint(row),
           url,rationale,actor,_time()))
        audit(conn,'physical_asset_review_requested',row['facility_id'],actor,
              {'proposal_id':proposal,'asset_id':asset_id,'status':status,'revision':row['revision']})
    return {'review_id':proposal,'status':'pending','coordinate_verified':False}

def asset_review_queue(conn,status='pending',facility_id='',limit=100):
    if status not in ('pending','approved','rejected','invalidated','all'):
        raise ValueError('Invalid approval status')
    where=[];args=[]
    if status!='all':where.append('r.status=?');args.append(status)
    if facility_id:where.append('a.facility_id=?');args.append(facility_id)
    sql="""SELECT r.*,a.facility_id,a.asset_type,a.name AS asset_name,
         a.status AS asset_status,a.revision AS asset_revision FROM facility_asset_reviews r
         JOIN facility_assets a ON a.id=r.asset_id"""
    if where:sql+=' WHERE '+' AND '.join(where)
    sql+=' ORDER BY r.requested_at DESC,r.id DESC LIMIT ?'
    args.append(max(1,min(int(limit),200)))
    return {'items':[dict(x) for x in conn.execute(sql,args)],
       'scope':'Identity evidence review only; never validates property coordinate, insurer or ultimate parent'}

def decide_asset_review(conn,review_id,decision,actor,note):
    actor=_person(actor)
    if decision not in ('approve','reject'):raise ValueError('Invalid review decision')
    note=_text(note,2000,True)
    if len(note)<12:raise ValueError('Independent decision rationale required')
    conn.execute('BEGIN IMMEDIATE')
    try:
        row=_required(conn,'''SELECT r.*,a.facility_id FROM facility_asset_reviews r
          JOIN facility_assets a ON a.id=r.asset_id WHERE r.id=?''',(review_id,),
          'Unknown asset review request')
        if row['status']!='pending':raise ValueError('Review already decided')
        if row['requested_by']==actor:raise ValueError('A reviewer cannot approve their own proposal')
        asset=_required(conn,'SELECT * FROM facility_assets WHERE id=?',
                        (row['asset_id'],),'Original asset has been removed')
        outcome='approved' if decision=='approve' else 'rejected'
        if decision=='approve':
            if asset['revision']!=row['revision'] or _fingerprint(asset)!=row['source_snapshot_sha256']:
                outcome='invalidated'
            else:
                conn.execute("""UPDATE facility_assets SET status=?,reviewed_by=?,reviewed_at=?
                   WHERE id=?""",(row['proposed_status'],actor,_time(),asset['id']))
        conn.execute("""UPDATE facility_asset_reviews
           SET status=?,decided_by=?,decided_at=?,decision_note=? WHERE id=? AND status='pending'""",
           (outcome,actor,_time(),note,review_id))
        audit(conn,'physical_asset_review_'+outcome,row['facility_id'],actor,
              {'review_id':review_id,'asset_id':asset['id'],'candidate_revision':row['revision']})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {'review_id':review_id,'status':outcome,
            'asset_identity_promoted':outcome=='approved' and row['proposed_status']=='identity_corroborated',
            'coordinate_verified':False,'insured_coverage_verified':False}
