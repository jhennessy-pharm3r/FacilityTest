"""Source-only EPA database installation must never overwrite insured research."""
import json
import sqlite3

import pytest

from facilityrisk.db import connect,initialize
from facilityrisk.universal_registry import import_records
from scripts.install_frs_source_index import validate_source_only_index,install_new_index


def source_fixture(tmp_path):
    source=tmp_path/'epafrs-source.sqlite'
    conn=connect(source)
    initialize(conn)
    import_records(conn,'EPA_FRS',[
        {'id':'110000001234','name':'Mountain Warehouse','country':'US','industry':'493110'},
        {'id':'110000001235','name':'Municipal Hospital','country':'US','industry':'622110'},
    ],'https://www.epa.gov/frs',vintage='2026-10-23')
    conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    conn.close()
    qa=tmp_path/'full-frs-index-qa.json'
    qa.write_text(json.dumps({
        'source':'EPA FRS public reporting identities',
        'unique_source_identifiers':2,
        'site_candidates':2,
        'database_bytes':source.stat().st_size,
        'sqlite_quick_check':'ok',
        'source_archive_sha256':'a'*64,
        'normalized_source_sha256':'b'*64,
        'source_vintage':'2026-10-23',
    }),encoding='utf-8')
    return source,qa


def test_install_new_public_source_only_index_does_not_overwrite(tmp_path):
    source,qa=source_fixture(tmp_path)
    validated=validate_source_only_index(source,qa,minimum_identities=2)
    assert validated['source_identities']==2
    assert validated['checked_sqlite_integrity'] is True
    target=tmp_path/'separate-source-only.sqlite'
    installed=install_new_index(source,qa,target,minimum_identities=2)
    assert installed['existing_database_overwritten'] is False
    assert installed['exclusively_created'] is True
    assert len(installed['copied_sqlite_sha256'])==64
    assert target.is_file()
    conn=sqlite3.connect('file:'+target.resolve().as_posix()+'?mode=ro',uri=True)
    assert conn.execute('SELECT COUNT(*) FROM universal_source_records').fetchone()[0]==2
    conn.close()
    previous_content=target.read_bytes()
    with pytest.raises(FileExistsError,match='Destination exists'):
        install_new_index(source,qa,target,minimum_identities=2)
    assert target.read_bytes()==previous_content


def test_rejects_qa_count_mismatch_and_private_rows(tmp_path):
    source,qa=source_fixture(tmp_path)
    payload=json.loads(qa.read_text(encoding='utf-8'))
    payload['unique_source_identifiers']=5
    qa.write_text(json.dumps(payload),encoding='utf-8')
    with pytest.raises(ValueError,match='missing or mismatched'):
        validate_source_only_index(source,qa,minimum_identities=2)
    payload['unique_source_identifiers']=2
    conn=sqlite3.connect(source)
    conn.execute("""INSERT INTO facilities
      (id,name,origin,last_imported) VALUES
      ('private-client','Insured warehouse','fixture','2026-10-23')""")
    conn.commit()
    conn.close()
    payload['database_bytes']=source.stat().st_size
    qa.write_text(json.dumps(payload),encoding='utf-8')
    with pytest.raises(ValueError,match='private or reviewed research'):
        validate_source_only_index(source,qa,minimum_identities=2)


def test_rejects_bad_source_or_an_existing_target_before_mutation(tmp_path):
    source,qa=source_fixture(tmp_path)
    payload=json.loads(qa.read_text(encoding='utf-8'))
    payload.pop('source_archive_sha256')
    qa.write_text(json.dumps(payload),encoding='utf-8')
    with pytest.raises(ValueError,match='source and normalized artifact hashes'):
        validate_source_only_index(source,qa,minimum_identities=2)
    target=tmp_path/'already-has-user-data.sqlite'
    target.write_bytes(b'IMPORTANT CLIENT DATA DO NOT MODIFY')
    with pytest.raises(FileExistsError,match='Destination exists'):
        install_new_index(source,qa,target,minimum_identities=2)
    assert target.read_bytes()==b'IMPORTANT CLIENT DATA DO NOT MODIFY'
