"""Private source handoff must remain outside public repo and preserve checksums."""
import hashlib
import json
import sqlite3
import pytest
from scripts.lane_c_private_handoff import private_bundle,sha

def test_private_bundle_preserves_original_normalized_bytes_and_ci_counts(tmp_path):
    root=tmp_path/"public-repository"
    root.mkdir()
    raw=tmp_path/"source.xlsx"
    raw.write_bytes(b"original-agency-raw-source-identity")
    normalized=tmp_path/"normalized.csv.gz"
    normalized.write_bytes(b"normalized-private-source-rows")
    report=tmp_path/"source-manifest.json"
    report.write_text(json.dumps({"raw_sha256":sha(raw),"normalized_sha256":sha(normalized),"accepted_rows":2}))
    db=tmp_path/"source-index.sqlite"
    with sqlite3.connect(db) as conn:
        conn.executescript("""
          CREATE TABLE source_incidents (source TEXT NOT NULL);
          INSERT INTO source_incidents VALUES('nrc_2025'),('nrc_2025');
          CREATE TABLE lane_c_review_candidates (source_id TEXT);
          INSERT INTO lane_c_review_candidates VALUES ('a');
        """)
    secure=tmp_path/"secure-private-handoff"
    result=private_bundle(db,[("nrc_2025",normalized,report)],
                          {"nrc_2025":raw},secure,repo_root=root)
    assert result["source_count"]==1
    assert result["records_exported_to_private_local_bundle"]==2
    assert result["review_candidate_pairs"]==1
    assert result["sqlite_quick_check"]=="ok"
    assert result["production_indexed"]==0
    assert (secure/"originals/nrc_2025.xlsx").read_bytes()==raw.read_bytes()
    assert (secure/"normalized/nrc_2025.csv.gz").read_bytes()==normalized.read_bytes()
    assert json.loads((secure/"private-bundle-manifest.json").read_text())["app_deployed"]==0
    with pytest.raises(ValueError,match="exists"):
        private_bundle(db,[("nrc_2025",normalized,report)],
                       {"nrc_2025":raw},secure,repo_root=root)

def test_private_bundle_rejects_public_destination(tmp_path):
    repo=tmp_path/"repo"
    repo.mkdir()
    with pytest.raises(ValueError,match="outside the repository"):
        private_bundle(tmp_path/"missing.db",[],{},repo/"data",repo_root=repo)

def test_private_bundle_checksum_failure_cleans_partial_files(tmp_path):
    repo=tmp_path/"repo"
    repo.mkdir()
    raw=tmp_path/"raw.xlsx"
    raw.write_bytes(b"raw-data")
    gz=tmp_path/"normalized.csv.gz"
    gz.write_bytes(b"normalized")
    manifest=tmp_path/"source.json"
    manifest.write_text(json.dumps({"raw_sha256":"bad_sha","normalized_sha256":sha(gz),"accepted_rows":1}))
    db=tmp_path/"db.sqlite"
    with sqlite3.connect(db) as conn:
        conn.executescript("""CREATE TABLE source_incidents(source TEXT);
           INSERT INTO source_incidents VALUES('nrc_2025');
           CREATE TABLE lane_c_review_candidates(source_id TEXT);
        """)
    dest=tmp_path/"private-copy"
    with pytest.raises(ValueError,match="checksum mismatch"):
        private_bundle(db,[("nrc_2025",gz,manifest)],{"nrc_2025":raw},dest,repo_root=repo)
    assert not dest.exists()
