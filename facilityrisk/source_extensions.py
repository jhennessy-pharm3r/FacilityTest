"""Additional public-source validation and review-only geospatial incident staging.

Official source pages and structured endpoints are probed separately from schema,
facility matching, and outcome validation. A nearby incident is NEVER automatically
a finding or loss at the insured facility.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import math
from pathlib import Path
from urllib.parse import urlparse

import requests

from .ingest import stable_id, utcnow
from .match import haversine_km

# These are researched source capabilities, not assertions of successful live
# ingestion. Data access, attribution, date semantics and licensing are separate gates.
SOURCES = (
    dict(key='nrc', name='USCG National Response Center', priority='High',
         category='Chemical release / incident', coverage='U.S. incident reports',
         access='Official report lookup / export; initial reports unverified',
         integration='review_only_geo_csv', probe_kind='html',
         documentation='https://nrc.uscg.mil/',
         test='Match reported address/operator; corroborate with agency follow-up and event chronology.',
         limitation='Initial reports are allegations, not confirmed facility incidents.'),
    dict(key='csb', name='U.S. Chemical Safety Board', priority='High',
         category='Process safety', coverage='Investigated U.S. fires, explosions and releases',
         access='Case pages and investigation reports; case-by-case extraction',
         integration='review_only_geo_csv', probe_kind='html',
         documentation='https://www.csb.gov/investigations/',
         test='Confirm investigated site, accident cause, injury, operations and final-report publication.',
         limitation='Selected serious incidents, not a denominator of all U.S. industrial failures.'),
    dict(key='neris', name='NERIS Public Incident Basics', priority='High',
         category='Fire / emergency response', coverage='U.S. current-year reported incidents',
         access='Public dataset; incident basics lag reporting by about 60 days',
         integration='review_only_geo_csv', probe_kind='html',
         documentation='https://www.usfa.fema.gov/neris/public/',
         test='Check coordinates, fire location and any reported incident amendments.',
         limitation='Reported response location does not establish damage at the insured site.'),
    dict(key='nfirs', name='NFIRS historical fire incidents', priority='High',
         category='Fire / emergency response', coverage='U.S. historical reports through 2025',
         access='OpenFEMA historical public releases; NFIRS now retired',
         integration='review_only_geo_csv', probe_kind='html',
         documentation='https://www.usfa.fema.gov/data-insights/nfirs/data/',
         test='Use linked relational keys and address verification; measure reporting bias.',
         limitation='Voluntary and incomplete reporting; no automatic address-level attribution.'),
    dict(key='fda_inspections', name='FDA inspections and compliance', priority='High',
         category='Regulatory / manufacturing', coverage='U.S. FDA-regulated sites',
         access='Official FDA CSV; existing application adapter',
         integration='existing_fda_csv', probe_kind='html',
         documentation='https://www.fda.gov/about-fda/performance-data/fda-data-dashboard',
         test='Validate exact FEI, inspection classification, and evidence availability before subsequent interruption.',
         limitation='Regulatory finding is not proof of property loss or shutdown.'),
    dict(key='aqueduct_floods', name='WRI Aqueduct Floods', priority='High',
         category='Flood', coverage='Global riverine and coastal inundation scenarios',
         access='Download modeled GeoTIFF inundation-depth rasters',
         integration='geospatial_raster_pending', probe_kind='html',
         documentation='https://datasets.wri.org/datasets/aqueduct-floods-hazard-maps',
         test='Overlay independently reviewed site point and compare hazard vintage, return period and FEMA flood zone.',
         limitation='Modeled depths, not actual property damage; flood protection not fully represented.'),
    dict(key='eia861', name='EIA-861 Electricity Reliability', priority='High',
         category='Utilities / business interruption', coverage='U.S. electricity utilities',
         access='Annual XLS/XLSX reliability and service-territory downloads',
         integration='utility_crosswalk_pending', probe_kind='html',
         documentation='https://www.eia.gov/electricity/data/eia861/',
         test='Verify serving utility and outage methods; compare SAIDI and SAIFI with disclosed disruptions.',
         limitation='Utility averages are NOT measured outages at an individual factory.'),
    dict(key='ireland_leap', name='Ireland EPA LEAP', priority='High',
         category='Environmental compliance', coverage='Licensed Irish industrial sites',
         access='Public Swagger-described REST API under CC BY 4.0',
         integration='identity_and_schema_pending', probe_kind='swagger',
         documentation='https://data.epa.ie/api-list/leap-open-data/',
         probe_url='https://data.epa.ie/leap/swagger/v1/swagger.json',
         test='Resolve Galway/Clonmel licence profile and site ID before retrieving incidents and enforcement.',
         limitation='A site/authorisation identifier must be corroborated; API coverage differs by licence.'),
    dict(key='eu_industrial', name='European Industrial Emissions Portal', priority='Medium-High',
         category='Emissions / environmental', coverage='European industrial complexes',
         access='EU Registry, E-PRTR reporting and spatial datasets',
         integration='facility_crosswalk_pending', probe_kind='html',
         documentation='https://industry.eea.europa.eu/industrial-emissions/dataset',
         test='Link physical site or production installation, pollutants and annual reporting changes.',
         limitation='Reporting thresholds and registry site structures differ from individual buildings.'),
    dict(key='canada_npri', name='Canada National Pollutant Release Inventory', priority='Medium-High',
         category='Emissions / environmental', coverage='Canadian NPRI reporting facilities',
         access='Bulk release, disposal, transfer and geolocation CSV',
         integration='facility_crosswalk_pending', probe_kind='html',
         documentation='https://open.canada.ca/data/en/dataset/40e01423-7728-429c-ac9d-2954385ccdfb',
         test='Match NPRI facility identifier and normalized physical address; compare pollutant/year trends.',
         limitation='Reporting threshold and toxic release quantities do not equal human exposure or BI loss.'),
    dict(key='rsei', name='EPA Risk-Screening Environmental Indicators', priority='Medium',
         category='Relative pollution impact', coverage='U.S. TRI-linked screening models',
         access='EPA EasyRSEI or model-result downloads',
         integration='tri_crosswalk_pending', probe_kind='html',
         documentation='https://www.epa.gov/rsei',
         test='Match version-consistent RSEI and TRI facility IDs; distinguish modeled exposure from release mass.',
         limitation='Relative modeled potential impact, not an individual property loss or health determination.'),
    dict(key='wildfire', name='USFS Wildfire Risk to Communities', priority='Medium',
         category='Wildfire', coverage='U.S. regional wildfire likelihood and exposure',
         access='GIS/region downloads and tabular community summaries',
         integration='geospatial_raster_pending', probe_kind='html',
         documentation='https://wildfirerisk.org/download/',
         test='Evaluate reviewed points and service areas using layer scale and annual burn probability.',
         limitation='National models are not calibrated for individual factories or buildings.'),
    dict(key='ucdp', name='UCDP Georeferenced Event Dataset', priority='Medium',
         category='Organized violence / geopolitical', coverage='Global conflict events',
         access='Versioned CSV downloads; API now requires an access token',
         integration='review_only_geo_csv', probe_kind='html',
         documentation='https://ucdp.uu.se/downloads/',
         test='Require event geocoding precision, date, location and regional relevance before any site association.',
         limitation='Not a complete measure of strikes/civil unrest; coarse geocoding may obscure distance.'),
    dict(key='phmsa', name='PHMSA Hazmat Transportation Incidents', priority='Medium',
         category='Transport / supply chain', coverage='U.S. hazardous material transport',
         access='Official 5800.1 search and export reports',
         integration='review_only_geo_csv', probe_kind='html',
         documentation='https://www.phmsa.dot.gov/hazmat-program-management-data-and-statistics/data-operations/incident-statistics',
         test='Determine shipment/route relevance and distinguish transportation events from plant incidents.',
         limitation='Nearby accident does not establish a supply chain impact or site-level release.'),
)

SOURCE_BY_KEY = {s['key']: s for s in SOURCES}
GEO_CSV_SOURCES = frozenset(s['key'] for s in SOURCES if s['integration'] == 'review_only_geo_csv')

SCHEMA = """
CREATE TABLE IF NOT EXISTS external_event_candidates (
  id TEXT PRIMARY KEY,
  facility_id TEXT NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
  source_key TEXT NOT NULL, source_record_id TEXT NOT NULL,
  event_date TEXT, title TEXT NOT NULL, source_url TEXT NOT NULL,
  latitude REAL NOT NULL, longitude REAL NOT NULL, distance_km REAL NOT NULL,
  geo_precision TEXT, provenance_sha256 TEXT NOT NULL,
  imported_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending'
    CHECK(status IN ('pending','reviewed_relevant','rejected')),
  reviewer TEXT, reviewed_at TEXT, review_note TEXT, review_evidence_url TEXT,
  UNIQUE (facility_id, source_key, source_record_id)
);
CREATE INDEX IF NOT EXISTS idx_external_event_candidates
 ON external_event_candidates(facility_id, source_key, status);
"""


def initialize_extensions(conn):
    conn.executescript(SCHEMA)


def catalog(conn):
    """Return official source metadata and explicitly differentiated test states."""
    checks = {r['source']: dict(r) for r in conn.execute('SELECT * FROM source_health')}
    counts = {r['source_key']: dict(r) for r in conn.execute(
        "SELECT source_key,COUNT(*) AS candidates,"
        "SUM(CASE WHEN status='reviewed_relevant' THEN 1 ELSE 0 END) AS reviewed "
        "FROM external_event_candidates GROUP BY source_key")}
    result = []
    for source in SOURCES:
        row = dict(source)
        row.pop('probe_url', None)
        check = checks.get(source['name'], {})
        matching = counts.get(source['key'], {})
        row['probe_state'] = check.get('state', 'not_tested')
        row['checked_at'] = check.get('checked_at')
        row['probe_details'] = check.get('details', 'No check executed from an internet-enabled environment')
        row['staged_candidates'] = matching.get('candidates', 0)
        row['reviewed_candidates'] = matching.get('reviewed', 0)
        result.append(row)
    return result


def probe_extensions(conn=None, session=None):
    """Reachability of docs and LEAP OpenAPI shape; never imply ingested data.

    No insured company, address, site coordinate or FEI is sent by this probe.
    """
    sess = session or requests.Session()
    result = []
    for spec in SOURCES:
        url = spec.get('probe_url', spec['documentation'])
        try:
            response = sess.get(url, timeout=15, headers={
                'User-Agent': 'Pharm3r-FacilityRisk-SourceValidation/0.5',
                'Accept': 'application/json,text/html;q=0.8'})
            response.raise_for_status()
            if spec['probe_kind'] == 'swagger':
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(payload.get('paths'), dict):
                    raise ValueError('OpenAPI paths object absent')
                paths = payload['paths']
                if not any('LicenceProfile' in x for x in paths):
                    raise ValueError('Expected LEAP LicenceProfile API path absent')
                state = 'schema_reachable'
                detail = 'Official OpenAPI paths parsed; site search and facility ID match still untested'
            else:
                # A publisher home page is only a documentation probe; no CSV,
                # feature layer, license or facility record has been fetched.
                state = 'docs_reachable'
                detail = 'Official source page reachable; dataset access, schema and facility match not tested'
        except Exception as exc:
            state = 'failed'
            detail = (type(exc).__name__ + ': ' + str(exc))[:320]
        if conn:
            from .advanced_sources import record_source_check
            record_source_check(conn, spec['name'], state, url, detail)
        result.append(dict(source=spec['name'], key=spec['key'], state=state, url=url, details=detail))
    return result


def _file_hash(path: Path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_source_url(value, fallback):
    url = str(value or '').strip()
    if not url:
        return fallback
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Source record URL must be valid HTTPS or left empty')
    return url


def import_geo_csv(conn, file_path, source_key, *,
                   id_column='id', latitude_column='latitude',
                   longitude_column='longitude', date_column='date_start',
                   title_column='description', url_column='',
                   precision_column='', radius_km=25.0):
    """Stage candidate nearby events from a locally obtained official CSV.

    Caller provides the ACTUAL field names from the dataset's release vintage.
    Only independently reviewed site coordinates participate. Staged events
    are not copied into evidence and are never interpreted as insured losses.
    """
    if source_key not in GEO_CSV_SOURCES:
        raise ValueError('This source has no incident-level CSV staging adapter')
    if not (0.5 <= radius_km <= 100):
        raise ValueError('Search radius must be 0.5-100 km')
    path = Path(file_path)
    if not path.is_file():
        raise ValueError('CSV file not found')
    sites = [dict(row) for row in conn.execute("""
       SELECT f.id,f.latitude,f.longitude FROM facilities f
       JOIN location_reviews l ON l.facility_id=f.id
       WHERE l.precision IN ('site_verified','property_polygon')
         AND f.latitude BETWEEN -90 AND 90
         AND f.longitude BETWEEN -180 AND 180
    """)]
    if not sites:
        raise ValueError('No independently reviewed site coordinates; no proximity matches allowed')
    required = [id_column, latitude_column, longitude_column, date_column, title_column]
    required += [x for x in (url_column, precision_column) if x]
    if any(not x or not isinstance(x, str) for x in required):
        raise ValueError('CSV column names are required')
    sha = _file_hash(path)
    totals = dict(source=source_key, rows_seen=0, invalid_rows=0,
                  outside_radius=0, candidates_nearby=0, new_candidates=0,
                  verified_sites_tested=len(sites), csv_sha256=sha)
    opener = gzip.open if path.name.lower().endswith('.gz') else open
    try:
        with opener(path, 'rt', encoding='utf-8-sig', newline='', errors='replace') as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or not set(required).issubset(reader.fieldnames):
                raise ValueError('CSV missing required columns: ' + ', '.join(sorted(set(required)-set(reader.fieldnames or []))))
            for row in reader:
                totals['rows_seen'] += 1
                record_id = str(row.get(id_column) or '').strip()
                title = str(row.get(title_column) or '').strip()[:1200]
                if not record_id or not title:
                    totals['invalid_rows'] += 1
                    continue
                try:
                    lat = float(row.get(latitude_column) or 'nan')
                    lon = float(row.get(longitude_column) or 'nan')
                except (ValueError, TypeError):
                    totals['invalid_rows'] += 1
                    continue
                if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    totals['invalid_rows'] += 1
                    continue
                event_date = str(row.get(date_column) or '').strip()[:60]
                precision = str(row.get(precision_column) or '').strip()[:120] if precision_column else 'unverified source geocode'
                url = _safe_source_url(row.get(url_column) if url_column else '', SOURCE_BY_KEY[source_key]['documentation'])
                has_match = False
                for site in sites:
                    distance = haversine_km(site['latitude'], site['longitude'], lat, lon)
                    if distance > radius_km:
                        continue
                    has_match = True
                    totals['candidates_nearby'] += 1
                    candidate_id = stable_id('additional_geo_candidate', source_key, site['id'], record_id)
                    cur = conn.execute("""
                    INSERT OR IGNORE INTO external_event_candidates
                    (id,facility_id,source_key,source_record_id,event_date,title,
                     source_url,latitude,longitude,distance_km,geo_precision,
                     provenance_sha256,imported_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (candidate_id, site['id'], source_key, record_id, event_date,
                          title, url, lat, lon, distance, precision, sha, utcnow()))
                    totals['new_candidates'] += max(0, cur.rowcount)
                if not has_match:
                    totals['outside_radius'] += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return totals


def review_event_candidate(conn, candidate_id, decision, reviewer, evidence_url, reason):
    """Review whether a nearby event is relevant CONTEXT, not a site loss."""
    if decision not in ('reviewed_relevant', 'rejected'):
        raise ValueError('Decision must be reviewed_relevant or rejected')
    if not reviewer or len(reviewer.strip()) < 2 or len((reason or '').strip()) < 12:
        raise ValueError('Reviewer and detailed rationale required')
    url = _safe_source_url(evidence_url, '')
    if not url:
        raise ValueError('Review requires an HTTPS corroborating record URL')
    row = conn.execute('SELECT id FROM external_event_candidates WHERE id=?', (candidate_id,)).fetchone()
    if row is None:
        raise ValueError('Unknown candidate')
    conn.execute("""
       UPDATE external_event_candidates
       SET status=?, reviewer=?, review_evidence_url=?, review_note=?, reviewed_at=?
       WHERE id=?""", (decision, reviewer.strip(), url, reason.strip(), utcnow(), candidate_id))
    conn.commit()
    return {'candidate_id':candidate_id, 'status':decision,
            'notice':'Reviewed for contextual relevance only. No insured-site event or loss is asserted.'}
