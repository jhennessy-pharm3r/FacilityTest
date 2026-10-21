"""Auditable intake and non-FDA source identities for facility discovery.

Official registry rows are source-reported *candidates*, not verified physical
properties. Names alone never merge sites across registries. No site risk score,
claim or environmental violation is asserted by this module.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import re
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from .ingest import stable_id, utcnow
from .intelligence import audit, name_similarity
from .match import haversine_km

SOURCES = {
    'EPA_FRS': ('US EPA Facility Registry Service','https://www.epa.gov/frs'),
    'EPA_TRI': ('US EPA Toxics Release Inventory','https://www.epa.gov/toxics-release-inventory-tri-program'),
    'EPA_RCRA': ('US EPA RCRAInfo','https://rcrapublic.epa.gov/'),
    'EPA_NPDES': ('US EPA NPDES','https://echo.epa.gov/'),
    'OSHA_EST': ('US OSHA Establishment','https://www.osha.gov/establishment-search'),
    'CA_NPRI': ('Canada National Pollutant Release Inventory','https://www.canada.ca/en/environment-climate-change/services/national-pollutant-release-inventory.html'),
    'IE_LEAP': ('Ireland EPA LEAP','https://data.epa.ie/api-list/leap-open-data/'),
    'EU_EPRTR': ('European Industrial Emissions Portal','https://industry.eea.europa.eu/'),
    'GB_ENV': ('UK Environment Agency regulated site','https://environment.data.gov.uk/'),
    'EU_EUDRAGMDP': ('European EudraGMDP establishment','https://eudragmdp.ema.europa.eu/'),
    'CH_SWISSGMDP': ('SwissGMDP establishment','https://www.swissmedic.ch/'),
    'CA_HEALTH': ('Health Canada establishment','https://health-products.canada.ca/'),
    'JP_PMDA': ('Japan PMDA establishment','https://www.pmda.go.jp/'),
    'CN_NMPA': ('China NMPA establishment','https://www.nmpa.gov.cn/'),
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS external_registry_entities (
 id TEXT PRIMARY KEY,
 source_key TEXT NOT NULL,
 source_identifier TEXT NOT NULL,
 name TEXT NOT NULL,
 company TEXT,
 address TEXT,
 city TEXT,
 state TEXT,
 country TEXT,
 sector TEXT,
 operations TEXT,
 source_url TEXT NOT NULL,
 source_sha256 TEXT NOT NULL,
 imported_at TEXT NOT NULL,
 UNIQUE(source_key,source_identifier)
);
CREATE INDEX IF NOT EXISTS idx_ext_reg_name ON external_registry_entities(name);
CREATE INDEX IF NOT EXISTS idx_ext_reg_company ON external_registry_entities(company);
CREATE INDEX IF NOT EXISTS idx_ext_reg_country ON external_registry_entities(country);
CREATE INDEX IF NOT EXISTS idx_ext_reg_source ON external_registry_entities(source_key);
CREATE TABLE IF NOT EXISTS external_registry_imports (
 source_key TEXT PRIMARY KEY,
 source_url TEXT NOT NULL,
 source_sha256 TEXT NOT NULL,
 imported_at TEXT NOT NULL,
 read_rows INTEGER NOT NULL,
 valid_rows INTEGER NOT NULL,
 notes TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_other_site_identity_verified
 ON identity_links(namespace,identifier)
 WHERE status='verified' AND namespace IN
 ('EPA_TRI','EPA_RCRA','EPA_NPDES','OSHA_EST','CA_NPRI','IE_LEAP',
  'EU_EPRTR','GB_ENV','EU_EUDRAGMDP','CH_SWISSGMDP','CA_HEALTH','JP_PMDA','CN_NMPA');
"""

def initialize_workspace(conn):
    conn.executescript(SCHEMA)


def _text(value, maximum=250):
    if value is None or isinstance(value,(dict,list)):
        return ''
    return re.sub(r'\\s+', ' ', str(value)).strip()[:maximum]


def _url(value):
    url=_text(value,1500)
    part=urlsplit(url)
    if part.scheme!='https' or not part.hostname or part.username or part.password:
        raise ValueError('An HTTPS source record or documentation URL is required')
    return url


def intake_site(conn, payload, actor):
    """Create a genuinely unassessed site without a false address/name merge."""
    if not isinstance(payload,dict):raise ValueError('Site payload must be an object')
    name=_text(payload.get('name'),160)
    if len(name)<3:raise ValueError('Site name must have at least three characters')
    company=_text(payload.get('company'),160) or name
    country=_text(payload.get('country'),80)
    address=_text(payload.get('address'),240)
    city=_text(payload.get('city'),120)
    state=_text(payload.get('state'),120)
    sector=_text(payload.get('sector'),120)
    source_url=_text(payload.get('source_url'),1500)
    if source_url:_url(source_url)
    fid='intake-'+uuid.uuid4().hex
    full_address=', '.join(x for x in (address,city,state,country) if x)
    note='Manually supplied source URL (not yet verified)' if source_url else 'Manual research request; no independently corroborated source'
    with conn:
        conn.execute("""INSERT INTO facilities
            (id,name,company,activity,address,country,site_case,research_summary,
             source_coverage_note,data_gaps,origin,last_imported)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (fid,name,company,sector or 'Not evaluated',full_address,country,
             'Research requested',
             'Newly opened site; operator, physical location and source identity are not verified.',
             note,
             'Property geocode, hazards, regulator crosswalks, construction, loss history and BI exposure are unknown.',
             'Manual source intake (unverified)',utcnow()))
        audit(conn,'manual_facility_intake',fid,actor,
              {'name':name,'country':country,'city':city,'source_url':source_url,'unverified':True})
    return {'facility_id':fid,'status':'unverified','warning':'Research intake only; no source match or risk rating asserted'}


def import_official_registry_csv(conn, path, source_key, source_url, *, 
                                 id_column='source_id', name_column='name',
                                 company_column='',address_column='address',
                                 city_column='',state_column='',country_column='country',
                                 sector_column='',operations_column='',notes=''):
    """Load an authorized downloaded registry CSV, with explicit source-field mapping.

    Every row retains its own official source ID and file checksum. Nothing links
    to an insured's facility or gets marked operational/current by default.
    """
    if source_key not in SOURCES:raise ValueError('Unsupported regulatory source')
    source_url=_url(source_url)
    path=Path(path)
    if not path.is_file():raise ValueError('Registry CSV not found')
    columns={'id':id_column,'name':name_column,'company':company_column,
             'address':address_column,'city':city_column,'state':state_column,
             'country':country_column,'sector':sector_column,'operations':operations_column}
    required={x for x in columns.values() if x}
    if not id_column or not name_column:raise ValueError('Source ID and name columns required')
    digest=hashlib.sha256()
    with path.open('rb') as raw:
        for chunk in iter(lambda:raw.read(1024*1024),b''):
            digest.update(chunk)
    sha=digest.hexdigest()
    opener=gzip.open if str(path).lower().endswith('.gz') else open
    stored=[];ids=set();seen=0;invalid=0
    with opener(path,'rt',encoding='utf-8-sig',errors='replace',newline='') as fh:
        reader=csv.DictReader(fh)
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError('CSV missing mapped columns: '+', '.join(sorted(required-set(reader.fieldnames or []))))
        for row in reader:
            seen+=1
            if seen>500000:raise ValueError('Registry import exceeds 500,000 rows; split into source partitions')
            source_id=_text(row.get(id_column),160)
            name=_text(row.get(name_column),160)
            if not source_id or not name:
                invalid+=1
                continue
            if source_id in ids:
                raise ValueError('Duplicate source identifier in one file: '+source_id[:80])
            ids.add(source_id)
            get=lambda key,max_len=250: _text(row.get(columns[key]),max_len) if columns[key] else ''
            stored.append(('external-'+stable_id(source_key,source_id),source_key,source_id,name,
                           get('company',160) or name,get('address',240),get('city',120),
                           get('state',120),get('country',80),get('sector',120),
                           get('operations',300),source_url,sha,utcnow()))
    if not stored:raise ValueError('No source IDs with named establishments; source not imported')
    initialize_workspace(conn)
    with conn:
        conn.executemany("""INSERT INTO external_registry_entities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(source_key,source_identifier) DO UPDATE SET
           name=excluded.name,company=excluded.company,address=excluded.address,
           city=excluded.city,state=excluded.state,country=excluded.country,
           sector=excluded.sector,operations=excluded.operations,
           source_url=excluded.source_url,source_sha256=excluded.source_sha256,
           imported_at=excluded.imported_at""",stored)
        conn.execute("""INSERT INTO external_registry_imports VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(source_key) DO UPDATE SET source_url=excluded.source_url,
           source_sha256=excluded.source_sha256,imported_at=excluded.imported_at,
           read_rows=excluded.read_rows,valid_rows=excluded.valid_rows,notes=excluded.notes""",
           (source_key,source_url,sha,utcnow(),seen,len(stored),_text(notes,900)))
        audit(conn,'regulatory_registry_import',source_key,'local-import',
              {'sha256':sha,'rows':len(stored),'invalid':invalid,'source_url':source_url})
    return {'source_key':source_key,'source_sha256':sha,'rows_read':seen,
            'source_entities':len(stored),'invalid_rows':invalid,
            'scope':'Unverified source identities; no cross-agency matches or risk conclusions'}


def search_external_registry(conn,query='',source_key='',country='',limit=50,offset=0):
    initialize_workspace(conn)
    words=_text(query,160).casefold().split()
    clauses=[];args=[]
    for word in words:
        escaped=word.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        clauses.append('('+' OR '.join("LOWER("+f+") LIKE ? ESCAPE '\\\\'"
               for f in ('name','company','address','city','source_identifier'))+')')
        args.extend(['%'+escaped+'%']*5)
    if source_key:
        clauses.append('source_key=?');args.append(source_key)
    if country:
        clauses.append('LOWER(country)=?');args.append(country.casefold())
    where=' WHERE '+' AND '.join(clauses) if clauses else ''
    total=conn.execute('SELECT COUNT(*) FROM external_registry_entities'+where,args).fetchone()[0]
    rows=conn.execute('SELECT * FROM external_registry_entities'+where+
                      ' ORDER BY name,id LIMIT ? OFFSET ?',args+[max(1,min(int(limit),100)),max(0,int(offset))]).fetchall()
    return {'items':[dict(row) for row in rows], 'total':total,
            'sources':SOURCES, 'caveat':'Source identity is unverified and is not a verified physical manufacturing plant'}


def track_external_registry_site(conn,record_id,actor):
    row=conn.execute('SELECT * FROM external_registry_entities WHERE id=?',(record_id,)).fetchone()
    if not row:raise ValueError('No such source registry entity')
    fid='source-'+row['id']
    full=', '.join(x for x in (row['address'],row['city'],row['state'],row['country']) if x)
    with conn:
        conn.execute("""INSERT OR IGNORE INTO facilities(id,name,company,activity,address,country,
             site_case,research_summary,source_coverage_note,data_gaps,origin,last_imported)
             VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (fid,row['name'],row['company'],row['operations'] or row['sector'],full,row['country'],
             'Research requested','Official registry observation; facility property is not independently verified.',
             'Source record observed, not an independently validated site/parent match',
             'Insurance exposures and physical-site corroboration are not evaluated',
             'Source registry: '+row['source_key'],utcnow()))
        conn.execute("""INSERT OR IGNORE INTO identity_links
            (id,facility_id,namespace,identifier,status,provenance_url,provenance_note,created_at)
            VALUES(?,?,?,?,?,?,?,?)""",
            (stable_id('observed_source_identity',fid,row['source_key'],row['source_identifier']),
             fid,row['source_key'],row['source_identifier'],'observed',row['source_url'],
             'Official source-reported identifier; independent site identity review pending',utcnow()))
        audit(conn,'source_registry_tracked',fid,actor,
              {'external_id':record_id,'namespace':row['source_key'],
               'source_identifier':row['source_identifier']})
    return {'facility_id':fid,'status':'unverified','source_identity':'observed'}


def stage_identity_candidate(conn,facility_id,external_id,actor):
    """Present independent regulatory record for review; never silently link."""
    f=conn.execute('SELECT * FROM facilities WHERE id=?',(facility_id,)).fetchone()
    r=conn.execute('SELECT * FROM external_registry_entities WHERE id=?',(external_id,)).fetchone()
    if not f or not r:raise ValueError('Unknown site or external registry record')
    candidate_id=stable_id('source_identity_candidate',facility_id,r['source_key'],r['source_identifier'])
    with conn:
        conn.execute("""INSERT INTO match_candidates
          (id,facility_id,namespace,identifier,candidate_name,candidate_address,
           distance_km,name_similarity,source_url,retrieved_at)
          VALUES (?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(facility_id,namespace,identifier) DO UPDATE SET
            candidate_name=excluded.candidate_name,candidate_address=excluded.candidate_address,
            name_similarity=excluded.name_similarity,
            source_url=excluded.source_url,retrieved_at=excluded.retrieved_at""",
            (candidate_id,facility_id,r['source_key'],r['source_identifier'],r['name'],
             ', '.join(x for x in (r['address'],r['city'],r['state'],r['country']) if x),
             None,name_similarity(f['name'],r['name']),r['source_url'],utcnow()))
        audit(conn,'identity_candidate_staged',facility_id,actor,
              {'candidate_id':candidate_id,'source_identity':external_id})
    return {'candidate_id':candidate_id,'decision':'pending_or_existing',
            'warning':'Source identity is only a candidate until reviewed with corroboration'}
