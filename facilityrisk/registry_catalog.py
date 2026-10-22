"""Searchable FDA establishment catalog, kept separate from evaluated risk evidence.

The openFDA device download contains listing records, not distinct physical sites.
We collapse exact FDA registration/FEI identities within each source while retaining
source record counts. Device and drug registries remain separate until an audited
physical-site crosswalk can establish equivalence.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import csv
import codecs
import io
import json
import re
import sqlite3
import zipfile
import pycountry

FIELDS = ('id','name','company','city','state','country','fei','registration_number',
          'activities','sector','address','expiry_year','source','source_records')
SOURCE_DEVICE = 'FDA device registration / listing'
SOURCE_DRUG = 'FDA drug establishment (DECRS)'
MAX_ROWS = 1_000_000


def clean(value, limit=250):
    if value is None: return ''
    if isinstance(value,(list,dict)): return ''
    return re.sub(r'\s+',' ',str(value)).strip()[:limit]


def ident(value):
    return re.sub(r'\D','',clean(value))


def sid(source, fei, reg, address, name, country):
    # Preserve FDA FEI as an observed identity, not as a verified physical-site match.
    # Registration number prevents distinct establishments being merged on similar names.
    if fei: key='fei:'+fei
    elif reg: key='registration:'+reg
    else: key='site:'+clean(country).lower()+'|'+clean(name).lower()+'|'+clean(address).lower()
    return source.lower().split()[1]+'-'+sha256(key.encode('utf-8')).hexdigest()[:20]


def normalize_device(raw):
    r=raw.get('registration') or {}
    if not isinstance(r,dict): return None
    oo=r.get('owner_operator') or {}
    if not isinstance(oo,dict): oo={}
    name=clean(r.get('name'))
    if not name: return None
    fei=ident(r.get('fei_number'))
    reg=ident(r.get('registration_number'))
    a=clean(' '.join(str(r.get(k) or '') for k in ('address_line_1','address_line_2')))
    country=clean(r.get('iso_country_code'),4).upper()
    roles=raw.get('establishment_type') or []
    if isinstance(roles,str): roles=[roles]
    roles=[clean(x,80) for x in roles if clean(x)]
    return dict(id=sid(SOURCE_DEVICE,fei,reg,a,name,country),name=name,company=clean(oo.get('firm_name')) or name,
       city=clean(r.get('city')),state=clean(r.get('state_code')),country=country,fei=fei,
       registration_number=reg,activities='; '.join(dict.fromkeys(roles))[:300],sector='Medical device',address=a,
       expiry_year=clean(r.get('reg_expiry_date_year'),4),source=SOURCE_DEVICE,source_records=1)


def normal_key(k):
    return re.sub(r'[^a-z0-9]','',str(k).casefold().lstrip('\ufeff'))


def first(row,*aliases):
    mapping={normal_key(k):v for k,v in row.items() if k}
    for k in aliases:
        val=mapping.get(normal_key(k))
        if val and clean(val): return clean(val)
    return ''


def _iso_countries():
    """Exact ISO names only, never fuzzy geography matching."""
    mapping={}
    for c in pycountry.countries:
        for name in (getattr(c,'name',''),getattr(c,'official_name',''),
                     getattr(c,'common_name','')):
            if name:mapping[name.casefold()]=c.alpha_2
        mapping[c.alpha_2.casefold()]=c.alpha_2
    mapping.update({
        'united states of america':'US','usa':'US','u.s.a.':'US',
        'u.s.':'US','great britain':'GB','uk':'GB',
        'south korea':'KR','north korea':'KP','russia':'RU',
        'taiwan':'TW','vietnam':'VN','turkey':'TR',
        'czech republic':'CZ','ivory coast':'CI'
    })
    # Identical to place/region names in common U.S. postal addresses.
    for ambiguous in ('georgia','congo','guinea','niger','dominica'):
        mapping.pop(ambiguous,None)
    return mapping


COUNTRY_NAMES=_iso_countries()


def country_from_explicit_address(address):
    """Recognize only an *explicit final country segment* in source address text.

    E.g., `Factory Road, Cork, Ireland` -> IE.
    No postal-state inference and no substring matching ("Canadian Street").
    Ambiguous country/state place names remain unresolved.
    """
    parts=[x.strip(' .\\t') for x in re.split(r'[,;]',clean(address,500))]
    if len(parts)<2:return ''
    last=parts[-1].casefold()
    if last in ('us','ca','in','ga'):return ''  # country vs state/postal ambiguity
    return COUNTRY_NAMES.get(last,'')


def exact_country_field(value):
    """Country field must be an exact published ISO name/code, never guessed."""
    raw=clean(value,120).casefold()
    if raw in ('us','ca','in','ga') and len(raw)==2:
        return COUNTRY_NAMES.get(raw,'')  # dedicated field is unambiguous
    return COUNTRY_NAMES.get(raw,'')


def normalize_drug(row):
    """Map official DECRS columns; never use contact/agent fields as site data.

    FDA's downloadable file has also appeared as tab-delimited Windows-1252 text.
    FEI and DUNS are distinct administrative identifiers. registration_number is
    reserved for an explicitly supplied registration number, otherwise DUNS as an
    observed source lookup key (not asserted to be a registration number).
    """
    name=first(row,'establishment name','establishment','firm name','firmname',
               'site name','facility name','establishment_name','firm legal name')
    fei=ident(first(row,'FEI','FEI Number','FDA Establishment Identifier',
                    'fda_fei','fei_number','FDA FEI'))
    duns=ident(first(row,'DUNS','DUNS number','establishment duns','duns_number',
                     'firm duns','DUNS No'))
    a=first(row,'firm address','establishment address','physical address',
            'address','street address','address line 1','address_1',
            'address1','street_address','address 1','facility address')
    city=first(row,'city','establishment city','firm city')
    explicit_country=first(row,'country','country code','country name','iso country code',
                           'iso_country_code','establishment country')
    country=exact_country_field(explicit_country) if explicit_country else ''
    address_country=country_from_explicit_address(a) if not country else ''
    country=country or address_country
    country_origin=('official_country_field' if country and explicit_country else
                    'explicit_address_suffix' if address_country else 'unresolved')
    if not name or not (fei or duns or (a and city and country)):
        return None
    explicit_registration=ident(first(row,'registration number','drug establishment registration number'))
    # Schema 1.0 has one secondary-ID column. Prefer a published registration
    # number, otherwise preserve DUNS as an observed lookup identifier.
    secondary=explicit_registration or duns
    return dict(id=sid(SOURCE_DRUG,fei,secondary,a,name,country),name=name,
        company=first(row,'registrant name','registrant','labeler name',
                      'owner operator','company name') or name,
        city=city,state=first(row,'state','state province','state code','province','firm state'),
        _country_origin=country_origin,
        country=country,fei=fei,registration_number=secondary,
        activities=first(row,'business operation','business operations',
                         'business_operation','operations','activity',
                         'business operation codes') or 'Registered drug establishment',
        sector='Pharmaceutical',address=a,
        expiry_year=first(row,'registration expiration date','expiration year',
                          'expiry year','expiration date','registration expires')[:16],
        source=SOURCE_DRUG,source_records=1)

def merge(target, record):
    key=record['id']
    if key not in target:
        target[key]=record.copy();return
    old=target[key]
    old['source_records']+=1
    # FEI/registration may appear across multiple address or operator variants.
    # Keep conflicting reported values explicitly; never hide possible relocation,
    # different buildings or stale registration behind the surviving first row.
    for field in ('name','company','address','city','state','country'):
        observed=old.get(field) or ''
        incoming=record.get(field) or ''
        if observed and incoming and normal_key(observed)!=normal_key(incoming):
            variants=old.setdefault('_source_conflicts',{}).setdefault(field,[observed])
            if all(normal_key(v)!=normal_key(incoming) for v in variants):
                variants.append(incoming)
    # Preserve alternate operation roles, but never assert physical identity across FDA sectors.
    roles=list(dict.fromkeys(filter(None,old['activities'].split('; ')+record['activities'].split('; '))))
    old['activities']='; '.join(roles)[:300]
    for k in ('name','company','city','state','country','address','fei','registration_number','expiry_year'):
        if not old[k] and record[k]: old[k]=record[k]
    if record.get('country') and old.get('country')==record['country'] and not old.get('_country_origin'):
        old['_country_origin']=record.get('_country_origin','unresolved')
    if record['address'] and old['address'] and normal_key(record['address'])!=normal_key(old['address']):
        old['identity_warning']='Same reported identifier occurs with different street addresses; site review required'


def parse_drug_zip(path:Path):
    """Stream a bounded, headered FDA DECRS CSV/TSV/pipe archive.

    Reject unexpected file types, unrecognized establishment headers and archives
    with no usable site identifiers. Official text may be Windows-1252 encoded,
    may start with a whitespace-prefixed header and may contain a trailing tab.
    Only establishment data is retained; agents, phone and contacts are ignored.
    """
    valid=0
    max_member_size=500_000_000
    with zipfile.ZipFile(path) as z:
        members=[m for m in z.infolist() if not m.is_dir()
                 and m.filename.lower().endswith(('.csv','.txt','.tsv','.psv','.dat'))
                 and 'excluded' not in m.filename.lower()]
        if not members:raise ValueError('DECRS ZIP contains no supported establishment text file')
        for member in members:
            if member.file_size>max_member_size:
                raise ValueError('DECRS member exceeds maximum uncompressed size')
            # Real FDA drls_reg.txt begins with UTF-8-compatible ASCII but
            # has Windows-1252 bytes in later records. A 64-KB preview can
            # misclassify its encoding. Scan the *complete bounded member*
            # using an incremental decoder, then stream the text once more.
            encoding='utf-8-sig'
            decoder=codecs.getincrementaldecoder('utf-8-sig')(errors='strict')
            with z.open(member) as probe:
                try:
                    while True:
                        block=probe.read(1024*1024)
                        if not block:break
                        decoder.decode(block,final=False)
                    decoder.decode(b'',final=True)
                except UnicodeDecodeError:
                    encoding='cp1252'
            print('DECRS text member: '+member.filename+'; encoding='+encoding,flush=True)
            with z.open(member) as file:
                buffered=io.BufferedReader(file)
                text=io.TextIOWrapper(buffered,encoding=encoding,errors='strict',newline='')
                first_line=text.readline()
                delimiter=max((',',first_line.count(',')),
                              ('\t',first_line.count('\t')),
                              ('|',first_line.count('|')),key=lambda x:x[1])
                if delimiter[1]==0:continue
                reader=csv.DictReader(__import__('itertools').chain([first_line],text),
                                      delimiter=delimiter[0])
                hdr={normal_key(x) for x in (reader.fieldnames or []) if x}
                if not hdr.intersection({'establishmentname','firmname','facilityname',
                                         'sitename','establishment','firmlegalname'}):
                    continue
                for row in reader:
                    value=normalize_drug(row)
                    if value:
                        valid+=1
                        yield value
    if not valid:raise ValueError('DECRS ZIP lacked recognizable establishment fields or identifiers')

def make_catalog(records,source_status,*,generated_at=None):
    distinct={}
    for x in records:
        if x and x.get('id'):merge(distinct,x)
    data=sorted(distinct.values(),key=lambda x:(x.get('name','').casefold(),x['id']))
    country_counts=Counter(x['country'] for x in data if x['country'])
    sector_counts=Counter(x['sector'] for x in data)
    # Measure source-record completeness; do not infer country/city from an
    # opaque DECRS free-text address or claim a verified property coordinate.
    field_coverage={}
    for sector in sorted(sector_counts):
        group=[x for x in data if x['sector']==sector]
        field_coverage[sector]={
            'source_identities':len(group),
            'with_fei':sum(bool(x['fei']) for x in group),
            'with_secondary_id':sum(bool(x['registration_number']) for x in group),
            'with_reported_address':sum(bool(x['address']) for x in group),
            'with_structured_city':sum(bool(x['city']) for x in group),
            'with_structured_country':sum(bool(x['country']) for x in group),
            'with_source_country_field':sum(x.get('_country_origin')=='official_country_field' for x in group),
            'with_explicit_address_country':sum(x.get('_country_origin')=='explicit_address_suffix' for x in group),
            'with_operations':sum(bool(x['activities']) for x in group)}
    conflicts=[{'id':r['id'],'source':r['source'],'fei':r.get('fei',''),
                'requires_site_review':True,'conflicting_fields':r['_source_conflicts']}
               for r in data if r.get('_source_conflicts')]
    return {'schema_version':'1.0','generated_at':generated_at or datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'fields':list(FIELDS),'rows':[[rec.get(k,'') for k in FIELDS] for rec in data],
        'summary':{'distinct_source_entities':len(data),'source_rows':sum(int(x['source_records']) for x in data),
                   'countries':len(country_counts),'by_sector':dict(sector_counts),
                    'identity_conflict_count':len(conflicts),
                    'field_coverage_by_sector':field_coverage,
                    'country_counts':dict(country_counts.most_common(300))},
        'identity_conflicts':conflicts,
        'sources':source_status,
        'coverage_note':'FDA registrations linked to the US market, including foreign establishments. Not a worldwide census, a verified site map, or an insurance-risk rating. Historical device listings may be present. Device and drug records are kept separate until independently matched.'}


def validate_catalog(d):
    if not isinstance(d,dict) or d.get('schema_version')!='1.0' or d.get('fields')!=list(FIELDS):
        raise ValueError('Unsupported registry catalog schema')
    if not isinstance(d.get('rows'),list) or len(d['rows'])>MAX_ROWS:raise ValueError('Invalid registry row count')
    ids=set()
    for r in d['rows']:
        if not isinstance(r,list) or len(r)!=len(FIELDS) or not isinstance(r[0],str) or not r[0] or r[0] in ids:
            raise ValueError('Invalid or duplicate registry row')
        ids.add(r[0])
    return d


def expand(r):return dict(zip(FIELDS,r))


def init_registry(conn):
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS registry_facilities (
      id TEXT PRIMARY KEY, name TEXT NOT NULL, company TEXT, city TEXT, state TEXT,
      country TEXT, fei TEXT, registration_number TEXT, activities TEXT, sector TEXT,
      address TEXT, expiry_year TEXT, source TEXT, source_records INTEGER);
    CREATE INDEX IF NOT EXISTS ix_registry_name ON registry_facilities(name);
    CREATE INDEX IF NOT EXISTS ix_registry_fei ON registry_facilities(fei);
    CREATE INDEX IF NOT EXISTS ix_registry_country ON registry_facilities(country);
    CREATE TABLE IF NOT EXISTS registry_import_meta (source TEXT PRIMARY KEY, checked_at TEXT, details_json TEXT);
    ''')


def import_catalog(conn,path):
    d=validate_catalog(json.loads(Path(path).read_text(encoding='utf-8')))
    init_registry(conn)
    with conn:
        conn.execute('DELETE FROM registry_facilities')
        conn.executemany('''INSERT INTO registry_facilities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',d['rows'])
        conn.execute('INSERT OR REPLACE INTO registry_import_meta VALUES (?,?,?)',('catalog',d['generated_at'],json.dumps({'summary':d.get('summary'),'sources':d.get('sources')})))
    return {'imported_facilities':len(d['rows']),'generated_at':d['generated_at'],'source_status':d.get('sources')}


def registry_search(conn,q='',country='',sector='',limit=50,offset=0):
    init_registry(conn)
    where=[];params=[]
    if q:
        words=[x for x in q.casefold().strip().split() if x]
        for word in words:
            where.append('('+' OR '.join('LOWER('+x+') LIKE ?' for x in ('name','company','address','city','state','fei','registration_number'))+')')
            params.extend(['%'+word+'%']*7)
    if country:
        where.append('country=?');params.append(country.upper())
    if sector:
        where.append('sector=?');params.append(sector)
    clause=(' WHERE '+' AND '.join(where)) if where else ''
    total=conn.execute('SELECT COUNT(*) FROM registry_facilities'+clause,params).fetchone()[0]
    sort=' ORDER BY CASE WHEN fei=? THEN 0 WHEN LOWER(name) LIKE ? THEN 1 ELSE 2 END,name,id' if q else ' ORDER BY name,id'
    sort_params=[q,q.lower()+'%'] if q else []
    rows=conn.execute('SELECT * FROM registry_facilities'+clause+sort+' LIMIT ? OFFSET ?',params+sort_params+[limit,offset]).fetchall()
    return {'items':[dict(x) for x in rows],'total':total,'limit':limit,'offset':offset}