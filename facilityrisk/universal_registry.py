"""Industry-agnostic source identity registry and auditable physical-site candidates.

Every record is eligible for search before a risk investigation exists. Ingestion
NEVER merges identities from different source authorities. The initial site is a
source-reported *candidate*, not a verified building, insured property, or risk
score. The registry is private/backend indexed; GitHub Pages remains a small
public-source catalog.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from urllib.parse import urlsplit

MAX_BATCH = 2000
MAX_RECORDS_PER_IMPORT = 10_000_000

SCHEMA = """
CREATE TABLE IF NOT EXISTS universal_sites (
 id TEXT PRIMARY KEY,
 name TEXT NOT NULL,
 company TEXT NOT NULL DEFAULT '',
 address TEXT NOT NULL DEFAULT '',
 city TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL DEFAULT '',
 country TEXT NOT NULL DEFAULT '',
 industry TEXT NOT NULL DEFAULT '',
 activities TEXT NOT NULL DEFAULT '',
 latitude REAL, longitude REAL,
 coordinate_quality TEXT NOT NULL DEFAULT 'unassessed',
 site_status TEXT NOT NULL DEFAULT 'source_observation',
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 CHECK(latitude IS NULL OR latitude BETWEEN -90 AND 90),
 CHECK(longitude IS NULL OR longitude BETWEEN -180 AND 180)
);
CREATE INDEX IF NOT EXISTS idx_universal_geo ON universal_sites(country,state,city);
CREATE INDEX IF NOT EXISTS idx_universal_industry ON universal_sites(industry);
CREATE INDEX IF NOT EXISTS idx_universal_operator ON universal_sites(company);
CREATE INDEX IF NOT EXISTS idx_universal_name_sort ON universal_sites(name COLLATE NOCASE,id);
CREATE INDEX IF NOT EXISTS idx_universal_country_name_sort ON universal_sites(country,name COLLATE NOCASE,id);
CREATE TABLE IF NOT EXISTS universal_source_records (
 source_key TEXT NOT NULL,
 source_identifier TEXT NOT NULL,
 site_id TEXT NOT NULL REFERENCES universal_sites(id),
 source_url TEXT NOT NULL,
 reported_name TEXT NOT NULL,
 reported_company TEXT NOT NULL DEFAULT '',
 reported_address TEXT NOT NULL DEFAULT '',
 reported_country TEXT NOT NULL DEFAULT '',
 industry TEXT NOT NULL DEFAULT '',
 category TEXT NOT NULL DEFAULT '',
 reported_latitude REAL, reported_longitude REAL,
 source_confidence REAL,
 vintage TEXT NOT NULL DEFAULT '',
 record_digest TEXT NOT NULL,
 last_imported TEXT NOT NULL,
 PRIMARY KEY(source_key,source_identifier)
);
CREATE INDEX IF NOT EXISTS idx_universal_source_site ON universal_source_records(site_id);
CREATE INDEX IF NOT EXISTS idx_universal_source_key ON universal_source_records(source_key);
CREATE INDEX IF NOT EXISTS idx_universal_source_identifier_lookup ON universal_source_records(source_identifier COLLATE NOCASE);
CREATE TABLE IF NOT EXISTS universal_import_runs (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 source_key TEXT NOT NULL, source_url TEXT NOT NULL,
 vintage TEXT NOT NULL, imported_at TEXT NOT NULL,
 read_rows INTEGER NOT NULL, valid_records INTEGER NOT NULL,
 inserted_identities INTEGER NOT NULL, rejected_rows INTEGER NOT NULL,
 notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS universal_identity_decisions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, source_key TEXT NOT NULL,
 source_identifier TEXT NOT NULL, from_site_id TEXT NOT NULL,
 to_site_id TEXT NOT NULL, evidence_url TEXT NOT NULL, rationale TEXT NOT NULL,
 reviewer TEXT NOT NULL, approver TEXT NOT NULL, decided_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS universal_research_links (
 site_id TEXT PRIMARY KEY REFERENCES universal_sites(id),
 research_facility_id TEXT NOT NULL UNIQUE
);
CREATE VIRTUAL TABLE IF NOT EXISTS universal_site_fts USING fts5(
 site_id UNINDEXED,name,company,address,city,state,country,industry,activities,
 content='universal_sites',content_rowid='rowid',tokenize='unicode61'
);
CREATE TRIGGER IF NOT EXISTS universal_sites_ai AFTER INSERT ON universal_sites BEGIN
 INSERT INTO universal_site_fts(rowid,site_id,name,company,address,city,state,country,industry,activities)
 VALUES(new.rowid,new.id,new.name,new.company,new.address,new.city,new.state,new.country,new.industry,new.activities);
END;
CREATE TRIGGER IF NOT EXISTS universal_sites_ad AFTER DELETE ON universal_sites BEGIN
 INSERT INTO universal_site_fts(universal_site_fts,rowid,site_id,name,company,address,city,state,country,industry,activities)
 VALUES('delete',old.rowid,old.id,old.name,old.company,old.address,old.city,old.state,old.country,old.industry,old.activities);
END;
CREATE TRIGGER IF NOT EXISTS universal_sites_au AFTER UPDATE ON universal_sites BEGIN
 INSERT INTO universal_site_fts(universal_site_fts,rowid,site_id,name,company,address,city,state,country,industry,activities)
 VALUES('delete',old.rowid,old.id,old.name,old.company,old.address,old.city,old.state,old.country,old.industry,old.activities);
 INSERT INTO universal_site_fts(rowid,site_id,name,company,address,city,state,country,industry,activities)
 VALUES(new.rowid,new.id,new.name,new.company,new.address,new.city,new.state,new.country,new.industry,new.activities);
END;
"""

def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def _text(value, limit=250):
    if value is None or isinstance(value, (dict, list)):
        return ''
    return re.sub(r'\s+', ' ', str(value)).strip()[:limit]

def _coord(value, lower, upper):
    if value is None or str(value).strip() == '':
        return None
    try:
        v = float(value)
        return v if lower <= v <= upper and v == v else None
    except (ValueError, TypeError, OverflowError):
        return None

def initialize(conn):
    conn.execute('PRAGMA foreign_keys=ON')
    conn.executescript(SCHEMA)

def normalize(source_key, record):
    if not isinstance(record, dict):
        return None
    ident = _text(record.get('source_identifier') or record.get('id'), 160)
    name = _text(record.get('name'), 240)
    if not ident or not name:
        return None
    lat = _coord(record.get('latitude'), -90, 90)
    lon = _coord(record.get('longitude'), -180, 180)
    if (lat is None) != (lon is None):
        lat = lon = None
    conf = _coord(record.get('source_confidence'), 0, 1)
    obj = dict(source_key=source_key, source_identifier=ident, name=name,
        company=_text(record.get('company'),240),
        address=_text(record.get('address'),320),
        city=_text(record.get('city'),120),
        state=_text(record.get('state'),120),
        country=_text(record.get('country'),8).upper(),
        industry=_text(record.get('industry') or record.get('sector'),120),
        category=_text(record.get('category'),180),
        activities=_text(record.get('activities'),300),
        latitude=lat, longitude=lon, source_confidence=conf)
    return obj

def _key(source_key, ident):
    return 'usite-' + sha256((source_key + '\0' + ident).encode('utf-8')).hexdigest()[:24]

def _validate_url(url):
    u = urlsplit(str(url))
    if u.scheme != 'https' or not u.hostname or u.username or u.password:
        raise ValueError('Official source evidence must have an HTTPS URL')
    return str(url)

def import_records(conn, source_key, records, source_url, *, vintage='', notes=''):
    """Stream records without reading a source file into memory or deleting missing sites.

    An existing manually reviewed link is retained on refresh. A record changing
    address never moves its previously approved property point. Previously
    imported identities remain present with their last-seen vintage until
    explicitly reviewed; absence from a later export is not proof of closure.
    """
    source_key = _text(source_key,80)
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{1,79}', source_key):
        raise ValueError('Invalid source key')
    source_url = _validate_url(source_url)
    initialize(conn)
    read = valid = rejected = inserted = 0
    now = _now()
    with conn:
        for raw in records:
            read += 1
            if read > MAX_RECORDS_PER_IMPORT:
                raise ValueError('Split source into smaller partitions (10 million limit)')
            r = normalize(source_key, raw)
            if r is None:
                rejected += 1
                continue
            valid += 1
            ident = r['source_identifier']
            existing = conn.execute(
                'SELECT site_id FROM universal_source_records WHERE source_key=? AND source_identifier=?',
                (source_key,ident)).fetchone()
            site_id = existing['site_id'] if existing else _key(source_key,ident)
            digest = sha256(json.dumps(r,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()
            if not existing:
                inserted += 1
                conn.execute("""INSERT OR IGNORE INTO universal_sites
                  (id,name,company,address,city,state,country,industry,activities,
                   latitude,longitude,coordinate_quality,site_status,created_at,updated_at)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  (site_id,r['name'],r['company'],r['address'],r['city'],r['state'],r['country'],
                   r['industry'],r['activities'],r['latitude'],r['longitude'],
                   'source_point_unverified' if r['latitude'] is not None else 'unassessed',
                   'source_observation',now,now))
            conn.execute("""INSERT INTO universal_source_records
                (source_key,source_identifier,site_id,source_url,reported_name,reported_company,
                 reported_address,reported_country,industry,category,reported_latitude,
                 reported_longitude,source_confidence,vintage,record_digest,last_imported)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(source_key,source_identifier) DO UPDATE SET
                  source_url=excluded.source_url,reported_name=excluded.reported_name,
                  reported_company=excluded.reported_company,reported_address=excluded.reported_address,
                  reported_country=excluded.reported_country,industry=excluded.industry,
                  category=excluded.category,reported_latitude=excluded.reported_latitude,
                  reported_longitude=excluded.reported_longitude,
                  source_confidence=excluded.source_confidence,vintage=excluded.vintage,
                  record_digest=excluded.record_digest,last_imported=excluded.last_imported""",
                (source_key,ident,site_id,source_url,r['name'],r['company'],
                 r['address'],r['country'],r['industry'],r['category'],
                 r['latitude'],r['longitude'],r['source_confidence'],_text(vintage,80),digest,now))
            if existing and site_id == _key(source_key, ident):
                conn.execute("""UPDATE universal_sites SET name=?,company=?,address=?,city=?,state=?,
                    country=?,industry=?,activities=?,latitude=?,longitude=?,coordinate_quality=?,updated_at=?
                    WHERE id=? AND site_status='source_observation'""",
                    (r['name'],r['company'],r['address'],r['city'],r['state'],r['country'],
                     r['industry'],r['activities'],r['latitude'],r['longitude'],
                     'source_point_unverified' if r['latitude'] is not None else 'unassessed',
                     now,site_id))
        conn.execute("""INSERT INTO universal_import_runs
            (source_key,source_url,vintage,imported_at,read_rows,valid_records,
             inserted_identities,rejected_rows,notes) VALUES (?,?,?,?,?,?,?,?,?)""",
             (source_key,source_url,_text(vintage,80),now,read,valid,inserted,rejected,_text(notes,800)))
    return {'source':source_key,'read':read,'valid':valid,'new_source_identities':inserted,
            'rejected':rejected,'vintage':_text(vintage,80)}

def import_published_catalog(conn, path):
    """Import existing FDA, Ireland and Canada public catalog without cross-source merging."""
    from pathlib import Path
    from .registry_catalog import validate_catalog
    data = validate_catalog(json.loads(Path(path).read_text(encoding='utf-8')))
    fields = data['fields']
    def rows_for(key):
        return (dict(source_identifier=r[0], **{
            'name':r[fields.index('name')], 'company':r[fields.index('company')],
            'address':r[fields.index('address')],'city':r[fields.index('city')],
            'state':r[fields.index('state')],'country':r[fields.index('country')],
            'industry':r[fields.index('sector')],'activities':r[fields.index('activities')]})
            for r in data['rows'] if _catalog_source(r[fields.index('source')]) == key)
    outputs = []
    keys = sorted(set(_catalog_source(r[fields.index('source')]) for r in data['rows']))
    for key in keys:
        if not key:
            continue
        src = data.get('sources',{}).get(key,{})
        url = src.get('url') or 'https://github.com/jhennessy-pharm3r/FacilityTest'
        outputs.append(import_records(conn,key,rows_for(key),url,
           vintage=str(src.get('export_date') or data.get('generated_at') or ''),
           notes='Public source identities, not independently verified physical properties'))
    return outputs

def _catalog_source(label):
    return {'FDA device registration / listing':'fda_device',
        'FDA drug establishment (DECRS)':'fda_drug',
        'Ireland EPA LEAP':'ireland_leap',
        'Canada NPRI':'canada_npri'}.get(label,'')

def search(conn, q='', *, country='', industry='', source='', limit=50, offset=0):
    initialize(conn)
    limit=max(1,min(int(limit),100))
    offset=max(0,int(offset))
    conditions=[];params=[]
    query_text=str(q).strip()[:120]
    tokens=re.findall(r'\w+',query_text.casefold(),re.UNICODE)[:8]
    if tokens:
        # FTS5 handles names, geography, operator, industry and activities.
        # The old '%term%' identifier fallback scanned every source identity
        # at national scale. Use an indexed case-insensitive prefix instead;
        # this also prevents user wildcard patterns from expanding a search.
        expression=' AND '.join('"' + x.replace('"','') + '"*' for x in tokens)
        if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{1,79}',query_text):
            conditions.append("""s.rowid IN (
              SELECT rowid FROM universal_site_fts WHERE universal_site_fts MATCH ?
              UNION SELECT t.rowid FROM universal_sites t
              JOIN universal_source_records ir ON ir.site_id=t.id
              WHERE ir.source_identifier LIKE ?)""")
            params += [expression,query_text+'%']
        else:
            conditions.append("""s.rowid IN (
              SELECT rowid FROM universal_site_fts WHERE universal_site_fts MATCH ?)""")
            params.append(expression)
    if country:
        conditions.append('s.country=?');params.append(_text(country,8).upper())
    if industry:
        conditions.append('s.industry=?');params.append(_text(industry,120))
    if source:
        conditions.append("""EXISTS (SELECT 1 FROM universal_source_records z
          WHERE z.site_id=s.id AND z.source_key=?)""")
        params.append(_text(source,80))
    clause=' WHERE '+' AND '.join(conditions) if conditions else ''
    total=conn.execute('SELECT COUNT(*) FROM universal_sites s'+clause,params).fetchone()[0]
    rows=conn.execute("""SELECT s.*, (SELECT COUNT(*) FROM universal_source_records x
                WHERE x.site_id=s.id) AS source_identity_count
                FROM universal_sites s"""+clause+
                ' ORDER BY s.name COLLATE NOCASE,s.id LIMIT ? OFFSET ?',
                params+[limit,offset]).fetchall()
    return {'items':[dict(row) for row in rows],'total':total,'limit':limit,'offset':offset,
        'status':'source_discovery_not_insurance_rating'}

def detail(conn, site_id):
    initialize(conn)
    row=conn.execute('SELECT * FROM universal_sites WHERE id=?',(site_id,)).fetchone()
    if not row:
        return None
    sources=conn.execute("""SELECT * FROM universal_source_records WHERE site_id=?
                    ORDER BY source_key,source_identifier""",(site_id,)).fetchall()
    research=conn.execute('SELECT research_facility_id FROM universal_research_links WHERE site_id=?',
                          (site_id,)).fetchone()
    return {'site':dict(row),'source_identities':[dict(x) for x in sources],
        'research_facility_id':research['research_facility_id'] if research else None,
        'risk_status':'unassessed','insured_coverage_status':'unknown'}

def statistics(conn):
    initialize(conn)
    total=conn.execute('SELECT COUNT(*) FROM universal_sites').fetchone()[0]
    ids=conn.execute('SELECT COUNT(*) FROM universal_source_records').fetchone()[0]
    providers=[dict(x) for x in conn.execute("""SELECT source_key,COUNT(*) AS records
               FROM universal_source_records GROUP BY source_key ORDER BY records DESC""").fetchall()]
    return {'site_candidates':total,'source_identities':ids,'sources':providers,
            'coverage_statement':'Source identity discovery only; counts are not physical properties',
            'loss_scores':'unranked','latest_imports':[dict(x) for x in conn.execute(
            'SELECT * FROM universal_import_runs ORDER BY id DESC LIMIT 15').fetchall()]}

def review_source_link(conn, *, source_key, source_identifier, target_site_id,
                       evidence_url, rationale, reviewer, approver):
    """Second-party manual link. Never infer physical equivalence from coordinates."""
    _validate_url(evidence_url)
    if not _text(rationale,2000) or not _text(reviewer) or not _text(approver) or reviewer==approver:
        raise ValueError('Evidence, rationale and different reviewer/approver identities required')
    initialize(conn)
    with conn:
        src=conn.execute('SELECT site_id FROM universal_source_records WHERE source_key=? AND source_identifier=?',
                         (source_key,source_identifier)).fetchone()
        target=conn.execute('SELECT id FROM universal_sites WHERE id=?',(target_site_id,)).fetchone()
        if not src or not target:
            raise ValueError('Unknown source identity or destination site')
        old=src['site_id']
        if old==target_site_id:
            raise ValueError('Already assigned to this site')
        conn.execute('UPDATE universal_source_records SET site_id=? WHERE source_key=? AND source_identifier=?',
                     (target_site_id,source_key,source_identifier))
        conn.execute("""INSERT INTO universal_identity_decisions
             (source_key,source_identifier,from_site_id,to_site_id,evidence_url,
              rationale,reviewer,approver,decided_at) VALUES (?,?,?,?,?,?,?,?,?)""",
             (source_key,source_identifier,old,target_site_id,evidence_url,
              rationale,reviewer,approver,_now()))
        # Only an empty, provisional record can be retired after consolidation.
        conn.execute("""DELETE FROM universal_sites WHERE id=? AND site_status='source_observation'
             AND NOT EXISTS (SELECT 1 FROM universal_source_records WHERE site_id=universal_sites.id)
             AND NOT EXISTS (SELECT 1 FROM universal_research_links WHERE site_id=universal_sites.id)""",
             (old,))
    return {'linked_to':target_site_id,'previous_site':old,'verified_by':[reviewer,approver]}

def track_for_research(conn, site_id, actor):
    """Opt-in promotion into the existing private research workspace, still unverified."""
    from .site_workspace import intake_site
    initialize(conn)
    existing=conn.execute('SELECT research_facility_id FROM universal_research_links WHERE site_id=?',
                          (site_id,)).fetchone()
    if existing:
        return {'facility_id':existing['research_facility_id'],'already_tracked':True}
    record=detail(conn,site_id)
    if not record:
        raise ValueError('Unknown facility candidate')
    s=record['site']
    src=record['source_identities']
    result=intake_site(conn,{'name':s['name'],'company':s['company'],'address':s['address'],
        'city':s['city'],'state':s['state'],'country':s['country'],
        'sector':s['industry'],'source_url':src[0]['source_url'] if src else ''},actor)
    facility_id=result['facility_id']
    with conn:
        conn.execute('INSERT INTO universal_research_links VALUES (?,?)',(site_id,facility_id))
    return {'facility_id':facility_id,'already_tracked':False}
