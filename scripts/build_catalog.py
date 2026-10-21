#!/usr/bin/env python3
"""Build public, minimal FDA-establishment catalog for GitHub Pages.

Usage: python scripts/build_catalog.py --output web/registry/catalog.json
Fetches every current openFDA DEVICE registration-listing partition. Drug DECRS is
attempted independently; on failure it is *explicitly* marked unavailable.
Does not download or publish any analyst workbook, private records, email,
contact person, US agent, or phone data.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path
import json
import shutil
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import urllib.error
import zipfile

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from facilityrisk.registry_catalog import make_catalog,normalize_device,parse_drug_zip,validate_catalog

META='https://api.fda.gov/download.json'
DECRS='https://www.fda.gov/drugs/drug-approvals-and-databases/drug-establishments-current-registration-site-decrs'
DECRS_DIRECT_ZIP='https://www.accessdata.fda.gov/cder/drls_reg.zip'
HEADERS={'User-Agent':'Pharm3r-FacilityRisk-ResearchCatalog/0.5 (+github.com/jhennessy-pharm3r/FacilityTest)','Accept':'application/json,text/html,*/*'}
MAX_DOWNLOAD=180*1024*1024


def get_bytes(url,limit=15_000_000):
    if urllib.parse.urlparse(url).scheme!='https':raise ValueError('HTTPS required')
    last=None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers=HEADERS),timeout=100) as res:
                data=res.read(limit+1)
                if len(data)>limit:raise ValueError('Response exceeds size limit')
                return data
        except Exception as exc:
            last=exc
            time.sleep(min(5,attempt+1))
    raise RuntimeError(f'{url}: {last}')


def download_zip(url):
    """Fetch official archive, with FDA-only public browser-agent compatibility.

    GitHub-hosted test: accessdata FDA HEAD/GET returned 404 with the catalog
    agent, but 200/206 with a browser-compatible agent and ZIP magic. This is
    a public FDA file, not a credentialed endpoint. The fallback is limited
    to the official accessdata host and rejects invalid/oversized ZIP content.
    """
    p=urllib.parse.urlparse(url)
    if p.scheme!='https':raise ValueError('HTTPS required')
    def open_archive():
        request=urllib.request.Request(url,headers=HEADERS)
        try:
            return urllib.request.urlopen(request,timeout=180)
        except urllib.error.HTTPError as error:
            if (error.code not in (403,404)
                or p.hostname not in ('www.accessdata.fda.gov','accessdata.fda.gov')):
                raise
            print('Official FDA archive returned '+str(error.code)+
                  ' to data-client agent; retrying public browser-compatible agent',flush=True)
            browser_headers=dict(HEADERS)
            browser_headers['User-Agent']='Mozilla/5.0 (compatible; Pharm3r-FacilityRisk-Archive/0.6)'
            browser_headers['Accept']='application/zip,application/octet-stream,*/*'
            return urllib.request.urlopen(urllib.request.Request(url,headers=browser_headers),timeout=180)
    f=tempfile.NamedTemporaryFile(suffix='.zip',delete=False)
    path=Path(f.name)
    try:
        with f:
            with open_archive() as res:
                final=urllib.parse.urlparse(res.geturl())
                if p.hostname in ('www.accessdata.fda.gov','accessdata.fda.gov') and (
                    final.scheme!='https' or final.hostname not in
                    ('www.accessdata.fda.gov','accessdata.fda.gov')):
                    raise ValueError('FDA archive redirect moved to unexpected host')
                total=0
                while True:
                    data=res.read(1024*1024)
                    if not data:break
                    total+=len(data)
                    if total>MAX_DOWNLOAD:raise ValueError('Official source archive exceeds maximum allowed size')
                    f.write(data)
        if not zipfile.is_zipfile(path):raise ValueError('Downloaded file is not a ZIP archive')
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise


class Links(HTMLParser):
    def __init__(self):
        super().__init__();self.href=None;self.text=[];self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':self.href=dict(attrs).get('href');self.text=[]
    def handle_data(self,data):
        if self.href is not None:self.text.append(data)
    def handle_endtag(self,tag):
        if tag=='a' and self.href is not None:
            self.links.append((' '.join(self.text).strip(),self.href));self.href=None;self.text=[]


def drug_zip_url(html):
    p=Links();p.feed(html)
    for name,url in p.links:
        if 'drug establishment annual registration status download file' in ' '.join(name.casefold().split()) and 'excluded' not in name.casefold():
            found=urllib.parse.urljoin(DECRS,url)
            if urllib.parse.urlparse(found).hostname not in ('www.accessdata.fda.gov','accessdata.fda.gov','www.fda.gov'):
                raise ValueError('DECRS download link points to unexpected domain')
            return found
    raise ValueError('Could not identify current official DECRS ZIP link')


def device_records(paths):
    try:import ijson
    except ImportError as exc:raise RuntimeError('Missing dependency: pip install ijson') from exc
    for path in paths:
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if not name.endswith('.json'):continue
                with z.open(name) as stream:
                    for raw in ijson.items(stream,'results.item'):
                        yield normalize_device(raw)


def run(out,device_archives=None,drug_archive=None,device_only=False):
    sources={};records=[]
    if device_archives:
        archives=[Path(x) for x in device_archives]
        device_date='fixture'
        expected=None
    else:
        metadata=json.loads(get_bytes(META).decode('utf-8'))
        m=metadata['results']['device']['registrationlisting']
        parts=m['partitions'];archives=[]
        device_date=m.get('export_date') or metadata.get('meta',{}).get('last_updated')
        expected=m.get('total_records')
        if not parts:raise ValueError('FDA metadata does not contain device registration partitions')
        print(f'FDA device registration: {len(parts)} partitions, {expected} reported records; export={device_date}',flush=True)
        for part in parts:
            url=part['file'];p=download_zip(url);archives.append(p)
            print(f'Downloaded {p.stat().st_size:,} bytes from {url}',flush=True)
    processed=0
    try:
        for row in device_records(archives):
            if row:records.append(row)
            processed+=1
    finally:
        if not device_archives:
            for p in archives:p.unlink(missing_ok=True)
    if expected is not None and processed!=expected:raise ValueError(f'Incomplete device source: saw {processed:,} records, expected {expected:,}')
    if not records:raise ValueError('Device source produced no valid establishment records')
    sources['fda_device']={'status':'imported','source':'openFDA device/registrationlisting full bulk download',
        'export_date':device_date,'reported_listing_records':expected,'processed_listing_records':processed,
        'valid_site_records':len(records),'url':META}
    print(f'Device registration records parsed: {processed:,}; valid establishment rows: {len(records):,}',flush=True)
    if device_only:
        sources['fda_drug']={'status':'not_requested','source':'FDA Drug Establishments Current Registration Site','url':DECRS}
    else:
        local_path=Path(drug_archive) if drug_archive else None
        try:
            if not local_path:
                try:
                    url=drug_zip_url(get_bytes(DECRS).decode('utf-8',errors='replace'))
                except Exception as page_error:
                    url=DECRS_DIRECT_ZIP
                    print(f'DECRS listing page unavailable ({page_error}); using official direct ZIP link',flush=True)
                print(f'DECRS download: {url}',flush=True)
                local_path=download_zip(url)
                with zipfile.ZipFile(local_path) as inspected:
                    print('DECRS archive members:',[(m.filename,m.file_size) for m in inspected.infolist()[:20]],flush=True)
                    for member in inspected.infolist()[:15]:
                        if member.filename.lower().endswith(('.csv','.tsv','.txt','.psv','.dat')):
                            with inspected.open(member) as sample:
                                print('DECRS member header bytes:',repr(sample.readline()[:250]),flush=True)
                            break
            else:url='local_official_fixture'
            try:
                drug_rows=list(parse_drug_zip(local_path))
            finally:
                if not drug_archive:local_path.unlink(missing_ok=True)
            # A publication of thousands of sites must not silently shrink to a
            # handful of successfully parsed lines when the official schema drifts.
            if not drug_archive and len(drug_rows)<5000:
                raise ValueError(f'DECRS count {len(drug_rows)} below live-source quality floor 5000')
            old_count=0
            prior_path=Path(out)
            if prior_path.is_file():
                prior=validate_catalog(json.loads(prior_path.read_text(encoding='utf-8')))
                old_count=sum(1 for row in prior['rows'] if row[prior['fields'].index('sector')]=='Pharmaceutical')
            if old_count>=5000 and len(drug_rows)<old_count*0.5 and not drug_archive:
                raise ValueError(f'DECRS source contracted from {old_count} to {len(drug_rows)} records; human review required')
            records.extend(drug_rows)
            sources['fda_drug']={'status':'imported','source':'FDA Drug Establishments Current Registration Site',
                'processed_site_records':len(drug_rows),'url':url}
            print(f'Drug registration records parsed: {len(drug_rows):,}',flush=True)
        except Exception as ex:
            # Do not turn an endpoint or parser outage into thousands of implied
            # deregistrations. Preserve the last published valid snapshot, labeled stale.
            sources['fda_drug']={'status':'unavailable','source':'FDA Drug Establishments Current Registration Site',
                'reason':str(ex)[:350],'url':DECRS}
            print(f'DECRS not imported: {ex}',file=sys.stderr,flush=True)
            prior_path=Path(out)
            if prior_path.is_file():
                try:
                    prior=validate_catalog(json.loads(prior_path.read_text(encoding='utf-8')))
                    before=prior['sources'].get('fda_drug',{})
                    if before.get('status') in ('imported','stale_preserved'):
                        old_sites=[dict(zip(prior['fields'],row)) for row in prior['rows']
                                   if row[prior['fields'].index('sector')]=='Pharmaceutical']
                        if len(old_sites)>=5000:
                            records.extend(old_sites)
                            sources['fda_drug'].update(status='stale_preserved',
                                preserved_site_records=len(old_sites),
                                last_good_generated_at=before.get('last_good_generated_at') or prior.get('generated_at'))
                            print(f'Preserved {len(old_sites):,} previously published drug establishments as STALE',flush=True)
                except (ValueError,KeyError,TypeError) as preserve_error:
                    print(f'Prior drug snapshot could not be preserved: {preserve_error}',file=sys.stderr,flush=True)
    result=make_catalog(records,sources)
    validate_catalog(result)
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    tmp=out.with_suffix('.tmp')
    with tmp.open('w',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,separators=(',',':'))
    tmp.replace(out)
    print('CATALOG STATUS:',json.dumps({'unique_source_entities':len(result['rows']),
        'countries':result['summary']['countries'],'by_sector':result['summary']['by_sector'],
        'source_status':{k:v['status'] for k,v in sources.items()},'bytes':out.stat().st_size}),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default=str(ROOT/'web'/'registry'/'catalog.json'))
    parser.add_argument('--device-zip',action='append',default=[])
    parser.add_argument('--drug-zip')
    parser.add_argument('--device-only',action='store_true')
    args=parser.parse_args()
    run(args.output,args.device_zip or None,args.drug_zip,args.device_only)

if __name__=='__main__':main()