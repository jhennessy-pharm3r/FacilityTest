"""The 25-FRS pilot is a *source identity* QA, never 25 insured sites."""
import json
import sqlite3
import pytest
from facilityrisk.universal_registry import import_records
from scripts.screen_25_real_frs_source_sites import select_cohort,run

def _frs_fixture(tmp_path):
    p=tmp_path/"epa-official-source-identity-FIXTURE.sqlite"
    with sqlite3.connect(p) as db:
        db.row_factory=sqlite3.Row
        sources=[]
        for n in range(30):
            sources.append({
              "source_identifier":str(110000100000+n),
              "name":f"Synthetic Facility {n}",
              "company":f"Synthetic Industry {n//3}",
              "address":f"{n} Synthetic Address Road",
              "city":f"Test City {n//3+1}",
              "state":["TX","MA","CA","FL","NC","OH","PA","NY","NJ","IL"][n//3],
              "country":"US",
              "industry":f"Test NAICS Sector {n//3}",
              "latitude":25+(n//3)*2,
              "longitude":-100+(n//3)*2,
            })
        import_records(db,"EPA_FRS",sources,
                       "https://www.epa.gov/frs",
                       vintage="SYNTHETIC_FIXTURE_NO_REAL_SITES")
    return p

def test_selection_uses_exact_source_id_and_sufficient_sector_and_state_diversity(tmp_path):
    f=_frs_fixture(tmp_path)
    items,summary=select_cohort(f)
    assert len(items)==25
    assert len({r["source_identifier"] for r in items})==25
    assert summary["different_reported_industries"]>=5
    assert summary["different_reported_states"]>=5
    assert all(x["site_status"]=="source_observation" for x in items)
    assert all(x["coordinate_quality"]=="source_point_unverified" for x in items)

def test_25_site_real_source_gate_rejects_synthetic_only_uninstalled_nrc(tmp_path):
    f=_frs_fixture(tmp_path)
    with pytest.raises(ValueError,match="(?i)(missing|requires validated|not configured|absent)"):
        run(f,tmp_path/"absent-industrial-index",tmp_path/"aggregate.json")
    assert not (tmp_path/"aggregate.json").exists()

def test_malformed_official_source_index_does_not_claim_25_validated_sites(tmp_path):
    p=tmp_path/"bad.sqlite"
    with sqlite3.connect(p) as db:db.execute("CREATE TABLE incomplete(x)")
    with pytest.raises(ValueError,match="source index tables missing"):
        select_cohort(p)
