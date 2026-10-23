"""Lane D install/verify/query/rollback tests use explicitly SYNTHETIC rows only."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest

from facilityrisk.lane_d.install_source_index import (
    SPECS, audit_source_bundle, install, query_install, resolve_current,
    sha256_file, verify_install,
)


def make_bundle(root, dataset):
    path = root / ("source-" + dataset)
    path.mkdir()
    source_sha = hashlib.sha256(b"SYNTHETIC_PUBLISHER_SOURCE_DO_NOT_COUNT").hexdigest()
    spec = SPECS[dataset]
    file = path / spec["database"]
    with sqlite3.connect(file) as db:
        if dataset == "eia861_2025":
            db.execute("""CREATE TABLE source_observations(
              ingestion_row_key TEXT PRIMARY KEY,source_kind TEXT,utility_id TEXT,
              state TEXT,county TEXT,source_member TEXT,source_sheet TEXT,
              source_row INTEGER,row_sha256 TEXT,original_row_json TEXT)""")
            db.executemany("INSERT INTO source_observations VALUES(?,?,?,?,?,?,?,?,?,?)", [
              ("a1","service_territory","0101","WA","Pierce",
               "Service_Territory_2025.xlsx","Counties_States",10,"rowsha1",
               json.dumps(["2025","0101","Utility One","WA","Pierce"])),
              ("a2","reliability","0101","WA",None,"Reliability_2025.xlsx",
               "Reliability_States",22,"rowsha2",
               json.dumps(["2025","0101","Utility One","WA","60.0"])),
            ])
            counts = {"reliability":1,"state_total":0,"service_territory":1}
            rejected = 1
            extra = {"reporting_year":2025}
        else:
            db.execute("""CREATE TABLE source_observations(
              source_row_key TEXT PRIMARY KEY,source_kind TEXT,dataset_year INTEGER,
              county_fips TEXT,state TEXT,county TEXT,reported_start TEXT,
              reported_duration_hours REAL,reported_mean_customers REAL,
              native_event_id TEXT,source_member TEXT,source_line_number INTEGER,
              source_row_sha256 TEXT,is_exact_duplicate_source_row INTEGER,
              duplicate_of_source_line INTEGER,raw_json TEXT)""")
            db.executemany("INSERT INTO source_observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",[
              ("p1","county_episode",2014,"01001","Alabama","Autauga",
               "2014-12-01T00:00:00",1.25,15.5,None,"episode.csv",2,"sha1",0,None,"{}"),
              ("p2","correlated_event",2014,"01001","Alabama","Autauga",
               "2014-12-01T00:00:00",1.25,15.5,"E1","event.csv",3,"sha2",1,2,"{}"),
            ])
            counts = {"county_episode":1,"correlated_event":1}
            rejected = 0
            extra = {"accepted_exact_duplicate_rows":1,
                     "distinct_source_table_row_contents":1,"source_coverage_years":[2014]}
        db.execute("CREATE INDEX idx_kind ON source_observations(source_kind)")
        db.commit()
    db_sha = sha256_file(file)
    manifest = {
        "source":spec["publisher_source"],"archive_sha256":source_sha,
        "accepted":2,"rejected":rejected,"source_rows_scanned":2+rejected,
        "accepted_by_source_kind":counts,
        "durable_backend_indexed":0,"deployed":0,
        **extra,
    }
    handoff = {
        spec["receipt_source_sha"]:source_sha,
        spec["receipt_db_sha"]:db_sha,
        spec["receipt_count"]:2,
        ("local_index_bytes" if dataset=="eia861_2025" else "staged_sqlite_bytes"):file.stat().st_size,
        "deployed":0,
    }
    (path/"manifest.json").write_text(json.dumps(manifest))
    (path/"coordinator_handoff.json").write_text(json.dumps(handoff))
    return path, source_sha, db_sha


class VerifiedSourceInstallTests(unittest.TestCase):
    def test_eia_install_query_repeat_and_verify_immutable(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            bundle,source_hash,db_hash=make_bundle(root,"eia861_2025")
            dest=root/"not-production"
            result=install(bundle,dest,"eia861_2025",source_hash,db_hash)
            self.assertTrue(result["verified_readonly_sqlite"])
            self.assertFalse(result["verified_application_deployment"])
            self.assertEqual(result["source_rows_accepted"],2)
            self.assertEqual(result["source_rows_rejected"],1)
            path,pointer=resolve_current(dest,"eia861_2025")
            self.assertEqual(sha256_file(path),db_hash)
            self.assertFalse(bool(path.stat().st_mode & stat.S_IWUSR))
            self.assertEqual(pointer["rows"],2)
            q=query_install(dest,"eia861_2025",state="WA",county="Pierce")
            self.assertEqual(q["data"]["source_territory_observations"],1)
            self.assertEqual(q["data"]["verified_serving_facility_utility_connections"],0)
            self.assertFalse(q["deployed_to_live_facility_app"])
            result2=install(bundle,dest,"eia861_2025",source_hash,db_hash)
            self.assertEqual(result["index_sha256"],result2["index_sha256"])
            self.assertEqual(len(list((dest/"eia861_2025"/"versions").iterdir())),1)
            with self.assertRaises(sqlite3.OperationalError):
                from facilityrisk.lane_d.install_source_index import readonly_connect
                with readonly_connect(path) as db:
                    db.execute("DELETE FROM source_observations")

    def test_pnnl_install_validates_duplicate_lineage_and_query(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            bundle,source_hash,db_hash=make_bundle(root,"pnnl_2014_2023")
            dest=root/"private-scratch"
            result=install(bundle,dest,"pnnl_2014_2023",source_hash,db_hash)
            self.assertEqual(result["source_rows_accepted"],2)
            self.assertEqual(result["exact_duplicate_rows_flagged"],1)
            q=query_install(dest,"pnnl_2014_2023",fips="01001",year=2014)
            self.assertEqual(q["data"]["candidate_counts"]["pnnl_historical_county_episodes"],1)
            self.assertTrue(all(not x["insured_facility_outage_verified"] for x in q["data"]["returned_findings"]))
            self.assertEqual(verify_install(dest,"pnnl_2014_2023")["index_sha256"],db_hash)

    def test_wrong_archive_hash_tampered_sqlite_or_row_count_cannot_install(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            bundle,source_hash,db_hash=make_bundle(root,"eia861_2025")
            target=root/"target"
            with self.assertRaisesRegex(ValueError,"Trusted raw-source"):
                install(bundle,target,"eia861_2025","f"*64)
            self.assertFalse((target/"eia861_2025"/"current.json").exists())
            (bundle/"manifest.json").write_text(
                (bundle/"manifest.json").read_text().replace('"accepted": 2','"accepted": 9'))
            with self.assertRaisesRegex(ValueError,"count"):
                install(bundle,target,"eia861_2025",source_hash)
            self.assertFalse((target/"eia861_2025"/"current.json").exists())
            bundle,source_hash,db_hash=make_bundle(root,"pnnl_2014_2023")
            with (bundle/SPECS["pnnl_2014_2023"]["database"]).open("ab") as db:
                db.write(b"NOT_AUTHENTICATED_SOURCE_INDEX")
            with self.assertRaisesRegex(ValueError,"SHA-256"):
                audit_source_bundle(bundle,"pnnl_2014_2023",source_hash)

    def test_failure_and_lock_do_not_replace_existing_pointer(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            bundle,source_hash,db_hash=make_bundle(root,"eia861_2025")
            dest=root/"dest"
            install(bundle,dest,"eia861_2025",source_hash)
            current=(dest/"eia861_2025"/"current.json")
            before=current.read_bytes()
            with self.assertRaises(ValueError):
                install(bundle,dest,"eia861_2025",source_hash,"f"*64)
            self.assertEqual(before,current.read_bytes())
            lock=current.parent/".install.lock"
            lock.write_text("OTHER PROCESS OWNS THIS LOCK")
            with self.assertRaises(FileExistsError):
                install(bundle,dest,"eia861_2025",source_hash)
            self.assertEqual(lock.read_text(),"OTHER PROCESS OWNS THIS LOCK")
            self.assertEqual(before,current.read_bytes())
            lock.unlink()

    def test_publisher_authenticated_live_odin_snapshot_install_and_review_guard(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            bundle=root/"first-party-odin"
            bundle.mkdir()
            source=hashlib.sha256(b"SYNTHETIC_ORNL_SOURCE_BYTES_NOT_REAL_OUTAGES").hexdigest()
            dbpath=bundle/"odin_direct_county_staging.sqlite"
            with sqlite3.connect(dbpath) as db:
                db.execute("""CREATE TABLE source_observations (
                    source_row_key TEXT PRIMARY KEY,
                    original_position INTEGER NOT NULL,
                    native_mrid TEXT,
                    native_county_fips TEXT NOT NULL,
                    native_eia_utility_id TEXT,
                    reported_start TEXT,
                    meters_affected INTEGER,
                    snapshot_utc TEXT NOT NULL,
                    is_exact_duplicate INTEGER NOT NULL,
                    duplicate_of_source_row INTEGER,
                    original_row_sha256 TEXT NOT NULL,
                    original_json TEXT NOT NULL)""")
                db.executemany("INSERT INTO source_observations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",[
                    ("a",1,None,"04013","803",None,10,"2026-10-23T18:00:00Z",0,None,"sha1","{}"),
                    ("b",2,None,"04013","803",None,10,"2026-10-23T18:00:00Z",1,1,"sha1","{}"),
                ])
            digest=sha256_file(dbpath)
            manifest={
                "source":"DOE_ORNL_ODIN_DIRECT_NON_AUTH_COUNTY",
                "original_raw_json_sha256":source,
                "normalized_accepted":2,"rejected":0,
                "original_https_download":True,
                "observations":{"exact_duplicate_source_rows_in_snapshot":1},
                "durable_backend_indexed":0,"deployed":0
            }
            handoff={
                "original_json_sha256":source,
                "staged_sqlite_sha256":digest,
                "indexed_source_rows":2,
                "staged_sqlite_bytes":dbpath.stat().st_size,
                "publisher_use_review_required":True,
                "deployed":0,
            }
            (bundle/"manifest.json").write_text(json.dumps(manifest))
            (bundle/"coordinator_handoff.json").write_text(json.dumps(handoff))
            installed=root/"private-check"
            result=install(bundle,installed,"odin_direct_public",source)
            self.assertEqual(result["source_rows_accepted"],2)
            self.assertEqual(result["exact_duplicate_rows_flagged"],1)
            q=query_install(installed,"odin_direct_public",fips="04013")
            self.assertEqual(q["data"]["candidate_counts"]["odin_firstparty_public_county_snapshot_raw_rows"],2)
            self.assertEqual(q["data"]["candidate_counts"]["odin_firstparty_exact_duplicate_rows_excluded"],1)
            self.assertFalse(q["deployed_to_live_facility_app"])
            pointer=(installed/"odin_direct_public"/"current.json").read_bytes()
            manifest["original_https_download"]=False
            (bundle/"manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,"authenticated official HTTPS"):
                install(bundle,installed,"odin_direct_public",source)
            self.assertEqual((installed/"odin_direct_public"/"current.json").read_bytes(),pointer)
            with self.assertRaises(ValueError):
                query_install(installed,"odin_direct_public",fips="04013",year=2023)

    def test_unauthorized_source_family_or_symlink_source_disallowed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            bundle,source_hash,db_hash=make_bundle(root,"eia861_2025")
            with self.assertRaises(ValueError):
                install(bundle,root/"dest","unknown",source_hash)
            link=root/"fake-source"
            try:
                link.symlink_to(bundle,target_is_directory=True)
            except (OSError,NotImplementedError):
                return
            with self.assertRaisesRegex(ValueError,"symlink"):
                install(link,root/"dest","eia861_2025",source_hash)


if __name__ == "__main__":
    unittest.main()
