"""Benchmark real indexed source-identity search without exporting private site data.

Runs against the disposable, public-source-only EPA FRS SQLite produced by
validate-frs-index.yml. Does not invent latency measurements or risk ratings.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
from pathlib import Path
try:
    import resource
except ImportError:  # Windows private operator workstation
    resource=None
import sqlite3
from statistics import median
import time
from urllib.parse import quote

import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from facilityrisk.universal_registry import search


def readonly_database(db_path):
    uri='file:'+quote(str(Path(db_path).resolve()),safe='/')+'?mode=ro'
    conn=sqlite3.connect(uri,uri=True,timeout=60)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA query_only=ON')
    conn.execute('PRAGMA busy_timeout=60000')
    return conn


def _percentile(values,percentage):
    ordered=sorted(values)
    return round(ordered[max(0,math.ceil(len(ordered)*percentage)-1)],2)


def benchmark(db_path,repeats=3,concurrency=4,*,cases=None):
    db_path=Path(db_path)
    if not db_path.is_file():raise FileNotFoundError(db_path)
    if not (1<=int(repeats)<=20 and 1<=int(concurrency)<=8):
        raise ValueError('Bounded repeats (1-20) and concurrency (1-8) required')
    with closing(readonly_database(db_path)) as conn:
        total_sites=conn.execute('SELECT COUNT(*) FROM universal_sites').fetchone()[0]
        total_identities=conn.execute('SELECT COUNT(*) FROM universal_source_records').fetchone()[0]
        candidate=conn.execute("""SELECT source_identifier FROM universal_source_records
              WHERE source_key='EPA_FRS' AND length(source_identifier)>=6 LIMIT 1""").fetchone()
        if not candidate:raise ValueError('No real EPA FRS identifier available for indexed lookup test')
        prefix=candidate['source_identifier'][:8]
    if cases is None:
        cases=[
           ('name_warehouse',{'q':'warehouse','limit':25}),
           ('name_hospital',{'q':'hospital','limit':25}),
           ('identifier_prefix',{'q':prefix,'source':'EPA_FRS','limit':25}),
           ('country_filter',{'q':'water','country':'US','limit':25}),
           ('deep_page',{'q':'warehouse','offset':250,'limit':50}),
        ]
    output=[]
    def query(case):
        label,opts=case
        start=time.perf_counter()
        with closing(readonly_database(db_path)) as c:
            result=search(c,**opts)
        return label,round((time.perf_counter()-start)*1000,2),result['total'],len(result['items'])
    # Warm each lookup. These timings are excluded from the reported cold/warm
    # measurements; the actual source file may still be in the kernel cache.
    for case in cases:
        query(case)
    for case in cases:
        observations=[query(case) for _ in range(repeats)]
        if case[0]=='identifier_prefix' and not observations[0][2]:
            raise AssertionError('Indexed exact source identifier failed to resolve')
        if case[0]=='identifier_prefix' and max(x[1] for x in observations)>10_000:
            raise AssertionError('National FRS source identifier lookup exceeds 10-second acceptance gate; investigate the query plan')
        output.append({'case':case[0],'params':case[1],
           'matching_source_site_candidates':observations[0][2],
           'returned':observations[0][3],
           'p50_ms':round(median(x[1] for x in observations),2),
           'p95_ms':_percentile([x[1] for x in observations],.95),
           'samples_ms':[x[1] for x in observations]})
    parallel_samples=[]
    if concurrency>1:
        # Per-thread SQLite read-only connection. Never share connections
        # between workers, which would misrepresent connection safety.
        tasks=[cases[i%len(cases)] for i in range(max(concurrency, len(cases)))]
        started=time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            parallel_samples=list(pool.map(query,tasks))
        parallel_elapsed=time.perf_counter()-started
    else:
        parallel_elapsed=0
    rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss if resource else None
    return {'benchmark':'source_identity_sqlite_fts5',
        'data_scope':'official public EPA FRS identities only; not verified properties or client records',
        'database_path_hint':db_path.name,
        'database_bytes':db_path.stat().st_size,
        'source_identities':total_identities,'site_candidates':total_sites,
        'repeats_per_query':repeats,'concurrent_workers':concurrency,
        'query_cases':output,
        'parallel':{'requests':len(parallel_samples),
           'wall_seconds':round(parallel_elapsed,3),
           'p50_ms':round(median(x[1] for x in parallel_samples),2) if parallel_samples else None,
           'p95_ms':_percentile([x[1] for x in parallel_samples],.95) if parallel_samples else None},
        'process_peak_rss_kib':rss_kib,
        'caveats':['GitHub Actions shared runner, not the production server',
          'Results depend on filesystem cache and runner load',
          'No authenticated concurrent-client, network latency or tenant isolation benchmark',
          'Every result is a source observation rather than a verified insured site']}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('database')
    parser.add_argument('--out',default='data/frs-search-benchmark.json')
    parser.add_argument('--repeats',type=int,default=3)
    parser.add_argument('--concurrency',type=int,default=4)
    opts=parser.parse_args()
    report=benchmark(opts.database,opts.repeats,opts.concurrency)
    destination=Path(opts.out)
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)

if __name__=='__main__':main()
