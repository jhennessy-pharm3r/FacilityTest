#!/usr/bin/env python3
"""Publish independently sourced Irish EPA LEAP licence profiles for discovery.

Official public API: https://data.epa.ie/leap/api/v1/LicenceProfile/list
These are regulatory LICENCE profiles; not verified property coordinates, not a
manufacturer census, and not an assertion of violation or underwriting risk.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
import urllib.request

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from facilityrisk.registry_catalog import FIELDS, validate_catalog

API='https://data.epa.ie/leap/api/v1/LicenceProfile/list'
SOURCE='Ireland EPA LEAP'
USER_AGENT='Pharm3r-FacilityRisk-Catalog/0.6 (+github.com/jhennessy-pharm3r/FacilityTest)'


def clean(v,limit=250):
    if isinstance(v,(str,int,float)):
        return re.sub(r'\s+',' ',str(v)).strip()[:limit]
    return ''


def make_ireland_catalog(payload,generated_at=None,min_rows=1):
    if not isinstance(payload,dict) or not isinstance(payload.get('list'),list):
        raise ValueError('Irish EPA LEAP response must have a list of licence profiles')
    raw=payload['list']
    if not isinstance(payload.get('count'),int) or payload['count']!=len(raw):
        raise ValueError('LEAP reported count does not match received profile list')
    rows=[];seen_guids={};profile_counts=Counter();repeated_guid_rows=0
    for item in raw:
        if not isinstance(item,dict):raise ValueError('Invalid LEAP profile element')
        profile=clean(item.get('profilenumber'),60).upper()
        guid=clean(item.get('licenceprofileid'),80)
        name=clean(item.get('name'),160)
        operator=clean(item.get('organisationname'),160) or name
        url=clean(item.get('url'),500)
        if not profile or not name or not guid:
            raise ValueError('LEAP profile is missing its official identifier/name')
        if not re.fullmatch(r'[A-Z][A-Z0-9-]{2,40}',profile):
            raise ValueError('Invalid official LEAP licence-profile identifier')
        if url and url!='https://leap.epa.ie/licence-profile/'+profile:
            raise ValueError('LEAP record source URL did not match its official profile')

        # A licence PROFILE NUMBER is not a unique API entity ID: the live
        # publisher contains duplicate profile numbers (e.g. S0020).
        # Use the publisher's stable licenceprofileid GUID to distinguish
        # separate source records; never collapse plants by a shared label.
        observation=(profile,name,operator,
                     clean(item.get('activelicencetype'),180),
                     clean(item.get('county'),120),clean(item.get('town'),120))
        if guid in seen_guids:
            if seen_guids[guid]!=observation:
                raise ValueError('Conflicting LEAP records for the same official profile GUID')
            repeated_guid_rows+=1
            continue
        seen_guids[guid]=observation
        profile_counts[profile]+=1
        row={
          'id':'ie-leap-'+sha256(guid.encode('utf-8')).hexdigest()[:20],
          'name':name,'company':operator,'city':clean(item.get('town'),120),
          'state':clean(item.get('county'),120),'country':'IE','fei':'',
          'registration_number':profile,
          'activities':clean(item.get('activelicencetype'),180) or 'EPA licence profile',
          'sector':'Environmental licence','address':'','expiry_year':'',
          'source':SOURCE,'source_records':1
        }
        rows.append([row.get(key,'') for key in FIELDS])
    if len(rows)<min_rows:raise ValueError(f'LEAP returned {len(rows)} profiles; expected >= {min_rows}')
    rows.sort(key=lambda x:(str(x[1]).casefold(),str(x[0])))
    by_type=Counter(row[FIELDS.index('activities')] for row in rows)
    return validate_catalog({
       'schema_version':'1.0',
       'generated_at':generated_at or datetime.now(timezone.utc).isoformat(timespec='seconds'),
       'fields':list(FIELDS),
       'rows':rows,
       'summary':{'distinct_source_entities':len(rows),
                  'source_rows':payload['count'],'countries':1,
                  'by_sector':{'Environmental licence':len(rows)},
                  'country_counts':{'IE':len(rows)},
                  'by_licence_type':dict(sorted(by_type.items())),
                  'repeated_profile_numbers':sum(v-1 for v in profile_counts.values() if v>1),
                  'repeated_guid_rows':repeated_guid_rows,
                  'profile_number_collisions':dict(sorted((k,v) for k,v in profile_counts.items() if v>1))},
       'sources':{'ireland_leap':{
           'status':'imported',
           'source':'Ireland EPA LEAP licence profile API',
           'url':API,'reported_profiles':payload['count'],
           'coverage':'All published licence profiles in the API response, not only life-sciences plants'}},
       'coverage_note':'Official Irish EPA regulatory licence profiles keyed to profile GUID, not property coordinates, '
                       'manufacturing verification, compliance infractions, or insured losses.'})


def fetch_live():
    request=urllib.request.Request(API,headers={'User-Agent':USER_AGENT,'Accept':'application/json'})
    with urllib.request.urlopen(request,timeout=75) as res:
        if res.status!=200:raise ValueError('LEAP returned HTTP '+str(res.status))
        body=res.read(25_000_001)
        if len(body)>25_000_000:raise ValueError('LEAP response exceeds limit')
        return json.loads(body.decode('utf-8-sig'))


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default=str(ROOT/'web'/'registry'/'ireland-leap.json'))
    parser.add_argument('--fixture',help='Offline test fixture JSON; not allowed for scheduled publication')
    parser.add_argument('--min-rows',type=int,default=1000)
    args=parser.parse_args(argv)
    payload=json.loads(Path(args.fixture).read_text(encoding='utf-8')) if args.fixture else fetch_live()
    result=make_ireland_catalog(payload,min_rows=args.min_rows)
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    temp=output.with_suffix('.tmp')
    temp.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    temp.replace(output)
    print(json.dumps({'source':SOURCE,'profiles':len(result['rows']),
                      'types':result['summary']['by_licence_type'],'generated_at':result['generated_at']},
                     ensure_ascii=False))


if __name__=='__main__':main()
