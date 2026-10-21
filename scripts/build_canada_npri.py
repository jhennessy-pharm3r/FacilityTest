#!/usr/bin/env python3
"""Export Canada's official NPRI reporting-facility ArcGIS layer as source identities.

This is a list of facilities reporting to NPRI in the layer's reporting YEAR.
It does not assert environmental violations, manufacturing or insured loss.
Coordinates are deliberately not released or treated as property centroids.
Data source: Government of Canada, Environment and Climate Change Canada
https://maps-cartes.ec.gc.ca/arcgis/rest/services/STB_DGST/NPRI/MapServer/0
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from facilityrisk.registry_catalog import FIELDS,validate_catalog

LAYER='https://maps-cartes.ec.gc.ca/arcgis/rest/services/STB_DGST/NPRI/MapServer/0'
QUERY=LAYER+'/query'
HEADERS={'User-Agent':'FacilityRisk-Canadian-NPRI-Catalog/0.6 (public governmental geodata research)',
         'Accept':'application/json'}
FIELDS_QUERY='OBJECTID_1,ReportYear,NpriID,CompanyName,FacilityName,Address1,City,ProvinceCode,NAICS__Code_SCIAN,SectorDescriptionEn'
MAX_OBJECTS=100000


def clean(value,limit=250):
    if value is None or isinstance(value,(dict,list)):return ''
    return re.sub(r'\s+',' ',str(value)).strip()[:limit]


def get_json(params):
    url=QUERY+'?'+urllib.parse.urlencode(params)
    last_error=None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers=HEADERS),timeout=80) as response:
                content=response.read(15_000_001)
                if len(content)>15_000_000:raise ValueError('ArcGIS page exceeds response size limit')
            result=json.loads(content.decode('utf-8-sig'))
            if not isinstance(result,dict) or result.get('error'):
                raise ValueError('ArcGIS query error: '+str(result.get('error'))[:200])
            return result
        except (OSError,TimeoutError) as exc:
            last_error=exc
            if attempt<2:time.sleep(attempt+1)
    raise RuntimeError('NPRI ArcGIS request failed: '+str(last_error))


def normalize_feature(feature):
    if not isinstance(feature,dict) or not isinstance(feature.get('attributes'),dict):
        raise ValueError('NPRI feature is missing ArcGIS attributes')
    a=feature['attributes']
    key=clean(a.get('NpriID'),45)
    oid=clean(a.get('OBJECTID_1'),30)
    year=clean(a.get('ReportYear'),8)
    name=clean(a.get('FacilityName'),160) or clean(a.get('CompanyName'),160)
    if not key or not key.isdigit() or not oid.isdigit() or not year.isdigit() or not name:
        raise ValueError('NPRI source feature missing stable record ID, year or facility name')
    company=clean(a.get('CompanyName'),160) or name
    address=clean(a.get('Address1'),240)
    province=clean(a.get('ProvinceCode'),40).upper()
    city=clean(a.get('City'),120)
    sector=clean(a.get('SectorDescriptionEn'),100)
    naics=clean(a.get('NAICS__Code_SCIAN'),20)
    siteid='ca-npri-'+sha256((year+'|'+key+'|'+oid).encode('utf-8')).hexdigest()[:20]
    return {
      'id':siteid,'name':name,'company':company,'city':city,'state':province,
      'country':'CA','fei':'','registration_number':key,
      'activities':'Reported '+year+' · '+(sector or 'NPRI reporting')+((' · NAICS '+naics) if naics else ''),
      'sector':'Environmental reporting','address':address,'expiry_year':'',
      'source':'Canada NPRI','source_records':1,
      '_oid':oid,'_year':year,'_npri':key
    }


def make_canada_catalog(features,expected_ids,generated_at=None,min_rows=1):
    """Require exactly the requested object IDs; no silent ArcGIS truncation."""
    if not isinstance(features,list):raise ValueError('Invalid ArcGIS feature list')
    if not isinstance(expected_ids,list) or not expected_ids:
        raise ValueError('ArcGIS must return a nonempty official ObjectID cohort')
    keys=[int(x) for x in expected_ids]
    if len(keys)!=len(set(keys)):raise ValueError('Duplicate requested ArcGIS feature IDs')
    expected={str(x) for x in keys}
    observed=set();records=[];years=Counter();by_npri=Counter()
    for feature in features:
        row=normalize_feature(feature)
        if row['_oid'] not in expected:raise ValueError('ArcGIS returned a feature outside the requested cohort')
        if row['_oid'] in observed:raise ValueError('ArcGIS repeated an ObjectID in its response')
        observed.add(row['_oid']);years[row['_year']]+=1;by_npri[row['_npri']]+=1
        records.append([row.get(key,'') for key in FIELDS])
    if observed!=expected:
        raise ValueError(f'Incomplete NPRI ArcGIS response: missing {len(expected-observed)} source IDs')
    if len(records)<min_rows:
        raise ValueError(f'Unexpectedly small NPRI source: {len(records)} rows (<{min_rows})')
    records.sort(key=lambda x:(str(x[1]).casefold(),str(x[0])))
    provinces=Counter(row[FIELDS.index('state')] for row in records if row[FIELDS.index('state')])
    return validate_catalog({
      'schema_version':'1.0',
      'generated_at':generated_at or datetime.now(timezone.utc).isoformat(timespec='seconds'),
      'fields':list(FIELDS),'rows':records,
      'summary':{'distinct_source_entities':len(records),'source_rows':len(features),
          'countries':1,'country_counts':{'CA':len(records)},
          'by_sector':{'Environmental reporting':len(records)},
          'reported_years':dict(sorted(years.items())),
          'provinces':dict(sorted(provinces.items())),
          'repeated_npri_identifiers':sum(n-1 for n in by_npri.values() if n>1)},
      'sources':{'canada_npri':{'status':'imported',
          'source':'Canada NPRI official reporting-facility ArcGIS layer',
          'url':LAYER,'reported_records':len(expected),'reported_years':dict(years),
          'coverage':'Facilities represented in the source layer; not all Canadian industry'}},
      'coverage_note':'Canada NPRI reporting locations (not all plants). Source address reported, no '
                      'approved property centroid, regulatory violation, or insurance risk inferred.'})


def refresh(min_rows=1000):
    ids=get_json({'where':'1=1','returnIdsOnly':'true','f':'json'})
    values=ids.get('objectIds')
    if not isinstance(values,list) or not (min_rows<=len(values)<=MAX_OBJECTS):
        raise ValueError('Unexpected NPRI ArcGIS ObjectID cohort size')
    if len(values)!=len(set(values)):raise ValueError('Repeated object identifiers in ArcGIS source')
    data=[]
    for offset in range(0,len(values),800):
        part=values[offset:offset+800]
        result=get_json({'objectIds':','.join(map(str,part)),
                         'outFields':FIELDS_QUERY,'returnGeometry':'false','f':'json'})
        batch=result.get('features')
        if not isinstance(batch,list) or len(batch)!=len(part):
            raise ValueError('ArcGIS page is incomplete or was truncated')
        data.extend(batch)
    return make_canada_catalog(data,values,min_rows=min_rows)


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--output',default=str(ROOT/'web'/'registry'/'canada-npri.json'))
    p.add_argument('--min-rows',type=int,default=1000)
    args=p.parse_args(argv)
    cat=refresh(min_rows=args.min_rows)
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    tmp=out.with_suffix('.tmp')
    tmp.write_text(json.dumps(cat,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    tmp.replace(out)
    print(json.dumps({'source':'Canada NPRI','entities':len(cat['rows']),
                      'years':cat['summary']['reported_years'],
                      'id_collisions':cat['summary']['repeated_npri_identifiers']},sort_keys=True))


if __name__=='__main__':main()
