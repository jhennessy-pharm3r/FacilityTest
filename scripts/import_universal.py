"""Import all-industry facility identities from authorized official CSV / GeoJSONSeq exports.

No network access or automatic physical-site deduplication. Input files must be
downloaded via the source publisher's authorized distribution channel. This
importer never publishes full third-party records to GitHub Pages.
"""
from __future__ import annotations
import argparse
import csv
import gzip
import json
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from facilityrisk.db import connect, initialize
from facilityrisk.universal_registry import import_records, import_published_catalog

def open_text(path):
    return gzip.open(path,'rt',encoding='utf-8-sig',errors='replace',newline='') if str(path).endswith('.gz') else open(path,'r',encoding='utf-8-sig',errors='replace',newline='')

def csv_rows(path, fields):
    with open_text(path) as f:
        reader=csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError('CSV header missing')
        if fields.get('id') not in reader.fieldnames or fields.get('name') not in reader.fieldnames:
            raise ValueError('Mapping requires real source ID and name columns')
        for r in reader:
            yield {dest: r.get(original,'') for dest,original in fields.items() if original}

def geojsonseq_rows(path):
    """Supports GeoJSON lines exports of point *places*, not anonymous polygons."""
    with open_text(path) as f:
        for line in f:
            line=line.lstrip('\x1e').strip()
            if not line:continue
            obj=json.loads(line)
            props=obj.get('properties') or {}
            names=props.get('names') or {}
            primary=names.get('primary') or props.get('name') or ''
            cats=props.get('categories') or {}
            cat=cats.get('primary') if isinstance(cats,dict) else ''
            geom=obj.get('geometry') or {}
            loc=geom.get('coordinates') if geom.get('type')=='Point' else []
            addresses=props.get('addresses') or []
            addr=addresses[0] if isinstance(addresses,list) and addresses else {}
            if not isinstance(addr,dict):addr={}
            yield {'source_identifier':props.get('id') or obj.get('id'),
                   'name':primary,'company':primary,
                   'country':addr.get('country',''),
                   'state':addr.get('region',''),
                   'city':addr.get('locality',''),
                   'address':addr.get('freeform',''),
                   'industry':cat or 'Unclassified place',
                   'category':cat,'latitude':loc[1] if len(loc)>1 else None,
                   'longitude':loc[0] if len(loc)>1 else None,
                   'source_confidence':props.get('confidence')}

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('path')
    p.add_argument('--format',required=True,choices=['csv','geojsonseq','published-catalog'])
    p.add_argument('--source',default='')
    p.add_argument('--source-url',default='')
    p.add_argument('--vintage',default='')
    p.add_argument('--field',action='append',default=[],help='Canonical field=Original CSV column')
    args=p.parse_args(argv)
    conn=connect()
    initialize(conn)
    try:
        if args.format=='published-catalog':
            out=import_published_catalog(conn,args.path)
        else:
            if not args.source or not args.source_url:
                p.error('Source key and source URL are required')
            fields={}
            for m in args.field:
                a,sep,b=m.partition('=')
                if not sep or a not in {'source_identifier','name','company','address',
                    'city','state','country','industry','category','activities',
                    'latitude','longitude','source_confidence'}:
                    p.error('Invalid --field mapping '+m)
                fields[a]=b
            if args.format=='csv':
                if 'source_identifier' not in fields or 'name' not in fields:
                    p.error('CSV requires --field source_identifier=ID and --field name=NAME')
                records=csv_rows(args.path,fields)
            else:
                records=geojsonseq_rows(args.path)
            out=import_records(conn,args.source,records,args.source_url,
                               vintage=args.vintage)
        print(json.dumps(out,indent=2))
    finally:
        conn.close()

if __name__=='__main__':main()
