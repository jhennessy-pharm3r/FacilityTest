"""Facility-level identity, event, geohazard, exposure and evidence governance.

A recorded FEI or analyst point is NOT a confirmed cross-system identity or
engineering-quality site geocode. Review decisions are explicit and audited.
"""
from __future__ import annotations
import json
import uuid
import sqlite3
import math
from datetime import datetime, timezone
from .ingest import stable_id, utcnow
from .match import haversine_km

EXT_SCHEMA = '''
CREATE TABLE IF NOT EXISTS identity_links (
 id TEXT PRIMARY KEY, facility_id TEXT NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
 namespace TEXT NOT NULL, identifier TEXT NOT NULL, status TEXT NOT NULL
 CHECK(status IN ('observed','candidate','verified','rejected')),
 provenance_url TEXT, provenance_note TEXT, reviewer TEXT, reviewed_at TEXT,
 created_at TEXT NOT NULL, UNIQUE(facility_id,namespace,identifier)
);
CREATE INDEX IF NOT EXISTS idx_identity_links ON identity_links(namespace,identifier,status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_identity_verified_global ON identity_links(namespace,identifier)
 WHERE status='verified' AND namespace IN ('EPA_FRS','FDA_FEI');
CREATE TABLE IF NOT EXISTS match_candidates (
 id TEXT PRIMARY KEY, facility_id TEXT NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
 namespace TEXT NOT NULL, identifier TEXT NOT NULL, candidate_name TEXT, candidate_address TEXT,
 candidate_lat REAL, candidate_lon REAL, distance_km REAL, name_similarity REAL,
 source_url TEXT, retrieved_at TEXT NOT NULL,
 decision TEXT NOT NULL DEFAULT 'pending' CHECK(decision IN ('pending','accepted','rejected')),
 reviewer TEXT, reviewed_at TEXT, review_note TEXT,
 UNIQUE(facility_id,namespace,identifier)
);
CREATE TABLE IF NOT EXISTS location_reviews (
 facility_id TEXT PRIMARY KEY REFERENCES facilities(id) ON DELETE CASCADE,
 precision TEXT NOT NULL CHECK(precision IN ('city','approximate','site_verified','property_polygon')),
 method TEXT, evidence_url TEXT, reviewer TEXT, verified_at TEXT, note TEXT,
 reviewed_latitude REAL, reviewed_longitude REAL
);
CREATE TABLE IF NOT EXISTS historical_events (
 id TEXT PRIMARY KEY, facility_id TEXT NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
 title TEXT NOT NULL, peril TEXT, incident_date TEXT NOT NULL, operational_outcome TEXT,
 production_effect TEXT, financial_effect TEXT, resilience_effect TEXT,
 pre_event_evidence_status TEXT, attribution_note TEXT, source_url TEXT,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS event_milestones (
 id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES historical_events(id) ON DELETE CASCADE,
 event_date TEXT NOT NULL, publication_date TEXT, stage TEXT NOT NULL,
 fact TEXT NOT NULL, source_url TEXT NOT NULL,
 timing TEXT NOT NULL CHECK(timing IN ('pre_event','during_event','post_event','unknown')),
 interpretation_note TEXT
);
CREATE TABLE IF NOT EXISTS hazard_assessments (
 id TEXT PRIMARY KEY, facility_id TEXT NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
 peril TEXT NOT NULL, status TEXT NOT NULL,
 source TEXT NOT NULL, source_url TEXT,
 hazard_zone TEXT, description TEXT, precision TEXT, effective_date TEXT,
 retrieved_at TEXT NOT NULL, limitations TEXT,
 reviewed_latitude REAL, reviewed_longitude REAL, location_reviewed_at TEXT,
 UNIQUE(facility_id,peril,source)
);
CREATE TABLE IF NOT EXISTS exposure_profiles (
 facility_id TEXT PRIMARY KEY REFERENCES facilities(id) ON DELETE CASCADE,
 property_damage TEXT NOT NULL, business_interruption TEXT NOT NULL,
 environmental_liability TEXT NOT NULL, supply_chain TEXT NOT NULL,
 resilience TEXT NOT NULL, source_scope TEXT NOT NULL,
 replacement_value_usd REAL, bi_value_usd REAL, source_url TEXT,
 updated_at TEXT NOT NULL, updated_by TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source_health (
 source TEXT PRIMARY KEY, state TEXT NOT NULL,
 checked_at TEXT NOT NULL, url TEXT, item_count INTEGER, details TEXT
);
CREATE TABLE IF NOT EXISTS audit_events (
 id TEXT PRIMARY KEY, action TEXT NOT NULL, subject_id TEXT,
 actor TEXT NOT NULL, recorded_at TEXT NOT NULL,
 details_json TEXT NOT NULL
);
'''


def initialize_intelligence(conn):
    conn.executescript(EXT_SCHEMA)
    # Additive migration: existing historical coordinate reviews cannot prove
    # which location was reviewed. They remain gated until re-reviewed.
    columns={row['name'] for row in conn.execute('PRAGMA table_info(location_reviews)')}
    for column in ('reviewed_latitude','reviewed_longitude'):
        if column not in columns:
            conn.execute('ALTER TABLE location_reviews ADD COLUMN '+column+' REAL')
    # Historical hazard rows lack proof of the approved location at screening.
    # Do not fabricate reviewed coordinates during an existing DB migration.
    known={r['name'] for r in conn.execute('PRAGMA table_info(hazard_assessments)')}
    for field,kind in (('reviewed_latitude','REAL'),('reviewed_longitude','REAL'),
                       ('location_reviewed_at','TEXT')):
        if field not in known:
            conn.execute('ALTER TABLE hazard_assessments ADD COLUMN '+field+' '+kind)
    # Analyst-provided FEI is "observed", not independently verified.
    for r in conn.execute("SELECT id,fei FROM facilities WHERE fei IS NOT NULL AND trim(fei)<>''"):
        conn.execute('''INSERT OR IGNORE INTO identity_links(id,facility_id,namespace,identifier,status,provenance_note,created_at)
          VALUES(?,?,?,?,?,?,?)''',
          (stable_id('FEI_observed',r['id'],r['fei']),r['id'],'FDA_FEI',r['fei'],'observed',
           'Transcribed from analyst research; not validated against current FDA registry',utcnow()))
    conn.commit()


def audit(conn,action,subject,actor,details):
    conn.execute('INSERT INTO audit_events VALUES (?,?,?,?,?,?)',
                 (uuid.uuid4().hex,action,subject,actor,utcnow(),json.dumps(details,sort_keys=True)))


def is_reviewed_site_coordinate(site, review):
    """Only the *currently stored* point, not an old reviewed site name, is approved."""
    if not site or not review or review['precision'] not in ('site_verified','property_polygon'):
        return False
    try:
        lat=float(site['latitude']);lon=float(site['longitude'])
        checked_lat=float(review['reviewed_latitude'])
        checked_lon=float(review['reviewed_longitude'])
    except (TypeError,ValueError,KeyError,IndexError):
        return False
    return (all(math.isfinite(v) for v in (lat,lon,checked_lat,checked_lon))
            and -90<=lat<=90 and -180<=lon<=180
            and lat==checked_lat and lon==checked_lon)


def review_location(conn,facility_id,precision,evidence_url,reviewer,note='',method='document-and-map-review'):
    if precision not in ('city','approximate','site_verified','property_polygon'):
        raise ValueError('Unsupported location precision')
    approved=precision in ('site_verified','property_polygon')
    if approved and not(isinstance(evidence_url,str) and evidence_url.startswith('https://')
                        and isinstance(reviewer,str) and reviewer.strip()):
        raise ValueError('Site verification requires an HTTPS evidence URL and named reviewer')
    site=conn.execute('SELECT latitude,longitude FROM facilities WHERE id=?',(facility_id,)).fetchone()
    if site is None:raise ValueError('Unknown facility')
    checked_lat,checked_lon=None,None
    if approved:
        try:
            checked_lat=float(site['latitude']);checked_lon=float(site['longitude'])
        except (TypeError,ValueError):
            raise ValueError('Facility is missing valid site coordinates') from None
        if not (math.isfinite(checked_lat) and math.isfinite(checked_lon)
                and -90<=checked_lat<=90 and -180<=checked_lon<=180):
            raise ValueError('Site coordinates are outside valid geographic bounds')
    when=utcnow()
    conn.execute('''INSERT INTO location_reviews
      (facility_id,precision,method,evidence_url,reviewer,verified_at,note,
       reviewed_latitude,reviewed_longitude) VALUES(?,?,?,?,?,?,?,?,?)
      ON CONFLICT(facility_id) DO UPDATE SET precision=excluded.precision,
        method=excluded.method,evidence_url=excluded.evidence_url,
        reviewer=excluded.reviewer,verified_at=excluded.verified_at,
        note=excluded.note,reviewed_latitude=excluded.reviewed_latitude,
        reviewed_longitude=excluded.reviewed_longitude''',
        (facility_id,precision,method,evidence_url,reviewer,when,note,
         checked_lat,checked_lon))
    audit(conn,'location_review',facility_id,reviewer or 'anonymous',
          {'precision':precision,'source':evidence_url,
           'reviewed_latitude':checked_lat,'reviewed_longitude':checked_lon})
    conn.commit()
    return {'facility_id':facility_id,'precision':precision,'reviewed_at':when,
            'point_locked_to_review':approved}



def verify_fei(conn,facility_id,reviewer,evidence_url,note):
    """Review analyst-recorded FDA FEI against a corroborating official source."""
    if not reviewer.strip() or not evidence_url.startswith('https://') or not note.strip():
        raise ValueError('Named reviewer, HTTPS source and rationale required for FEI verification')
    f=conn.execute('SELECT id,fei FROM facilities WHERE id=?',(facility_id,)).fetchone()
    if not f or not f['fei']:raise ValueError('Cannot verify missing FEI or unknown facility')
    when=utcnow()
    rec=conn.execute("SELECT id FROM identity_links WHERE facility_id=? AND namespace='FDA_FEI' AND identifier=?",(facility_id,f['fei'])).fetchone()
    if rec:
        conn.execute("UPDATE identity_links SET status='verified',provenance_url=?,provenance_note=?,reviewer=?,reviewed_at=? WHERE id=?",
                     (evidence_url,note,reviewer,when,rec['id']))
    else:
        conn.execute('''INSERT INTO identity_links(id,facility_id,namespace,identifier,status,provenance_url,provenance_note,reviewer,reviewed_at,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)''',
        (stable_id('verified_fda_fei',facility_id,f['fei']),facility_id,'FDA_FEI',f['fei'],'verified',evidence_url,note,reviewer,when,when))
    audit(conn,'fei_verified',facility_id,reviewer,{'fei':f['fei'],'evidence_url':evidence_url,'note':note})
    conn.commit()
    return {'facility_id':facility_id,'fei':f['fei'],'status':'verified','reviewed_at':when}


def name_similarity(a,b):
    import re
    from difflib import SequenceMatcher
    def tokens(v):
        s=re.findall(r'[a-z0-9]+',(v or '').lower())
        return ' '.join(x for x in s if x not in {'inc','llc','ltd','co','corporation','manufacturing','facility','the'})
    return round(SequenceMatcher(None,tokens(a),tokens(b)).ratio(),3)


def register_frs_candidates(conn,facility_id,records,source_url,when=None):
    """Candidates are NEVER promoted to a verified crosswalk automatically."""
    f=conn.execute('SELECT * FROM facilities WHERE id=?',(facility_id,)).fetchone()
    if f is None:raise ValueError('Unknown facility')
    count=0
    for r in records:
        rid=str(r.get('registry_id') or '').strip()
        if not rid.isdigit() or not 10<=len(rid)<=13:continue
        lat,lon=r.get('latitude'),r.get('longitude')
        dist=None
        if all(v is not None for v in (lat,lon,f['latitude'],f['longitude'])):
            dist=round(haversine_km(f['latitude'],f['longitude'],float(lat),float(lon)),2)
        cid=stable_id('frs_candidate',facility_id,rid)
        conn.execute('''INSERT INTO match_candidates
        (id,facility_id,namespace,identifier,candidate_name,candidate_address,candidate_lat,candidate_lon,
         distance_km,name_similarity,source_url,retrieved_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(facility_id,namespace,identifier) DO UPDATE SET
        candidate_name=excluded.candidate_name,candidate_address=excluded.candidate_address,
        candidate_lat=excluded.candidate_lat,candidate_lon=excluded.candidate_lon,
        distance_km=excluded.distance_km,name_similarity=excluded.name_similarity,
        source_url=excluded.source_url,retrieved_at=excluded.retrieved_at''',
        (cid,facility_id,'EPA_FRS',rid,r.get('name'),r.get('address'),lat,lon,dist,
         name_similarity(f['name'],r.get('name')),source_url,when or utcnow()))
        count+=1
    conn.commit()
    return count


def decide_candidate(conn,candidate_id,decision,reviewer,evidence_url,note=''):
    if decision not in ('accepted','rejected'):raise ValueError('Decision must be accepted/rejected')
    if not reviewer.strip() or not evidence_url.startswith('https://') or not note.strip():
        raise ValueError('Reviewer, HTTPS corroborating source, and review rationale required')
    row=conn.execute('SELECT * FROM match_candidates WHERE id=?',(candidate_id,)).fetchone()
    if row is None:raise ValueError('Candidate not found')
    if decision=='accepted' and row['namespace']=='EPA_FRS' and row['distance_km'] is not None and row['distance_km']>50 and 'distance' not in note.lower():
        raise ValueError('Distant candidate requires explicit distance explanation')
    when=utcnow()
    # Both decisions preserved; verified IDs are uniqueness-checked by database.
    conn.execute('UPDATE match_candidates SET decision=?,reviewer=?,reviewed_at=?,review_note=? WHERE id=?',
                 (decision,reviewer,when,note,candidate_id))
    if decision=='accepted':
        key=stable_id('accepted_identifier',row['facility_id'],row['namespace'],row['identifier'])
        conn.execute('''INSERT INTO identity_links(id,facility_id,namespace,identifier,status,provenance_url,provenance_note,reviewer,reviewed_at,created_at)
          VALUES(?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(facility_id,namespace,identifier) DO UPDATE SET
            status='verified',provenance_url=excluded.provenance_url,
            provenance_note=excluded.provenance_note,reviewer=excluded.reviewer,reviewed_at=excluded.reviewed_at''',
          (key,row['facility_id'],row['namespace'],row['identifier'],'verified',evidence_url,note,reviewer,when,when))
    audit(conn,'candidate_'+decision,row['facility_id'],reviewer,
          {'candidate_id':candidate_id,'identifier':row['identifier'],'evidence_url':evidence_url,'note':note})
    conn.commit()
    return {'candidate':candidate_id,'decision':decision,'reviewed_at':when}


def store_hazard(conn,facility_id,peril,status,source,description,source_url='',zone='',precision='',effective_date='',limitations=''):
    """Pin a hazard screening to a reviewed physical point and review revision.

    This is modeled exposure, never an insured property loss. A move or later
    coordinate re-review requires a fresh source screening.
    """
    site=conn.execute('SELECT id,latitude,longitude FROM facilities WHERE id=?',(facility_id,)).fetchone()
    if not site:raise ValueError('Unknown facility')
    review=conn.execute('SELECT * FROM location_reviews WHERE facility_id=?',(facility_id,)).fetchone()
    if not is_reviewed_site_coordinate(site,review):
        raise ValueError('Hazard screening requires reviewed coordinates for the current site')
    hid=stable_id('hazard',facility_id,peril,source)
    conn.execute('''INSERT INTO hazard_assessments
       (id,facility_id,peril,status,source,source_url,hazard_zone,description,
        precision,effective_date,retrieved_at,limitations,
        reviewed_latitude,reviewed_longitude,location_reviewed_at)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
       ON CONFLICT(facility_id,peril,source) DO UPDATE SET
          status=excluded.status,source_url=excluded.source_url,
          hazard_zone=excluded.hazard_zone,description=excluded.description,
          precision=excluded.precision,effective_date=excluded.effective_date,
          retrieved_at=excluded.retrieved_at,limitations=excluded.limitations,
          reviewed_latitude=excluded.reviewed_latitude,
          reviewed_longitude=excluded.reviewed_longitude,
          location_reviewed_at=excluded.location_reviewed_at''',
        (hid,facility_id,peril,status,source,source_url,zone,description,
         precision,effective_date,utcnow(),limitations,
         site['latitude'],site['longitude'],review['verified_at']))
    conn.commit()
    return {'facility_id':facility_id,'peril':peril,'status':status,'zone':zone,
            'reviewed_coordinate_snapshot':True}



def assess_fema_payload(payload):
    """NFHL: no feature is unmapped/unknown, NOT 'low flood risk'."""
    if payload.get('error'):raise ValueError('FEMA ArcGIS error: '+str(payload['error']))
    features=payload.get('features')
    if not isinstance(features,list):raise ValueError('Invalid FEMA response: no features array')
    if not features:return ('not_mapped','No NFHL flood-zone polygon returned for this point','')
    attrs=features[0].get('attributes') or {}
    z=str(attrs.get('FLD_ZONE') or '').strip()
    sfha=str(attrs.get('SFHA_TF') or '').strip().upper()
    if not z or sfha not in {'T','F'}:
        raise ValueError('FEMA returned missing/unrecognized flood-zone attributes')
    status='mapped_sfha' if sfha=='T' else 'mapped_outside_sfha'
    return (status, f'NFHL current map: Flood Zone {z}; SFHA flag {sfha}',z)


def make_underwriting_profile(conn,facility_id,sections,actor='analyst',source_scope='Analyst research',source_url=''):
    keys=('property_damage','business_interruption','environmental_liability','supply_chain','resilience')
    if set(sections)!=set(keys):raise ValueError('Profile must supply each exposure category')
    for k,v in sections.items():
        if not isinstance(v,str) or len(v)>5000:raise ValueError('Invalid text in '+k)
    if source_url and not source_url.startswith('https://'):raise ValueError('Source must be HTTPS')
    conn.execute('''INSERT INTO exposure_profiles
     (facility_id,property_damage,business_interruption,environmental_liability,supply_chain,
      resilience,source_scope,replacement_value_usd,bi_value_usd,source_url,updated_at,updated_by)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(facility_id) DO UPDATE SET
       property_damage=excluded.property_damage,business_interruption=excluded.business_interruption,
       environmental_liability=excluded.environmental_liability,supply_chain=excluded.supply_chain,
       resilience=excluded.resilience,source_scope=excluded.source_scope,source_url=excluded.source_url,
       updated_at=excluded.updated_at,updated_by=excluded.updated_by''',
     (facility_id,*(sections[k] for k in keys),source_scope,None,None,source_url,utcnow(),actor))
    audit(conn,'underwriting_profile_update',facility_id,actor,{'categories':list(keys),'scope':source_scope})
    conn.commit()


def get_intelligence(conn,facility_id):
    facility=conn.execute('SELECT latitude,longitude FROM facilities WHERE id=?',(facility_id,)).fetchone()
    if facility is None:return None
    from .db import items,one
    events=items(conn,'SELECT * FROM historical_events WHERE facility_id=? ORDER BY incident_date',(facility_id,))
    for ev in events:
        ev['milestones']=items(conn,'SELECT * FROM event_milestones WHERE event_id=? ORDER BY event_date,publication_date',(ev['id'],))
    loc=one(conn,'SELECT * FROM location_reviews WHERE facility_id=?',(facility_id,))
    if loc:
        valid=is_reviewed_site_coordinate(facility,loc)
        loc['review_valid_for_current_coordinates']=valid
        if loc['precision'] in ('site_verified','property_polygon') and not valid:
            loc['original_review_precision']=loc['precision']
            loc['precision']='review_stale'
    hazard_checks=items(conn,'SELECT * FROM hazard_assessments WHERE facility_id=? ORDER BY peril',(facility_id,))
    current_review=loc and is_reviewed_site_coordinate(facility,loc)
    for hazard in hazard_checks:
        valid=bool(current_review and
                   hazard['reviewed_latitude'] is not None and
                   hazard['reviewed_longitude'] is not None and
                   hazard['reviewed_latitude']==facility['latitude'] and
                   hazard['reviewed_longitude']==facility['longitude'] and
                   hazard['location_reviewed_at']==loc['verified_at'])
        hazard['valid_for_current_site_point']=valid
        if not valid:
            hazard['original_status']=hazard['status']
            hazard['status']='stale_location_review'
    return dict(facility_id=facility_id,identifiers=items(conn,'SELECT * FROM identity_links WHERE facility_id=? ORDER BY namespace,status',(facility_id,)),
        candidates=items(conn,'SELECT * FROM match_candidates WHERE facility_id=? ORDER BY decision,name_similarity DESC',(facility_id,)),
        location=loc,
        hazard_checks=hazard_checks,
        incidents=events,profile=one(conn,'SELECT * FROM exposure_profiles WHERE facility_id=?',(facility_id,)))


def intelligence_quality(conn):
    return {
      'verified_frs_links':conn.execute("SELECT COUNT(*) FROM identity_links WHERE namespace='EPA_FRS' AND status='verified'").fetchone()[0],
      'frs_candidates_pending':conn.execute("SELECT COUNT(*) FROM match_candidates WHERE decision='pending'").fetchone()[0],
      'verified_site_locations':conn.execute("""SELECT COUNT(*) FROM location_reviews l
        JOIN facilities f ON f.id=l.facility_id
        WHERE l.precision IN ('site_verified','property_polygon')
          AND l.reviewed_latitude=f.latitude
          AND l.reviewed_longitude=f.longitude
          AND f.latitude BETWEEN -90 AND 90
          AND f.longitude BETWEEN -180 AND 180""").fetchone()[0],
      'historical_incidents':conn.execute('SELECT COUNT(*) FROM historical_events').fetchone()[0],
      'hazard_screenings':conn.execute('SELECT COUNT(*) FROM hazard_assessments').fetchone()[0],
      'current_hazard_screenings':conn.execute("""SELECT COUNT(*) FROM hazard_assessments h
          JOIN facilities f ON f.id=h.facility_id
          JOIN location_reviews l ON l.facility_id=f.id
          WHERE l.precision IN ('site_verified','property_polygon')
            AND h.reviewed_latitude=f.latitude
            AND h.reviewed_longitude=f.longitude
            AND l.reviewed_latitude=f.latitude
            AND l.reviewed_longitude=f.longitude
            AND h.location_reviewed_at=l.verified_at""").fetchone()[0],
      'profiles':conn.execute('SELECT COUNT(*) FROM exposure_profiles').fetchone()[0],
      'live_source_checks':conn.execute('SELECT COUNT(*) FROM source_health').fetchone()[0]
    }
