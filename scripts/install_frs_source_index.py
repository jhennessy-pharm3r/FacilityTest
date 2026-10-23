"""Safely install a validated public-source EPA FRS index to a NEW private volume.

Never overwrite insured/client workspace SQLite. The source index is not
a verified physical-property inventory or a public Pages search database.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile


PRIVATE_TABLES=('facilities','evidence','sec_findings','raw_snapshots','audit_events',
    'insurance_policies','insurance_terms','facility_assets','review_approvals',
    'physical_asset_reviews','facility_asset_reviews')


def validate_source_only_index(database,qa_file,minimum_identities=5_000_000):
    db=Path(database)
    qa_path=Path(qa_file)
    if not db.is_file() or not qa_path.is_file():
        raise ValueError('Required indexed SQLite and its QA JSON must both exist')
    report=json.loads(qa_path.read_text(encoding='utf-8'))
    if not isinstance(report,dict):raise ValueError('Invalid index QA manifest')
    if report.get('sqlite_quick_check')!='ok':
        raise ValueError('Original source-index integrity gate did not pass')
    if report.get('source')!='EPA FRS public reporting identities':
        raise ValueError('Unexpected non-source-only index manifest')
    if not report.get('source_archive_sha256') or not report.get('normalized_source_sha256'):
        raise ValueError('Exact official source and normalized artifact hashes are required')
    if db.stat().st_size!=report.get('database_bytes'):
        raise ValueError('SQLite byte size differs from official validation report')
    uri='file:'+db.resolve().as_posix()+'?mode=ro'
    try:conn=sqlite3.connect(uri,uri=True)
    except sqlite3.Error as exc:raise ValueError('Cannot open read-only index') from exc
    try:
        count=conn.execute('SELECT COUNT(*) FROM universal_source_records').fetchone()[0]
        sites=conn.execute('SELECT COUNT(*) FROM universal_sites').fetchone()[0]
        source_keys={row[0] for row in conn.execute(
            'SELECT DISTINCT source_key FROM universal_source_records')}
        if count<minimum_identities or count!=report.get('unique_source_identifiers'):
            raise ValueError('Indexed source identifier total is missing or mismatched')
        if sites!=report.get('site_candidates'):
            raise ValueError('Indexed source-site candidate total does not match QA')
        if source_keys!={'EPA_FRS'}:
            raise ValueError('Index contains non-EPA source identities; manual review required')
        for table in PRIVATE_TABLES:
            present=conn.execute('SELECT 1 FROM sqlite_master WHERE type="table" AND name=?',
                                 (table,)).fetchone()
            if present and conn.execute('SELECT 1 FROM "'+table+'" LIMIT 1').fetchone():
                raise ValueError('Refusing a database with private or reviewed research table rows: '+table)
        integrity=conn.execute('PRAGMA quick_check').fetchone()[0]
        if integrity!='ok':raise ValueError('Transferred source-only SQLite integrity check failed')
        return {'site_candidates':sites,'source_identities':count,
                'source_key':'EPA_FRS','database_bytes':db.stat().st_size,
                'source_vintage':report.get('source_vintage',''),
                'checked_sqlite_integrity':True,
                'insured_property_verifications':0}
    finally:conn.close()


def install_new_index(database,qa_file,target,*,minimum_identities=5_000_000):
    """Atomic, no-overwrite same-filesystem copy; no live-client DB mutation."""
    db=Path(database).resolve()
    dest=Path(target).resolve()
    if dest.exists():raise FileExistsError('Destination exists; refusing to overwrite any research database')
    if db==dest:raise ValueError('Source and destination must differ')
    report=validate_source_only_index(db,qa_file,minimum_identities)
    if not dest.parent.is_dir():
        raise ValueError('Create and secure the private destination volume first')
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(prefix='.frs-index-staging-',suffix='.sqlite',
             dir=dest.parent,delete=False) as out:
            tmp=Path(out.name)
            digest=hashlib.sha256()
            with db.open('rb') as source:
                for chunk in iter(lambda:source.read(4*1024*1024),b''):
                    digest.update(chunk)
                    out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(tmp,0o600)
        # Hard link is exclusive: unlike os.replace, it never overwrites an
        # existing insured-data volume even if another operator creates it
        # concurrently during the 5.5GB copy.
        os.link(tmp,dest)
    finally:
        if tmp is not None:tmp.unlink(missing_ok=True)
    return {**report,'installed_path':str(dest),
      'copied_sqlite_sha256':digest.hexdigest(),
      'exclusively_created':True,'existing_database_overwritten':False,
      'warning':'Source identities only, not site geocodes, client records, policy coverage or a hosted deployment'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True,help='Validated public-source-only SQLite')
    parser.add_argument('--qa',required=True,help='Matching full-frs-index-qa.json')
    parser.add_argument('--target',required=True,help='New file on private secure data volume; existing file is rejected')
    args=parser.parse_args()
    result=install_new_index(args.source,args.qa,args.target)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
