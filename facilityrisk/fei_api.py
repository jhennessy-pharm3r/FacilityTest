"""Opt-in FDA FEI API lookup for reviewed private facility research.

The FDA OII FEI API requires credentials obtained from FDA. This connector
never guesses credentials, scrapes the authenticated endpoint, or automatically
verifies an identity based on an API result. A response is reviewable evidence,
not proof of property boundaries, insurer loss, or ultimate-parent ownership.
"""
from __future__ import annotations

import json
import os
import time
import uuid

import requests

from .ingest import utcnow
from .intelligence import audit

API='https://www.accessdata.fda.gov/rest/feiapi/firmdata/feinumber/'
DOCUMENTATION='https://www.accessdata.fda.gov/scripts/feiportal/apidocs/'

def _text(value,limit=250):
    if value is None or isinstance(value,(dict,list)):
        return ''
    return str(value).strip()[:limit]


def normalize_response(response,requested_fei):
    """Validate a successful FEI firm-result envelope and physical address."""
    if not isinstance(response,dict) or not isinstance(response.get('RESULT'),dict):
        raise ValueError('FDA FEI API did not return a firm RESULT object')
    result=response['RESULT']
    observed=''.join(c for c in _text(result.get('FEINUMBER'),25) if c.isdigit())
    if not observed or observed!=requested_fei:
        raise ValueError('FDA FEI response identifier differs from the requested site FEI')
    addr=result.get('physicaladdress')
    if not isinstance(addr,dict):
        addr={}
    address={field:_text(addr.get(key),160) for field,key in (
        ('street1','FIRMADDRESS1'),('street2','FIRMADDRESS2'),('city','FIRMCITY'),
        ('state','FIRMSTATE'),('province','FIRMPROVINCE'),
        ('country','FIRMCOUNTRY'),('postal_code','FIRMZIP'),
        ('address_validation','VALIDATIONSTATUS'))}
    return {'fei':observed,
            'legal_name':_text(result.get('LEGALNAME'),200),
            'physical_address':address,
            'merged_firm_indicator':bool(result.get('MERGEDFIRMINDICATOR')),
            'review_status':'observed_unverified',
            'documented_source':DOCUMENTATION}


def lookup_fei(conn,facility_id,actor,session=None):
    """Retrieve and archive the *minimum* authenticated firm metadata.

    Transmission is opt-in and FEI-only. The URL and validation result contain
    no API secrets. The calling workspace remains unverified until independent
    corroboration and an explicit reviewer decision.
    """
    row=conn.execute('SELECT id,fei FROM facilities WHERE id=?',(facility_id,)).fetchone()
    if row is None:raise ValueError('Unknown facility')
    requested=''.join(c for c in str(row['fei'] or '') if c.isdigit())
    if not (7<=len(requested)<=12 and requested==str(row['fei']).strip()):
        raise ValueError('Facility needs a numeric observed FDA FEI before API lookup')
    user=os.environ.get('FACILITY_RISK_FEI_AUTH_USER','').strip()
    key=os.environ.get('FACILITY_RISK_FEI_AUTH_KEY','').strip()
    if not user or not key:
        raise ValueError('FDA FEI API credentials not configured; request authorization from FDA OII')
    url=API+requested
    client=session or requests.Session()
    response=client.get(url,params={'signature':str(time.time_ns())},
        headers={'Authorization-User':user,'Authorization-Key':key,
                 'Accept':'application/json'},
        timeout=30)
    if response.status_code in (401,403):
        raise ValueError('FDA FEI API authorization rejected')
    if response.status_code in (429,430):
        raise ValueError('FDA FEI API rate limit reached')
    response.raise_for_status()
    normalized=normalize_response(response.json(),requested)
    now=utcnow()
    with conn:
        conn.execute('''INSERT INTO raw_snapshots
          (id,source,facility_id,url,retrieved_at,response_json,notes)
          VALUES (?,?,?,?,?,?,?)''',
          (uuid.uuid4().hex,'FDA OII authenticated FEI lookup',facility_id,
           DOCUMENTATION,now,json.dumps(normalized,ensure_ascii=False),
           'Official authorized API metadata, edited to minimum firm fields; '
           'site identity and coordinates remain UNVERIFIED'))
        audit(conn,'fda_fei_lookup_observed',facility_id,actor,
              {'fei':requested,'documentation':DOCUMENTATION,
               'has_physical_address':bool(normalized['physical_address']['street1'])})
    return {'facility_id':facility_id,'checked_at':now,**normalized,
            'warning':'Source observation only. No verified site crosswalk, '
                      'property coordinate, inspection outcome or risk score has been asserted.'}
