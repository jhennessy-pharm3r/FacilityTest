"""Lane C installer must install a verified private immutable release, query and roll back.

These use fixtures for negative gates; the official-source workflow executes
the same installer against the real 429,796-row bundle independently.
"""
from __future__ import annotations
import json
from pathlib import Path
import sqlite3

import pytest

from scripts.lane_c_install import (
    active_status, install, query, rollback, verify_bundle, _readonly_db
)
from scripts.lane_c_private_handoff import private_bundle, sha

def _bundle(tmp_path):
    repo=tmp_path/"public-repo"
    repo.mkdir()
    raw=tmp_path/"official-CY25.xlsx"
    raw.write_bytes(b"official-test-original")  # synthetic ONLY for regression
    normalized=tmp_path/"normalized.csv.gz"
    normalized.write_bytes(b"normalized-test-source")
    manifest=tmp_path/"source.json"
    manifest.write_text(json.dumps({
        "year":2025,"accepted_rows":2,"rejected_rows":0,
        "raw_sha256":sha(raw),"normalized_sha256":sha(normalized)
    }))
    db=tmp_path/"source.sqlite"
    with sqlite3.connect(db) as conn:
        conn.executescript("""CREATE TABLE source_incidents (
         source TEXT NOT NULL,source_id TEXT NOT NULL,publisher_native_id TEXT NOT NULL,
         source_vintage TEXT NOT NULL,incident_date TEXT,city TEXT,state TEXT,
         latitude REAL,longitude REAL,evidence_status TEXT NOT NULL,
         site_link_status TEXT NOT NULL,source_url TEXT NOT NULL,source_json TEXT NOT NULL,
         PRIMARY KEY(source,source_id));
         CREATE TABLE lane_c_review_candidates (
         nrc_source TEXT,nrc_source_id TEXT,csb_source TEXT,csb_source_id TEXT,
         match_rule TEXT,status TEXT NOT NULL);
        """)
        for seq,date,state in [("0001","2025-02-03","TX"),("0002","2025-04-05","OH")]:
            conn.execute("INSERT INTO source_incidents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(
                "nrc_2025",seq,seq,"2025",date,"Example City",state,
                None,None,"NRC_initial_notification_unverified",
                "candidate_only_not_matched",
                "https://nrc.uscg.mil/FOIAFiles/CY25.xlsx",
                json.dumps({"source_id":seq})))
        conn.execute("INSERT INTO lane_c_review_candidates VALUES(?,?,?,?,?,?)",
                     ("nrc_2025","0001","csb","csb:2026-09-01:4",
                      "exact_reported_day_city_state_company_text",
                      "review_candidate_not_corrob"))
    bundle=tmp_path/"private-handoff"
    private_bundle(db,[("nrc_2025",normalized,manifest)],
                   {"nrc_2025":raw},bundle,repo_root=repo)
    root=tmp_path/"authorized-private-release-store"
    root.mkdir(mode=0o700)
    return repo,root,bundle

def test_verified_bundle_installs_and_readonly_source_query(tmp_path):
    repo,root,bundle=_bundle(tmp_path)
    checked=verify_bundle(bundle)
    assert checked["total_indexed_source_observations"]==2
    assert checked["review_candidate_pairs"]==1
    result=install(bundle,root,release_id="official-2025-a",repo_root=repo)
    assert result["total_indexed_source_observations"]==2
    assert result["authenticated_service_connected"] is False
    assert result["app_deployed_records"]==0
    assert result["persisted_on_configured_private_mount"] is True
    assert active_status(root,repo_root=repo)["active_release_id"]=="official-2025-a"
    assert (root/"releases/official-2025-a/indexes/lane-c-source.sqlite").exists()
    page=query(root,source="nrc_2025",page_size=1,repo_root=repo)
    assert page["total"]==2
    assert len(page["items"])==1
    assert page["items"][0]["source_id"]=="0002"
    assert page["items"][0]["site_link_status"]=="candidate_only_not_matched"
    assert "source_json" not in page["items"][0]
    assert query(root,source="nrc_2025",state="OH",repo_root=repo)["total"]==1
    assert query(root,source="nrc_2025",since="2025-03-01",repo_root=repo)["total"]==1
    assert query(root,source="nrc_2025",page=5,page_size=1,repo_root=repo)["items"]==[]
    with _readonly_db(root/"releases/official-2025-a/indexes/lane-c-source.sqlite") as conn:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM source_incidents")

    again=install(bundle,root,release_id="official-2025-a",repo_root=repo)
    assert again["installation"]=="ALREADY_INSTALLED_CHECKSUM_VERIFIED"
    install(bundle,root,release_id="official-2025-b",repo_root=repo)
    assert active_status(root,repo_root=repo)["active_release_id"]=="official-2025-b"
    assert rollback(root,"official-2025-a",repo_root=repo)["active_release_id"]=="official-2025-a"
    assert active_status(root,repo_root=repo)["total_indexed_source_observations"]==2

def test_failed_checksum_does_not_change_current_active_release(tmp_path):
    repo,root,bundle=_bundle(tmp_path)
    install(bundle,root,release_id="good",repo_root=repo)
    p=bundle/"originals/nrc_2025.xlsx"
    p.write_bytes(p.read_bytes()+b"tamper")
    with pytest.raises(ValueError,match="checksum"):
        install(bundle,root,release_id="bad",repo_root=repo)
    assert active_status(root,repo_root=repo)["active_release_id"]=="good"
    assert not (root/"releases/bad").exists()

def test_unsafe_bundle_and_repository_destination_fail_closed(tmp_path):
    repo,root,bundle=_bundle(tmp_path)
    with pytest.raises(ValueError,match="outside repository"):
        install(bundle,repo,repo_root=repo)
    with pytest.raises(ValueError,match="Unsafe release"):
        install(bundle,root,release_id="../evil",repo_root=repo)
    with pytest.raises(ValueError,match="Unknown source"):
        # Need an active release to reach namespace check
        install(bundle,root,release_id="good",repo_root=repo)
        query(root,source="nrc_1999",repo_root=repo)
    with pytest.raises(ValueError,match="paging"):
        query(root,source="nrc_2025",page_size=10000,repo_root=repo)
    with pytest.raises(ValueError,match="ISO"):
        query(root,source="nrc_2025",since="2025' OR 1=1",repo_root=repo)
    with pytest.raises(ValueError,match="Unsafe rollback"):
        rollback(root,"../../etc/passwd",repo_root=repo)

def test_world_readable_installer_directory_rejected(tmp_path):
    repo,root,bundle=_bundle(tmp_path)
    root.chmod(0o755)
    with pytest.raises(ValueError,match="not be accessible"):
        install(bundle,root,repo_root=repo)
