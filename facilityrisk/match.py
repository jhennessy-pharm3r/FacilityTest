"""Facility matching support. Non-FEI matches are always review candidates."""
from __future__ import annotations
import math
import re
from difflib import SequenceMatcher

ABBREVS = {'road':'rd','rd':'rd','street':'st','st':'st','avenue':'ave','ave':'ave',
           'boulevard':'blvd','blvd':'blvd','drive':'dr','dr':'dr',
           'north':'n','south':'s','east':'e','west':'w','highway':'hwy','hwy':'hwy'}
SUFFIXES = {'inc','llc','corp','corporation','ltd','limited','company','co'}


def norm(text: str | None, drop_suffixes: bool = False) -> str:
    tokens = re.findall(r'[a-z0-9]+', (text or '').lower())
    return ' '.join(ABBREVS.get(t,t) for t in tokens if not(drop_suffixes and t in SUFFIXES))


def haversine_km(lat1: float,lon1: float,lat2: float,lon2: float) -> float:
    r=6371.0088
    a1,a2=math.radians(lat1),math.radians(lat2)
    da=math.radians(lat2-lat1);dl=math.radians(lon2-lon1)
    a=math.sin(da/2)**2+math.cos(a1)*math.cos(a2)*math.sin(dl/2)**2
    return 2*r*math.asin(min(1,math.sqrt(a)))


def preview_match(rows: list[dict], name: str = '', address: str = '', fei: str = '') -> list[dict]:
    results=[]
    input_name=norm(name,True)
    input_addr=norm(address)
    for facility in rows:
        reasons=[]
        score=0.0
        exact_fei = bool(fei and facility.get('fei') and fei.strip()==str(facility['fei']).strip())
        if exact_fei:
            score=1.0
            reasons.append('Exact FDA FEI match')
        else:
            if input_name:
                similarity=SequenceMatcher(None,input_name,norm(facility['name'],True)).ratio()
                score += 0.25*similarity
                if similarity>0.70: reasons.append('Similar facility name')
            if input_addr:
                site_addr=norm(facility.get('address'))
                similarity=SequenceMatcher(None,input_addr,site_addr).ratio()
                score += 0.55*similarity
                if similarity>0.75: reasons.append('Similar site address')
            if input_name and input_addr and score>0.68: reasons.append('Site identity requires review')
        if score>0.25:
            results.append({'id':facility['id'],'name':facility['name'],'fei':facility.get('fei'),
                            'score':round(score,3),'reasons':reasons,
                            'status':'verified_identifier' if exact_fei else 'candidate_review',
                            'auto_link_allowed':exact_fei})
    return sorted(results,key=lambda x:x['score'],reverse=True)[:10]
