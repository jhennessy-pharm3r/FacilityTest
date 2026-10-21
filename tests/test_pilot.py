"""No synthetic or unlabeled outcome controls in the 25-facility pilot."""
import csv
import json
from collections import Counter
from pathlib import Path
import pytest

from facilityrisk.registry_catalog import FIELDS
from facilityrisk.pilot import (create_pilot_manifest,export_pilot_manifest,
                                SOURCES,FIELDS_OUTPUT)

def write_source(path,source_name,amount,country):
    fields=list(FIELDS)
    records=[]
    for n in range(amount):
        record={field:'' for field in fields}
        record.update(id=source_name[:3].lower()+'-'+str(n),
            name='Research manufacturing candidate '+str(n),
            company='Reported Company '+str(n),
            country=country,city='City '+str(n),state='Region',
            registration_number='P'+str(1000+n),
            source=source_name,sector='Not independently verified')
        records.append([record[field] for field in fields])
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({'schema_version':'1.0','fields':fields,
                     'rows':records}),encoding='utf-8')
    return path

def fixture_catalogs(tmp_path):
    out={}
    for key,(relative,source,quota) in SOURCES.items():
        country={'fda_device':'US','ireland_leap':'IE','canada_npri':'CA'}[key]
        out[key]=write_source(tmp_path/relative,source,quota+6,country)
    return out

def test_generate_25_prospective_review_candidates_without_false_controls(tmp_path):
    catalogs=fixture_catalogs(tmp_path)
    rows=create_pilot_manifest(catalogs)
    assert len(rows)==25
    roles=Counter(r['cohort_role'] for r in rows)
    assert roles['retrospective_documented_disruption']==3
    assert roles['unverified_source_record']==22
    assert len({r['cohort_id'] for r in rows})==25
    assert all(r['identity_review']!='verified' for r in rows)
    assert all(r['pre_event_publication_validation']=='not_completed' for r in rows)
    assert all(r['outcome_status']!='no_loss' for r in rows)
    assert all('unknown_not_a_confirmed_no_event_control'==r['outcome_status']
               for r in rows if r['cohort_role']=='unverified_source_record')
    assert set(FIELDS_OUTPUT)==set(rows[0])
    out=tmp_path/'private-pilot.csv'
    status=export_pilot_manifest(out,catalog_root=tmp_path)
    assert status['cohort_rows']==25 and status['verified_comparison_controls']==0
    with out.open(encoding='utf-8',newline='') as stream:
        listed=list(csv.DictReader(stream))
    assert len(listed)==25 and 'selection_note' in listed[0]

def test_manifest_requires_all_official_populations_and_prevents_mislabeling(tmp_path):
    catalogs=fixture_catalogs(tmp_path)
    catalogs.pop('canada_npri')
    with pytest.raises(ValueError,match='Missing source catalog'):
        create_pilot_manifest(catalogs)
    catalogs=fixture_catalogs(tmp_path)
    item=catalogs['fda_device']
    doc=json.loads(item.read_text())
    doc['rows']=doc['rows'][:2]
    item.write_text(json.dumps(doc))
    with pytest.raises(ValueError,match='fewer eligible'):
        create_pilot_manifest(catalogs)
    with pytest.raises(ValueError,match='exactly 25'):
        create_pilot_manifest(fixture_catalogs(tmp_path),size=24)
