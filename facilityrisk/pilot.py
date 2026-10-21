"""Build a 25-row *research candidate* cohort, not 25 verified outcome cases.

Use the live public official source catalogs when available. The selection is
deterministic, balanced by source family and remains identity-unconfirmed.
Comparison candidates do NOT imply that the facility experienced no loss.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

from .registry_catalog import validate_catalog,FIELDS

ROOT=Path(__file__).resolve().parent.parent
SOURCES={
    'fda_device':('web/registry/catalog.json','FDA device registration / listing',12),
    'ireland_leap':('web/registry/ireland-leap.json','Ireland EPA LEAP',5),
    'canada_npri':('web/registry/canada-npri.json','Canada NPRI',5)
}
CASES=[
 ('Baxter North Cove','site-baxter-north-cove','Flood / production disruption'),
 ('Pfizer Rocky Mount','site-pfizer-rocky-mount','Tornado / manufacturing disruption'),
 ('Amgen Juncos','site-amgen-juncos','Hurricane / supply-chain interruption')
]
FIELDS_OUTPUT=[
 'cohort_id','cohort_role','facility_name','reported_operator',
 'country','source_family','source_identity','source_reference',
 'known_research_case_id','outcome_status','identity_review',
 'coordinate_review','pre_event_publication_validation',
 'underwriting_exposure_validation','selection_note'
]

def _digest(text):
    return hashlib.sha256(str(text).encode('utf-8')).hexdigest()

def source_url(row):
    source=row['source']
    if source=='Ireland EPA LEAP':
        reg=row['registration_number']
        if re.fullmatch(r'[A-Z][A-Z0-9-]{2,40}',reg or ''):
            return 'https://leap.epa.ie/licence-profile/'+reg
    if source=='Canada NPRI':
        return 'https://maps-cartes.ec.gc.ca/arcgis/rest/services/STB_DGST/NPRI/MapServer/0'
    return 'https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfRL/rl.cfm'

def _catalog(path,source_family):
    document=validate_catalog(json.loads(Path(path).read_text(encoding='utf-8')))
    return [dict(zip(FIELDS,row)) for row in document['rows']
            if row[FIELDS.index('source')]==source_family]

def create_pilot_manifest(catalog_files,*,size=25):
    """Return a 25-row cohort screening list; never labels no-event controls."""
    if size!=25:raise ValueError('This pilot protocol requires exactly 25 candidate rows')
    selected=[]
    for name,fid,event in CASES:
        selected.append(dict(cohort_id='retrospective-'+fid,
            cohort_role='retrospective_documented_disruption',
            facility_name=name,reported_operator='Not independently verified for this pilot',
            country='US',source_family='Curated event case study',
            source_identity='',source_reference='https://github.com/jhennessy-pharm3r/FacilityTest/blob/main/web/case-studies.json',
            known_research_case_id=fid,outcome_status='retrospective_public_disruption',
            identity_review='pending_current_plant_identity',
            coordinate_review='pending_pilot_review',
            pre_event_publication_validation='not_completed',
            underwriting_exposure_validation='not_completed',
            selection_note=event+'; retrospective example only, not a pre-event predictive observation'))
    seen_ids=set(x['cohort_id'] for x in selected)
    for key,(_,official_type,quota) in SOURCES.items():
        path=catalog_files.get(key)
        if path is None:raise ValueError('Missing source catalog: '+key)
        population=_catalog(path,official_type)
        # Fully deterministic pseudo-random sampling avoids taking only the
        # alphabetical first entries, without pretending to remove selection bias.
        population.sort(key=lambda row:_digest(key+':'+row['id']))
        accepted=0
        for source in population:
            if accepted>=quota:break
            identifier=str(source['id'])
            if identifier in seen_ids or len(source['name'])<4:continue
            seen_ids.add(identifier)
            selected.append(dict(cohort_id='candidate-'+identifier,
                cohort_role='unverified_source_record',
                facility_name=source['name'],
                reported_operator=source['company'],country=source['country'],
                source_family=source['source'],
                source_identity=source['registration_number'] or source['fei'],
                source_reference=source_url(source),known_research_case_id='',
                outcome_status='unknown_not_a_confirmed_no_event_control',
                identity_review='source_only_unverified_physical_site',
                coordinate_review='not_reviewed',
                pre_event_publication_validation='not_completed',
                underwriting_exposure_validation='not_completed',
                selection_note='Candidate only; industry, operator, property and outcome must be verified'))
            accepted+=1
        if accepted<quota:
            raise ValueError(key+' source catalog contains fewer eligible candidates than quota '+str(quota))
    if len(selected)!=size:raise ValueError('Cohort size mismatch')
    return selected

def export_pilot_manifest(outpath,catalog_root=ROOT):
    base=Path(catalog_root)
    sources={name:base/rel for name,(rel,_,_) in SOURCES.items()}
    rows=create_pilot_manifest(sources)
    target=Path(outpath).expanduser().resolve()
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=FIELDS_OUTPUT)
        writer.writeheader()
        writer.writerows(rows)
    return {'status':'research_candidates_only',
            'cohort_rows':len(rows),'retrospective_cases':3,
            'unverified_source_candidates':22,
            'verified_comparison_controls':0,
            'output':str(target),'warning':'No source-only row is a known no-event control or verified manufacturer.'}
