#!/usr/bin/env python3
"""Diagnose FDA DECRS archive accessibility without scraping or bulk caching.

Read the FDA landing page and at most four bytes from the official ZIP target.
A valid ZIP prefix means only that the endpoint is reachable, not that the
archive is complete, current, parseable or authorized for a production import.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime,timezone
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.parse import urlparse
from urllib.request import Request,urlopen

from scripts.build_catalog import DECRS,DECRS_DIRECT_ZIP,drug_zip_url

ALLOWED={'www.fda.gov','fda.gov','www.accessdata.fda.gov','accessdata.fda.gov'}
AGENTS={
    'catalog_client':'FacilityRisk-DECRS-Availability/0.6 (+github.com/jhennessy-pharm3r/FacilityTest)',
    'standard_browser':'Mozilla/5.0 (compatible; FacilityRisk-DECRS-Diagnostic)'
}

def _safe(url):
    p=urlparse(url)
    if p.scheme!='https' or p.hostname not in ALLOWED:
        raise ValueError('Only the official HTTPS FDA hosts may be probed')
    return url

def inspect(url,opener=urlopen,agent='catalog_client',method='GET',timeout=25):
    _safe(url)
    headers={'User-Agent':AGENTS[agent],
             'Accept':'application/zip,application/octet-stream,*/*'}
    if method=='GET':headers['Range']='bytes=0-3'
    request=Request(url,method=method,headers=headers)
    info={'mode':method,'agent':agent,'requested_url':url}
    try:
        with opener(request,timeout=timeout) as response:
            final=response.geturl()
            _safe(final)
            data=response.read(4) if method=='GET' else b''
            info.update(http_status=response.status,final_url=final,
              content_type=response.headers.get('Content-Type',''),
              content_length=response.headers.get('Content-Length',''),
              accept_ranges=response.headers.get('Accept-Ranges',''),
              zip_header_verified=(data.startswith(b'PK\x03\x04') if method=='GET' else None))
    except HTTPError as e:
        info.update(http_status=e.code,error_type='HTTPError',
                    diagnostic='FDA server returned error status')
    except (URLError,OSError,TimeoutError,ValueError) as e:
        info.update(http_status=None,error_type=type(e).__name__,
                    diagnostic=str(e)[:180])
    return info

def probe(opener=urlopen):
    result={'checked_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'landing_page':DECRS,'candidate_urls':[], 'tests':[],
            'interpretation':'Header inspection only; never report facility records or a verified data import.'}
    try:
        with opener(Request(DECRS,headers={'User-Agent':AGENTS['catalog_client']}),timeout=30) as response:
            body=response.read(1_500_001)
            if len(body)>1_500_000:raise ValueError('FDA page exceeds allowed diagnostic size')
            url=drug_zip_url(body.decode('utf-8',errors='replace'))
            result['landing_page_status']='parsed'
    except (HTTPError,URLError,OSError,ValueError) as ex:
        url=DECRS_DIRECT_ZIP
        result['landing_page_status']='unavailable_using_documented_direct_link'
        result['listing_error_type']=type(ex).__name__
    candidates=list(dict.fromkeys([url,DECRS_DIRECT_ZIP]))
    for candidate in candidates:
        _safe(candidate)
        result['candidate_urls'].append(candidate)
        for agent in AGENTS:
            for method in ('HEAD','GET'):
                result['tests'].append(inspect(candidate,opener,agent,method))
    result['state']=('zip_header_observed' if any(
        p.get('zip_header_verified') is True for p in result['tests'])
        else 'zip_not_confirmed')
    result['next_step']=('Run the complete validated DECRS parser against a securely retrieved official archive'
                         if result['state']=='zip_header_observed'
                         else 'Request accessible current archive or download instructions from eDRLS@fda.hhs.gov')
    return result

def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    args=parser.parse_args(argv)
    status=probe()
    target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(status,indent=2,sort_keys=True),encoding='utf-8')
    print(json.dumps({'state':status['state'],
                      'landing_page':status['landing_page_status'],
                      'http_codes':[p.get('http_status') for p in status['tests']],
                      'next_step':status['next_step']}))

if __name__=='__main__':main()
