"""Review legacy evidence created before strict coordinate/FEI attribution gates.

Dry-run is the default. Quarantine is opt-in, reversible from original JSON,
and never attempts to change analyst-curated workbook evidence. It is not a
mechanism to relabel proximity or regulatory source records as insured losses.
"""
from __future__ import annotations

from collections import Counter
import json
import uuid

from .ingest import utcnow
from .intelligence import audit,is_reviewed_site_coordinate

SOURCE_NOAA='NOAA (CSV)'
SOURCE_INSPECTION='FDA inspections (CSV)'
LOCATION_SOURCES=('USGS (live)','WRI Aqueduct (live)')

SCHEMA="""
CREATE TABLE IF NOT EXISTS legacy_evidence_quarantine (
 id TEXT PRIMARY KEY,
 facility_id TEXT NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
 source TEXT NOT NULL,reason TEXT NOT NULL,
 original_record_json TEXT NOT NULL,
 quarantined_at TEXT NOT NULL,reviewed_by TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_legacy_quarantine_site ON legacy_evidence_quarantine(facility_id,source);
"""

def initialize_legacy(conn):
    conn.executescript(SCHEMA)


def _flagged(conn):
    from .db import items
    rows=items(conn,"""SELECT * FROM evidence WHERE source IN
       ('NOAA (CSV)','FDA inspections (CSV)','USGS (live)','WRI Aqueduct (live)')
       ORDER BY facility_id,source,id""")
    sites={r['id']:dict(r) for r in conn.execute('SELECT * FROM facilities')}
    reviews={r['facility_id']:dict(r) for r in conn.execute('SELECT * FROM location_reviews')}
    verified={(r['facility_id'],r['identifier']):r['reviewed_at']
              for r in conn.execute("""SELECT facility_id,identifier,reviewed_at
                    FROM identity_links
                    WHERE namespace='FDA_FEI' AND status='verified'""")}
    issues=[]
    for row in rows:
        reason=None
        if row['source']==SOURCE_NOAA:
            reason='legacy_noaa_proximity_in_accepted_evidence'
        elif row['source']==SOURCE_INSPECTION:
            review_at=verified.get((row['facility_id'],str(row['record_ref'] or '').strip()))
            if not review_at or (row['last_imported'] and review_at>row['last_imported']):
                reason='inspection_import_preceded_verified_fei_link'
        else:
            point=sites.get(row['facility_id'])
            review=reviews.get(row['facility_id'])
            if not is_reviewed_site_coordinate(point,review):
                reason='geographic_evidence_without_current_reviewed_point'
            elif (not review.get('verified_at') or not row['retrieval_at'] or
                  row['retrieval_at']<review['verified_at']):
                reason='geographic_evidence_precedes_point_review'
        if reason:
            issues.append((row,reason))
    return issues


def audit_legacy_attribution(conn,*,apply=False,actor=''):
    initialize_legacy(conn)
    issues=_flagged(conn)
    reasons=dict(sorted(Counter(reason for _,reason in issues).items()))
    if not apply:
        return {'mode':'dry_run','flagged':len(issues),'by_reason':reasons,
                'sample_evidence_ids':[row['id'] for row,_ in issues[:30]],
                'quarantine_applied':False,
                'caveat':'No evidence changed. Reviewed original source correspondence is required.'}
    if not actor or len(actor.strip())<2:
        raise ValueError('Named authenticated reviewer required to quarantine legacy evidence')
    removed=0
    with conn:
        for record,reason in issues:
            stored=conn.execute("""INSERT OR IGNORE INTO legacy_evidence_quarantine
              (id,facility_id,source,reason,original_record_json,quarantined_at,reviewed_by)
              VALUES(?,?,?,?,?,?,?)""",
              (record['id'],record['facility_id'],record['source'],reason,
               json.dumps(record,ensure_ascii=False,sort_keys=True,default=str),utcnow(),actor))
            if stored.rowcount:
                conn.execute('DELETE FROM evidence WHERE id=?',(record['id'],))
                removed+=1
        audit(conn,'legacy_evidence_quarantined','facility_evidence',actor,
              {'records':removed,'reasons':reasons})
    return {'mode':'apply','flagged':len(issues),'quarantined':removed,
            'by_reason':reasons,'quarantine_applied':True,
            'caveat':'Original evidence JSON preserved in private quarantine table; no loss conclusion.'}
