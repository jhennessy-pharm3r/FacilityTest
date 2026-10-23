"""Source-native EIA reporting utility ID concordance must never imply property service."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from facilityrisk.lane_d.audit_native_eia_ids import audit_native_utility_identity


class SourceIdentityCrosscheck(unittest.TestCase):
    def populate(self,eia,odin):
        with sqlite3.connect(eia) as db:
            db.execute("""CREATE TABLE source_observations (
                utility_id TEXT,source_kind TEXT,state TEXT,county TEXT,
                original_row_json TEXT)""")
            db.executemany("INSERT INTO source_observations VALUES (?,?,?,?,?)",[
                ("803","service_territory","AZ","Maricopa",json.dumps(["2025","803","Arizona Public Service Co","Y","AZ","Maricopa"])),
                ("803","reliability","AZ",None,json.dumps(["2025","803","Arizona Public Service Co","AZ","Investor","120"])),
                ("500","service_territory","NY","Bronx",json.dumps(["2025","500","Independent Utility","Y","NY","Bronx"])),
                ("1500","reliability","MA",None,json.dumps(["2025","1500","Massachusetts utility","MA","Other","1"])),
            ])
        with sqlite3.connect(odin) as db:
            db.execute("CREATE TABLE source_observations (native_eia_utility_id TEXT,native_county_fips TEXT,original_json TEXT)")
            def name(utility):
                return json.dumps({"names":[
                    {"name":utility,"nameType":"UtilityName","nameTypeAuthority":"EIA"}]})
            db.executemany("INSERT INTO source_observations VALUES (?,?,?)",[
                ("803","04013",name("ARIZONA PUBLIC SERVICE CO")),
                ("803","04025",name("ARIZONA PUBLIC SERVICE CO")),
                ("500","36005",name("Some Other Name")),
                ("1500","25025",name("Massachusetts utility")),
                ("999","04013",name("Not present 2025")),
                (None,"04013",name("Unknown utility")),
            ])
    def test_identifiers_and_original_names_only_no_site_mapping(self):
        with tempfile.TemporaryDirectory() as t:
            eia=Path(t)/"eia.db";odin=Path(t)/"odin.db"
            self.populate(eia,odin)
            report=audit_native_utility_identity(eia,odin)
            self.assertEqual(report["odin_public_county_status_rows"],6)
            self.assertEqual(report["odin_native_utility_id_missing_rows"],1)
            self.assertEqual(report["odin_distinct_source_native_eia_utility_ids"],4)
            self.assertEqual(report["native_id_matches"],3)
            self.assertEqual(report["publisher_native_id_link_status"],{
                "in_both":1,"in_reliability_only":1,
                "in_territory_only":1,"missing_from_eia_2025":1})
            self.assertEqual(report["source_utility_name_disagreement_candidates"],1)
            link=next(r for r in report["links"] if r["native_eia_utility_id"]=="803")
            self.assertEqual(link["odin_county_fips_count"],2)
            self.assertEqual(link["eia_territory_county_text_rows"],1)
            self.assertFalse(link["verified_insured_site_serving_utility"])
            self.assertFalse(link["verified_insured_site_power_outage"])
            self.assertEqual(report["verified_physical_facility_power_provider_assignments"],0)
            self.assertEqual(report["deployed"],0)
    def test_no_fuzzy_identity_link_or_backfill(self):
        with tempfile.TemporaryDirectory() as t:
            eia=Path(t)/"eia.db";odin=Path(t)/"odin.db"
            self.populate(eia,odin)
            report=audit_native_utility_identity(eia,odin)
            self.assertEqual(next(v for v in report["links"] if v["native_eia_utility_id"]=="999")["eia_2025_availability"],"missing_from_eia_2025")
            self.assertTrue(next(v for v in report["links"] if v["native_eia_utility_id"]=="500")["publisher_name_review_needed"])
            self.assertEqual(sum(v["odin_observation_rows"] for v in report["links"])+report["odin_native_utility_id_missing_rows"],report["odin_public_county_status_rows"])
    def test_missing_backend_files_fail_closed(self):
        with self.assertRaises(FileNotFoundError):
            audit_native_utility_identity("/missing/eia.sqlite","/missing/odin.sqlite")


if __name__=="__main__":
    unittest.main()
