"""Public all-industry source progress must represent CI staging, never insured deployment."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "web" / "coordination" / "parallel-ingestion.json"
GITHUB = "https://github.com/jhennessy-pharm3r/FacilityTest/"


def load_sources():
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return doc, {source["id"]: source for lane in doc["lanes"] for source in lane["sources"]}


def test_reviewed_lane_manifest_is_complete_reconciled_and_never_claims_deployment():
    doc, sources = load_sources()
    assert doc["schema_version"] == "1.0"
    assert doc["review_status"] == "verified_source_qa_not_deployed"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", doc["as_of"])
    assert doc["coordination_issue"] == GITHUB + "issues/73"
    assert [lane["id"] for lane in doc["lanes"]] == ["A", "B", "C", "D"]
    assert len(sources) == sum(len(lane["sources"]) for lane in doc["lanes"]) == 20
    permitted = {"sample_ci_indexed", "ci_indexed", "staged_normalized",
                 "downloaded_qa", "access_blocked"}
    for lane in doc["lanes"]:
        assert lane["pr_url"].startswith(GITHUB + "pull/")
        assert lane["gate"]
        for row in lane["sources"]:
            assert row["stage"] in permitted
            assert row["name"] and row["scope"] and row["notes"]
            assert row["deployed"] == 0
            assert row["verified_insured_sites"] == 0
            assert row["run_url"].startswith(GITHUB + "actions/runs/")
            digest = row["source_sha256"]
            assert digest is None or re.fullmatch("[0-9a-f]{64}", digest)
            if row["stage"] == "access_blocked":
                assert all(row[key] is None for key in
                           ("scanned", "accepted", "rejected", "indexed_ci"))
            else:
                assert all(isinstance(row[key], int) and row[key] >= 0 for key in
                           ("scanned", "accepted", "rejected"))
                assert row["scanned"] == row["accepted"] + row["rejected"]
                assert row["accepted"] > 0
            if row["indexed_ci"] is not None:
                assert isinstance(row["indexed_ci"], int)
                assert 0 <= row["indexed_ci"] <= row["accepted"]
            if row["valid_coordinates"] is not None:
                assert 0 <= row["valid_coordinates"] <= row["accepted"]
    assert "private" not in MANIFEST.name


def test_specific_official_workflow_counts_are_not_fabricated_or_summed_as_sites():
    doc, rows = load_sources()
    assert len(rows) == 20
    assert (rows['fema_nfhl']['accepted'], rows['usfs_whp']['accepted'],
            rows['usfs_whp_classified']['accepted'], rows['usfs_whp_aggregates']['accepted']) == (34, 70, 70, 35304)
    assert (rows['epa_echo']['scanned'], rows['epa_echo']['accepted'],
            rows['epa_echo']['rejected'], rows['epa_echo']['valid_coordinates']) == (
            3229311, 3208008, 21303, 3146109)
    assert rows['epa_rcra']['accepted'] == rows['epa_rcra']['indexed_ci'] == 7022589
    assert rows['epa_tri']['accepted'] == rows['epa_tri']['indexed_ci'] == 3218093
    assert rows['epa_rmp_public']['accepted'] == rows['epa_rmp_public']['indexed_ci'] == 21853
    assert rows['uscg_nrc']['accepted'] == rows['uscg_nrc']['indexed_ci'] == 429122
    assert rows['uscg_nrc']['valid_coordinates'] == 62276
    assert rows['csb']['scanned'] == 675 and rows['csb']['accepted'] == 674
    assert rows['csb']['indexed_ci'] == 674 and rows['csb']['rejected'] == 1
    assert rows['phmsa_enforcement']['accepted'] == rows['phmsa_enforcement']['indexed_ci'] == 5089
    assert rows['phmsa_liquid']['accepted'] is None
    assert rows['eia861']['accepted'] == 12923 and rows['eia861']['rejected'] == 3
    assert rows['eia_b1']['accepted'] == 72 and rows['eia_b2']['accepted'] == 158
    assert rows['pnnl_outages']['accepted'] == rows['pnnl_outages']['indexed_ci'] == 2124183
    assert rows['odin_county']['accepted'] == 558 and rows['odin_feeds']['accepted'] == 157
    assert rows['baxter_bi']['accepted'] == 3 and rows['sec_bi']['accepted'] is None
    assert sum(rows[key]['accepted'] for key in ('eia861', 'eia_b1', 'eia_b2')) == 13153
    assert all(row['deployed'] == 0 and row['verified_insured_sites'] == 0
               for row in rows.values())
    assert doc['integration_status']['production_source_rows_deployed'] == 0
    assert doc['integration_status']['approved_insured_physical_site_links'] == 0
    assert doc['integration_status']['private_backend'] == 'not_provisioned'
    assert len(doc['integration_status']['missing_gates']) >= 3
    assert 'Publisher' in ' '.join(doc['caveats']) or 'Source blocks' in ' '.join(doc['caveats'])

def test_public_viewer_shows_progress_as_separate_source_qa_not_live_ingestions():
    api = (ROOT / "web" / "public-api.js").read_text(encoding="utf-8")
    view = (ROOT / "web" / "intelligence-ui.js").read_text(encoding="utf-8")
    status_publisher = (ROOT / "scripts" / "publish_source_status.py").read_text(encoding="utf-8")
    assert "parallel-ingestion.json" in api
    assert "validatedParallel(" in api
    assert "parallel_ingestion:snapshot.parallel_ingestion||null" in api
    assert "parallelIngestionPanel(parallel)" in view
    assert "CI indexed" in view and "App deployed" in view
    assert "Unknown source counts are not zero events" in view
    assert 'parallel-lane-filter' in view and 'parallel-stage-filter' in view
    assert 'parallel-visible-count' in view
    # Existing public source connectivity/ingestion snapshots remain independent.
    assert "PUBLIC_INGESTION_SOURCES" in status_publisher
    assert "NOAA Storm Events Details" in status_publisher
    assert "NOAA IncidentNews Selected Spills" in status_publisher

