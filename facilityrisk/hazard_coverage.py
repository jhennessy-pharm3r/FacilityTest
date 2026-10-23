"""Peril-specific source coverage; a single flood map never means all-cat risk screened.

A hazard screening is a source observation at a reviewed point, not a calibrated
site-loss probability, verified property damage, insurance guarantee or
determination that the property is low risk.
"""
from __future__ import annotations
import re

PERILS=(
  ('flood','Flood / river and inland inundation',r'\bflood\b|\binundat'),
  ('storm_surge','Coastal storm surge',r'\bstorm surge\b|\bcoastal surge\b'),
  ('windstorm','Hurricane / windstorm',r'\bwindstorm\b|\bhurricane\b|\bwind speed\b|\btropical cyclone\b'),
  ('wildfire','Wildfire / smoke',r'\bwildfire\b|\bbushfire\b|\bwild fire\b'),
  ('earthquake','Earthquake / seismic shaking',r'\bearthquake\b|\bseismic\b|\bground shaking\b'),
  ('tornado','Tornado',r'\btornado\b'),
  ('convective','Hail / severe convective storm',r'\bhail\b|\bconvective\b|\bthunderstorm\b'),
  ('extreme_rain','Extreme precipitation',r'\bextreme rainfall\b|\bextreme precipitation\b|\bheavy rainfall\b'),
  ('heat','Extreme heat',r'\bextreme heat\b|\bheatwave\b|\bheat wave\b'),
  ('drought_water','Drought / water stress',r'\bdrought\b|\bwater stress\b|\baqueduct\b'),
  ('winter','Winter storm / ice / freeze',r'\bwinter storm\b|\bice storm\b|\bheavy snow\b|\bfreeze\b'),
  ('tsunami','Tsunami',r'\btsunami\b'),
  ('landslide','Landslide / slope instability',r'\blandslide\b|\bslope instability\b'),
)
UNRESOLVED_STATES={'','unknown','unassessed','not_mapped','source_unavailable','error',
    'not_available','stale_location_review','data_missing'}

def _normalized(value):
    return re.sub(r'[^a-z0-9]+',' ',str(value or '').casefold()).strip()

def _peril(value):
    name=_normalized(value)
    # Coastal surge is not inland flood, and a generic storm alone cannot
    # imply windstorm, hail, tornado or any separate peril.
    for key,label,pattern in PERILS:
        if re.search(pattern,name):return key
    return None

def build_peril_coverage(hazards,point_verified=False):
    """Only count classifications at the exact, currently reviewed facility point.

    The input hazard rows come from get_intelligence, which invalidates any
    stored source result if the reviewed coordinate changed.
    """
    groups={key:[] for key,_,_ in PERILS}
    unmatched=[]
    for hazard in hazards or []:
        valid=bool(point_verified and hazard.get('valid_for_current_site_point'))
        if not valid:continue
        key=_peril(hazard.get('peril'))
        if key:groups[key].append(hazard)
        else:unmatched.append(hazard)
    items=[]
    for key,label,_ in PERILS:
        rows=groups[key]
        completed=[h for h in rows if _normalized(h.get('status')).replace(' ','_') not in UNRESOLVED_STATES]
        status=('source_screened' if completed else
                'source_checked_unresolved' if rows else 'unassessed')
        items.append({'key':key,'peril':label,'status':status,
            'current_source_rows':len(rows),
            'source_classifications':[
              {'source':str(h.get('source') or ''),'status':str(h.get('status') or ''),
               'source_url':str(h.get('source_url') or ''),
               'effective_date':str(h.get('effective_date') or ''),
               'retrieved_at':str(h.get('retrieved_at') or ''),
               'limitations':str(h.get('limitations') or '')}
              for h in rows],
            'interpretation':(
                'Source classified this peril at the reviewed point; site vulnerability, actual loss and policy coverage remain unknown'
                if completed else
                'A source was queried, but returned no classified peril zone; NOT a low-risk finding'
                if rows else
                'No independently valid source screening for this peril; cannot infer an absence of exposure')})
    screened=[item['key'] for item in items if item['status']=='source_screened']
    unresolved=[item['key'] for item in items if item['status']=='source_checked_unresolved']
    missing=[item['key'] for item in items if item['status']=='unassessed']
    aggregate=('fully_source_screened' if len(screened)==len(PERILS) else
               'partially_source_screened' if screened else
               'source_checked_unresolved' if unresolved else 'unassessed')
    return {'status':aggregate,'site_coordinate_reviewed':bool(point_verified),
      'peril_count':len(PERILS),'perils_source_screened':screened,
      'perils_source_checked_unresolved':unresolved,'perils_unassessed':missing,
      'uncategorized_current_source_perils':[
          {'peril':str(h.get('peril') or ''),'status':str(h.get('status') or ''),
           'source':str(h.get('source') or '')} for h in unmatched],
      'perils':items,
      'limitations':['Source classifications are not building damage, vulnerability or loss probabilities',
        'An unclassified/absent flood zone is not a low flood exposure conclusion',
        'Unscreened hazards are unknown, never lower-risk by default',
        'Even a full source-screening set is not a calibrated catastrophe model or insurance assessment']}
