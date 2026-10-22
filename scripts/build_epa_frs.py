#!/usr/bin/env python3
"""Stage official EPA FRS national single CSV into bounded, provenance-rich source data.

Run on GitHub Actions or locally. The resulting .csv.gz is a *source-identity
cohort*, not a reconciled inventory of verified properties. It is not published
on GitHub Pages. The exact source ZIP and normalized manifest have checksums.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
import zipfile

OFFICIAL_URL="https://ordsext.epa.gov/FLA/www3/state_files/national_single.zip"
PUBLISHER="https://www.epa.gov/frs/epa-frs-facilities-state-single-file-csv-download"
FIELDS=('source_identifier','name','company','address','city','state','country',
        'industry','category','activities','latitude','longitude','source_confidence')
MAX_ZIP_BYTES=1_500_000_000

def official_download(out):
    h=hashlib.sha256()
    size=0
    with urlopen(Request(OFFICIAL_URL,headers={'User-Agent':'Pharm3r-Facility-Risk/0.7 (GitHub FRS source evaluation)',
                   'Accept':'application/zip,application/octet-stream,*/*'}),timeout=180) as response:
        target=urlsplit(response.geturl())
        if target.scheme!='https' or not target.hostname.endswith('.epa.gov'):
            raise ValueError('The official FRS download redirected outside a verified EPA.gov HTTPS host')
        with open(out,'wb') as writer:
            while True:
                block=response.read(1024*1024)
                if not block:break
                size+=len(block)
                if size>MAX_ZIP_BYTES:raise ValueError('Unusually large EPA ZIP exceeds 1.5 GB cap')
                writer.write(block)
                h.update(block)
    if not zipfile.is_zipfile(out):raise ValueError('EPA response was not a ZIP archive')
    return {'sha256':h.hexdigest(),'bytes':size,'download_url':OFFICIAL_URL}

def get_field(raw,*aliases):
    for x in aliases:
        if x in raw and str(raw[x] or '').strip():
            return str(raw[x]).strip()
    return ''

def normalize_row(raw):
    reg=get_field(raw,'REGISTRY_ID','REGISTRYID','FRS_ID')
    name=get_field(raw,'PRIMARY_NAME','FAC_NAME','FACILITY_NAME','FACILITY_SITE_NAME')
    if not reg or not name:return None
    country=get_field(raw,'COUNTRY_ISO_3166_1_ALPHA_2','COUNTRY_CODE','COUNTRY_NAME').upper()
    if country in ('UNITED STATES','UNITED STATES OF AMERICA','USA'):country='US'
    # EPA may omit country; the national cohort is overwhelmingly U.S. but
    # absence in the record is reported as unknown rather than guessed.
    if len(country)!=2:country=''
    industry=get_field(raw,'NAICS_DESCRIPTION','NAICS_PRIMARY_DESCRIPTION',
                        'PRIMARY_NAICS_DESCRIPTION','NAICS_CODE','NAICS_CODES') or 'Unclassified'
    return {
        'source_identifier':reg,
        'name':name,
        'company':get_field(raw,'ORGANIZATION_NAME','OWNER_NAME'),
        'address':get_field(raw,'LOCATION_ADDRESS','FAC_STREET','ADDRESS'),
        'city':get_field(raw,'CITY_NAME','FAC_CITY','CITY'),
        'state':get_field(raw,'STATE_CODE','FAC_STATE','STATE'),
        'country':country,
        'industry':industry[:120],
        'category':'EPA FRS source identity',
        'activities':'',
        'latitude':get_field(raw,'LATITUDE83','REP_LATITUDE83','LATITUDE_MEASURE','LATITUDE'),
        'longitude':get_field(raw,'LONGITUDE83','REP_LONGITUDE83','LONGITUDE_MEASURE','LONGITUDE'),
        'source_confidence':''}

def scan_zip(path):
    with zipfile.ZipFile(path) as z:
        candidates=[m for m in z.infolist()
                    if m.filename.lower().endswith('.csv') and not m.is_dir()]
        if not candidates:
            raise ValueError('No CSV member in official national FRS ZIP')
        # The national single file is normally the largest CSV member.
        selected=max(candidates,key=lambda f:f.file_size)
        if selected.file_size>7_000_000_000:
            raise ValueError('Unexpectedly large uncompressed source')
        with z.open(selected) as binary:
            # Accept UTF-8 with replacement when upstream old encodings contain
            # invalid byte sequences; preserve original source ZIP for audit.
            with io.TextIOWrapper(binary,encoding='utf-8-sig',errors='replace',newline='') as text:
                reader=csv.DictReader(text)
                names=[str(v or '').strip().lstrip('\ufeff').upper() for v in (reader.fieldnames or [])]
                if not {'REGISTRY_ID','PRIMARY_NAME'}.issubset(set(names)):
                    raise ValueError('Official FRS national CSV schema changed: '+repr(names[:50]))
                for row in reader:
                    yield {str(k or '').strip().upper():v for k,v in row.items()}

def build(archive,output,max_rows=0,min_rows=0):
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    counters={'read_rows':0,'valid_records':0,'rejected_rows':0}
    hash_out=hashlib.sha256()
    tmp=output.with_name(output.name+'.tmp')
    try:
        with open(tmp,'wb') as raw:
            with gzip.GzipFile(fileobj=raw,mode='wb',compresslevel=6,mtime=0) as z:
                with io.TextIOWrapper(z,encoding='utf-8',newline='') as text:
                    writer=csv.DictWriter(text,fieldnames=FIELDS,lineterminator='\n')
                    writer.writeheader()
                    for row in scan_zip(archive):
                        counters['read_rows']+=1
                        normal=normalize_row(row)
                        if not normal:
                            counters['rejected_rows']+=1
                            continue
                        counters['valid_records']+=1
                        writer.writerow(normal)
                        if max_rows and counters['read_rows']>=max_rows:break
        if counters['valid_records']<min_rows:
            raise ValueError('FRS cohort below validation floor: '+str(counters['valid_records']))
        tmp.replace(output)
        with open(output,'rb') as f:
            for part in iter(lambda:f.read(1024*1024),b''):
                hash_out.update(part)
        return dict(counters,output=str(output),output_bytes=output.stat().st_size,
                    output_sha256=hash_out.hexdigest(),complete_source=not bool(max_rows),
                    publisher=PUBLISHER)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--official-zip',default='',help='Optional already-downloaded official ZIP')
    p.add_argument('--output',default='data/epa-frs-national.csv.gz')
    p.add_argument('--manifest',default='data/epa-frs-national-manifest.json')
    p.add_argument('--max-rows',type=int,default=0,help='Fixture/sample mode; never label as complete')
    p.add_argument('--min-rows',type=int,default=100_000)
    args=p.parse_args(argv)
    if args.max_rows<0 or args.min_rows<0:p.error('Rows must be nonnegative')
    temp=None
    if args.official_zip:
        archive=Path(args.official_zip)
        if not archive.is_file():p.error('Official ZIP not found')
        sha=hashlib.sha256()
        with open(archive,'rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):sha.update(block)
        digest=sha.hexdigest()
        source={'sha256':digest,'bytes':archive.stat().st_size,'download_url':'operator_supplied_official_zip'}
    else:
        temp=tempfile.NamedTemporaryFile(suffix='.zip',delete=False)
        temp.close()
        archive=Path(temp.name)
        source=official_download(archive)
    try:
        result=build(archive,args.output,max_rows=args.max_rows,min_rows=args.min_rows)
        manifest={**source,**result,'generated_at':datetime.now(timezone.utc).isoformat(timespec='seconds')}
        path=Path(args.manifest);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(manifest,indent=2,sort_keys=True),encoding='utf-8')
        print(json.dumps(manifest,indent=2))
    finally:
        if temp is not None:archive.unlink(missing_ok=True)

if __name__=='__main__':main()
