"""SQLite persistence and read-only query helpers.

All evidence rows retain workbook provenance, source URLs, match quality and
raw dates. Data storage is NOT a predictive property-loss model.
"""
from __future__ import annotations
import json
import os
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_ROOT / 'data' / 'facility_risk.sqlite'

SCHEMA = '''
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS facilities (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, company TEXT, activity TEXT,
 address TEXT, country TEXT, fei TEXT, latitude REAL, longitude REAL,
 site_case TEXT, research_summary TEXT, source_coverage_note TEXT,
 data_gaps TEXT, origin TEXT NOT NULL, last_imported TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facilities_name ON facilities(name);
CREATE INDEX IF NOT EXISTS idx_facilities_fei ON facilities(fei);
CREATE TABLE IF NOT EXISTS evidence (
 id TEXT PRIMARY KEY,
 facility_id TEXT NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
 source TEXT NOT NULL, program TEXT, date_raw TEXT, record_type TEXT,
 finding TEXT, value_text TEXT, record_ref TEXT, evidence_scope TEXT,
 match_quality TEXT, source_url TEXT, limitations TEXT,
 risk_domain TEXT NOT NULL, origin TEXT NOT NULL, availability_date TEXT,
 spatial_distance_km REAL, retrieval_at TEXT, last_imported TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_facility ON evidence(facility_id);
CREATE INDEX IF NOT EXISTS idx_evidence_source ON evidence(source);
CREATE INDEX IF NOT EXISTS idx_evidence_domain ON evidence(risk_domain);
CREATE TABLE IF NOT EXISTS sec_findings (
 id TEXT PRIMARY KEY, company TEXT, facility_label TEXT,
 finding_type TEXT, incident_window TEXT, finding TEXT, supply_impact TEXT,
 financial_impact TEXT, insurance_recovery TEXT, prior_public_hazard TEXT,
 attribution TEXT, country TEXT, address TEXT, filing_form TEXT,
 reporting_period TEXT, filing_date TEXT, section TEXT, filing_url TEXT,
 public_evidence_ids TEXT, caveats TEXT, facility_id TEXT REFERENCES facilities(id),
 event_group TEXT NOT NULL, origin TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sec_findings_facility ON sec_findings(facility_id);
CREATE TABLE IF NOT EXISTS public_evidence (
 id TEXT PRIMARY KEY, related_findings TEXT, source TEXT, date_vintage TEXT,
 observation TEXT, match_timing TEXT, limitations TEXT, source_url TEXT,
 origin TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT, record_level TEXT,
 facility_matching TEXT, history TEXT, update_schedule TEXT, access_method TEXT,
 license_notes TEXT, uses TEXT, limitations TEXT, core_tables TEXT, url TEXT,
 origin TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS field_catalog (
 id TEXT PRIMARY KEY, source TEXT, dataset TEXT, table_name TEXT,
 purpose TEXT, field_count TEXT, join_identifiers TEXT, key_risk_fields TEXT,
 actual_fields TEXT, download_url TEXT, documentation_url TEXT, caveats TEXT,
 origin TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ingestion_runs (
 id TEXT PRIMARY KEY, source TEXT NOT NULL, started_at TEXT NOT NULL,
 finished_at TEXT, status TEXT NOT NULL, imported_count INTEGER NOT NULL DEFAULT 0,
 source_sha256 TEXT, details_json TEXT
);
CREATE TABLE IF NOT EXISTS regulatory_observations (
 id TEXT PRIMARY KEY, facility_id TEXT NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
 source TEXT NOT NULL, source_id TEXT NOT NULL, observed_date TEXT,
 observation TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'identity_pending'
 CHECK(status IN ('identity_pending','reviewed','rejected')),
 source_url TEXT NOT NULL, source_sha256 TEXT NOT NULL, retrieved_at TEXT NOT NULL,
 reviewer TEXT, reviewed_at TEXT, review_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_reg_observations_site ON regulatory_observations(facility_id,status);
CREATE TABLE IF NOT EXISTS raw_snapshots (
 id TEXT PRIMARY KEY, source TEXT NOT NULL, facility_id TEXT,
 url TEXT NOT NULL, retrieved_at TEXT NOT NULL, response_json TEXT NOT NULL,
 notes TEXT, FOREIGN KEY(facility_id) REFERENCES facilities(id)
);
'''


def get_db_path() -> Path:
    return Path(os.environ.get('FACILITY_RISK_DB', str(DEFAULT_DB))).expanduser()


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    target = Path(path) if path else get_db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA journal_mode=WAL')
    return conn


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    from .intelligence import initialize_intelligence
    initialize_intelligence(conn)
    from .source_extensions import initialize_extensions
    initialize_extensions(conn)
    from .site_workspace import initialize_workspace
    initialize_workspace(conn)
    from .research import initialize_research
    initialize_research(conn)
    from .legacy_audit import initialize_legacy
    initialize_legacy(conn)
    from .approval import initialize_approvals
    initialize_approvals(conn)
    from .coverage_review import initialize_insurance_reviews
    initialize_insurance_reviews(conn)
    from .physical_assets import initialize_assets
    initialize_assets(conn)
    from .bi_scenarios import initialize_interruption
    initialize_interruption(conn)
    conn.commit()


def items(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def one(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> dict | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    return conn.execute(sql, params).fetchone()[0]


def source_breakdown(conn: sqlite3.Connection, facility_id: str | None = None) -> list[dict]:
    clause = 'WHERE facility_id=?' if facility_id else ''
    params = (facility_id,) if facility_id else ()
    return items(conn, f'''SELECT source, COUNT(*) AS records,
       COUNT(DISTINCT program) AS programs,
       SUM(CASE WHEN source_url LIKE 'http%' THEN 1 ELSE 0 END) AS linked
       FROM evidence {clause} GROUP BY source ORDER BY records DESC''', params)


def quality_report(conn: sqlite3.Connection) -> dict:
    facilities = scalar(conn, 'SELECT COUNT(*) FROM facilities')
    evidences = scalar(conn, 'SELECT COUNT(*) FROM evidence')
    findings = scalar(conn, 'SELECT COUNT(*) FROM sec_findings')
    public = scalar(conn, 'SELECT COUNT(*) FROM public_evidence')
    with_coordinates = scalar(conn, 'SELECT COUNT(*) FROM facilities WHERE latitude IS NOT NULL AND longitude IS NOT NULL')
    with_fei = scalar(conn, 'SELECT COUNT(*) FROM facilities WHERE fei IS NOT NULL')
    with_url = scalar(conn, "SELECT COUNT(*) FROM evidence WHERE source_url LIKE 'https://%' OR source_url LIKE 'http://%'")
    unmatched_sec = scalar(conn, 'SELECT COUNT(*) FROM sec_findings WHERE facility_id IS NULL')
    dated_publication = scalar(conn, 'SELECT COUNT(*) FROM evidence WHERE availability_date IS NOT NULL')
    # The raw date field mixes record, status, expiration and event dates.
    # Flag future ISO dates for semantic review, not as necessarily incorrect.
    future_dated = scalar(conn, "SELECT COUNT(*) FROM evidence WHERE date_raw GLOB '[12][0-9][0-9][0-9]-[01][0-9]-[0-3][0-9]' AND date(date_raw)>date('now')")
    failures = []
    for r in items(conn, "SELECT id,latitude,longitude FROM facilities WHERE latitude IS NOT NULL OR longitude IS NOT NULL"):
        lat,lon = r['latitude'],r['longitude']
        if lat is None or lon is None or not(-90<=lat<=90 and -180<=lon<=180):
            failures.append(f"Invalid geographic point: {r['id']}")
    dangling = scalar(conn, 'SELECT COUNT(*) FROM evidence e LEFT JOIN facilities f ON f.id=e.facility_id WHERE f.id IS NULL')
    if dangling:
        failures.append(f'{dangling} orphan evidence rows')
    # A changed coordinate invalidates an old review; do not silently use a
    # historical approval to permit property-level hazards at a new location.
    stale_site_reviews=scalar(conn,'''SELECT COUNT(*) FROM location_reviews l
      JOIN facilities f ON f.id=l.facility_id
      WHERE l.precision IN ('site_verified','property_polygon')
        AND (l.reviewed_latitude IS NULL OR l.reviewed_longitude IS NULL
             OR f.latitude IS NULL OR f.longitude IS NULL
             OR l.reviewed_latitude<>f.latitude OR l.reviewed_longitude<>f.longitude)''')
    total_hazards=scalar(conn,'SELECT COUNT(*) FROM hazard_assessments')
    current_hazards=scalar(conn,'''SELECT COUNT(*) FROM hazard_assessments h
      JOIN facilities f ON f.id=h.facility_id
      JOIN location_reviews l ON l.facility_id=f.id
      WHERE l.precision IN ('site_verified','property_polygon')
        AND h.reviewed_latitude=f.latitude AND h.reviewed_longitude=f.longitude
        AND l.reviewed_latitude=f.latitude AND l.reviewed_longitude=f.longitude
        AND h.location_reviewed_at=l.verified_at''')
    stale_hazards=total_hazards-current_hazards
    duplicates = items(conn, 'SELECT fei,COUNT(*) AS n FROM facilities WHERE fei IS NOT NULL GROUP BY fei HAVING n>1')
    for r in duplicates:
        failures.append(f"Duplicated FEI: {r['fei']}")
    import_sources = items(conn,'''SELECT source_key,valid_rows,imported_at
             FROM external_registry_imports ORDER BY source_key''')
    tracked_without_evidence=scalar(conn,'''SELECT COUNT(*) FROM facilities f
             WHERE NOT EXISTS (SELECT 1 FROM evidence e WHERE e.facility_id=f.id)''')
    external_entries=scalar(conn,'SELECT COUNT(*) FROM external_registry_entities')
    from .legacy_audit import audit_legacy_attribution
    unsafe=audit_legacy_attribution(conn)
    quarantined=scalar(conn,'SELECT COUNT(*) FROM legacy_evidence_quarantine')
    return dict(legacy_attribution_pending=unsafe['flagged'],
                legacy_attribution_reasons=unsafe['by_reason'],
                legacy_evidence_quarantined=quarantined,
                stale_or_legacy_coordinate_reviews=stale_site_reviews,
                current_hazard_screenings=current_hazards,
                stale_or_legacy_hazard_screenings=stale_hazards,
                external_registry_entities=external_entries,
                external_source_imports=import_sources,
                research_sites_without_evidence=tracked_without_evidence,
                facilities=facilities, evidence=evidences, sec_findings=findings,
                public_references=public, geo_matched=with_coordinates, with_fei=with_fei,
                evidence_with_url=with_url, unmatched_sec_findings=unmatched_sec,
                evidence_with_verified_publication_date=dated_publication,
                future_dated_evidence=future_dated,
                sources=scalar(conn, 'SELECT COUNT(*) FROM sources'),
                snapshots=scalar(conn, 'SELECT COUNT(*) FROM raw_snapshots'),
                integrity_failures=failures, important_caveats=[
                    'Workbook records were researched by the analyst, not independently refetched during import.',
                    'Recorded event dates cannot substitute for pre-event public-availability dates.',
                    'SEC findings are disclosures, not unique loss events; forecasts and recoveries are not additive.',
                    'Geographic proximity establishes regional exposure, not damage to an insured location.',
                    'A missing enforcement or incident record is not evidence of a safe facility.',
                    'Raw workbook dates can describe permit validity or future expiration, not necessarily an incident.'
                ])


def add_run(conn, run_id: str, source: str, when: str, sha: str | None = None):
    conn.execute('INSERT INTO ingestion_runs(id,source,started_at,status,source_sha256) VALUES(?,?,?,?,?)',
                 (run_id,source,when,'running',sha))
    conn.commit()


def complete_run(conn, run_id: str, finished: str, count: int, details: dict, status: str = 'completed'):
    conn.execute('UPDATE ingestion_runs SET status=?, finished_at=?,imported_count=?,details_json=? WHERE id=?',
                 (status,finished,count,json.dumps(details,default=str),run_id))
    conn.commit()
