"""Legacy source-level evidence must be audited before retrospective site use."""
import pytest
from facilityrisk.db import connect,initialize,quality_report
from facilityrisk.legacy_audit import audit_legacy_attribution

@pytest.fixture
def db(tmp_path):
    c=connect(tmp_path/'legacy.sqlite')
    initialize(c)
    c.execute("""INSERT INTO facilities
      (id,name,company,country,fei,latitude,longitude,origin,last_imported)
      VALUES ('a','Demo Site','Demo','US','123456789',40,-75,'fixture','2026-10-21')""")
    for eid,source,ref in [('noaa-1','NOAA (CSV)','storm-id'),
                           ('fda-1','FDA inspections (CSV)','123456789'),
                           ('usgs-1','USGS (live)','quake-id'),
                           ('baseline','EPA','permit-id')]:
        c.execute("""INSERT INTO evidence(id,facility_id,source,record_ref,record_type,
                  finding,risk_domain,origin,last_imported,retrieval_at)
                  VALUES(?,?,?,?,?,?,?,?,?,?)""",
                  (eid,'a',source,ref,'Source record','Original data preserved',
                   'Environmental compliance','fixture','2026-10-21','2026-10-21'))
    c.commit()
    yield c
    c.close()

def test_legacy_attribution_dry_run_does_not_mutate_evidence(db):
    r=audit_legacy_attribution(db)
    assert r['mode']=='dry_run'
    assert r['flagged']==3
    assert r['by_reason']['legacy_noaa_proximity_in_accepted_evidence']==1
    assert r['by_reason']['inspection_import_preceded_verified_fei_link']==1
    assert r['by_reason']['geographic_evidence_without_current_reviewed_point']==1
    assert db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]==4
    assert db.execute("SELECT COUNT(*) FROM legacy_evidence_quarantine").fetchone()[0]==0
    assert quality_report(db)['legacy_attribution_pending']==3

def test_quarantine_preserves_original_records_and_is_idempotent(db):
    with pytest.raises(ValueError,match='reviewer'):
        audit_legacy_attribution(db,apply=True,actor='')
    result=audit_legacy_attribution(db,apply=True,actor='QA analyst')
    assert result['quarantined']==3
    assert db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]==1
    assert db.execute("SELECT source FROM evidence").fetchone()[0]=='EPA'
    original=db.execute("SELECT * FROM legacy_evidence_quarantine WHERE id='noaa-1'").fetchone()
    assert original['source']=='NOAA (CSV)'
    assert 'Original data preserved' in original['original_record_json']
    assert audit_legacy_attribution(db,apply=True,actor='QA analyst')['quarantined']==0
    assert quality_report(db)['legacy_evidence_quarantined']==3
    assert db.execute("SELECT COUNT(*) FROM audit_events WHERE action='legacy_evidence_quarantined'").fetchone()[0]>=1

def test_verified_fei_protects_legitimate_inspection_from_audit(db):
    from facilityrisk.intelligence import verify_fei
    verify_fei(db,'a','Reviewer','https://www.fda.gov/',
               'Verified facility FEI against official source')
    db.execute("UPDATE evidence SET last_imported='9999-01-01' WHERE id='fda-1'")
    db.commit()
    rows=audit_legacy_attribution(db)
    assert rows['flagged']==2
    assert 'fda-1' not in rows['sample_evidence_ids']
