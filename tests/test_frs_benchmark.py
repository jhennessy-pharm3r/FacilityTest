"""Benchmark checks cannot assume a demo source sample is a real 5M corpus."""
import sqlite3

from facilityrisk.db import connect,initialize
from facilityrisk.universal_registry import import_records
from scripts.benchmark_frs_search import benchmark


def test_readonly_index_benchmark_preserves_identifiers_and_data(tmp_path):
    path=tmp_path/'source.sqlite'
    c=connect(path);initialize(c)
    data=[
        {'id':'110000000001','name':'Bluebird Warehouse','company':'Bluebird Logistics',
         'country':'US','industry':'493110'},
        {'id':'110000000002','name':'Bluebird Hospital','company':'Bluebird Health',
         'country':'US','industry':'622110'},
        {'id':'110000000003','name':'Water Works','company':'Public Utility',
         'country':'US','industry':'221310'},
        {'id':'110000000004','name':'Regional Clinic','company':'Regional Healthcare',
         'country':'CA','industry':'621111'},
    ]
    import_records(c,'EPA_FRS',data,'https://www.epa.gov/frs',vintage='fixture')
    c.close()
    original_size=path.stat().st_size
    result=benchmark(path,repeats=2,concurrency=2)
    assert result['site_candidates']==4
    assert result['source_identities']==4
    assert result['concurrent_workers']==2
    assert len(result['query_cases'])==5
    assert result['parallel']['requests']>=2
    assert all(row['p50_ms']>=0 and row['p95_ms']>=0 for row in result['query_cases'])
    assert next(x for x in result['query_cases'] if x['case']=='identifier_prefix')['matching_source_site_candidates']>=1
    assert path.stat().st_size==original_size, 'Benchmark cannot rewrite indexed database'
    c=sqlite3.connect(path)
    assert c.execute('SELECT COUNT(*) FROM universal_sites').fetchone()[0]==4
    c.close()


def test_benchmark_rejects_empty_db_or_invalid_settings(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        benchmark(tmp_path/'none.db')
    path=tmp_path/'empty.db'
    from facilityrisk.universal_registry import initialize as init_universal
    c=connect(path);initialize(c);init_universal(c);c.close()
    with pytest.raises(ValueError,match='No real EPA FRS identifier'):
        benchmark(path)
    with pytest.raises(ValueError,match='Bounded'):
        benchmark(path,repeats=0)
