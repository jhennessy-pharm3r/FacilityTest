"""Lane D fixture tests. Synthetic rows are never real-source counts."""
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

from openpyxl import Workbook
from facilityrisk.lane_d.ingest_eia861 import normalize, process_sheet, run, table_rows


def workbook_bytes(sheets):
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets:
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    output = io.BytesIO()
    wb.save(output)
    wb.close()
    return output.getvalue()


class LaneDTests(unittest.TestCase):
    def test_ids_duplicates_null_and_provenance(self):
        text = ("Metadata\nUtility Number,Utility Name,State,SAIDI With Major Events,SAIFI\n"
                "101,Utility One,ME,42.5,1.2\n"
                "101,Utility One,ME,42.5,1.2\n"
                "102,Utility Two,NY,,\n"
                "not-an-id,Invalid,NY,9,2\n")
        accepted, rejected, dup, null = normalize("Reliability_2025.csv", text.encode(), 2025)
        self.assertEqual((len(accepted), len(rejected), dup, null), (2, 2, 1, 1))
        self.assertEqual(accepted[0]["source_utility_id"], "101")
        self.assertEqual(accepted[0]["facility_match_status"], "NOT_ASSESSED")
        self.assertEqual({r["reason"] for r in rejected}, {"duplicate_exact_row", "invalid_utility_id"})

    def test_realistic_workbook_separate_sheets_and_repeated_headings(self):
        header = [
            ["Utility Characteristics", None, None, None, None, "IEEE Standard", None, "Other Standard"],
            ["", None, None, None, None, "All Events With MED", None, "Without MED"],
            ["Data Year", "Utility Number", "Utility Name", "State", "Ownership",
             "SAIDI (minutes per year)", "SAIDI (minutes per year)", "SAIDI (minutes per year)"],
        ]
        data = [
            ["2025", "00012", "Public Power", "MA", "Municipal", 105.2, 44.0, 110.4],
            ["2025", "00012", "Public Power", "NY", "Municipal", 99.0, 22.0, 100.1],
        ]
        totals = [
            ["Characteristics", None, "IEEE Standard", None],
            ["", "", "All Events With MED", None],
            ["Data Year", "State", "SAIDI (minutes per year)", "SAIFI (times per year)"],
            ["2025", "MA", 12.0, 0.7],
        ]
        archive = workbook_bytes([("Reliability_States", header + data),
                                  ("State Totals", totals)])
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "f8612025.zip"
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("Reliability_2025.xlsx", archive)
            result = run(2025, Path(t) / "output", path)
            self.assertEqual(result["accepted_by_source_kind"]["reliability"], 2)
            self.assertEqual(result["accepted_by_source_kind"]["state_total"], 1)
            self.assertEqual(result["rejected"], 0)
            self.assertEqual(result["unique_reliability_utility_ids"], 1)
            self.assertEqual(result["local_index"]["records"], 3)
            self.assertEqual(result["local_index"]["integrity_check"], "ok")
            self.assertEqual(result["durable_backend_indexed"], 0)
            self.assertEqual(result["deployed_rows"], 0)
            self.assertEqual(result["verified_facility_matches"], 0)
            with (Path(t)/"output"/"eia861_reliability.jsonl").open() as f:
                record = json.loads(next(f))
            self.assertEqual(record["source_utility_id"], "00012")
            self.assertEqual(record["raw_cells"][5:8], ["105.2", "44.0", "110.4"])
            schema = next(s for s in result["sheets"] if s["source_sheet"] == "Reliability_States")
            self.assertEqual(len(schema["columns"]), 8)
            self.assertEqual(schema["columns"][5]["group"], "IEEE Standard")
            self.assertEqual(schema["columns"][7]["group"], "Other Standard")
            self.assertNotEqual(schema["columns"][5]["column_1based"], schema["columns"][6]["column_1based"])

    def test_county_territory_is_only_provider_candidate(self):
        reliability = ("Data Year,Utility Number,Utility Name,State,SAIDI\n"
                       "2025,101,Public Power,ME,24\n")
        territory = ("Data Year,Utility Number,Utility Name,State,County\n"
                     "2025,101,Public Power,ME,Cumberland\n"
                     "2025,101,Public Power,ME,York\n"
                     "2024,101,Public Power,ME,Old County\n")
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/"official.zip"
            with zipfile.ZipFile(path,"w") as z:
                z.writestr("Reliability_2025.csv",reliability)
                z.writestr("Service_Territory_2025.csv",territory)
            out=Path(t)/"out"
            result=run(2025,out,path)
            self.assertEqual(result["accepted_by_source_kind"], {"reliability": 1, "state_total": 0, "service_territory": 2})
            self.assertEqual(result["rejection_reasons"], {"invalid_reporting_year": 1})
            self.assertEqual(result["local_index"]["by_source_kind"]["service_territory"], 2)
            territory_rows=[json.loads(v) for v in (out/"eia861_service_territory.jsonl").read_text().splitlines()]
            self.assertEqual({v["reported_county"] for v in territory_rows}, {"Cumberland", "York"})
            self.assertTrue(all(v["facility_match_status"] == "NOT_ASSESSED" for v in territory_rows))
            self.assertTrue(all(v["evidence_type"] == "COUNTY_SERVICE_TERRITORY_CANDIDATE" for v in territory_rows))
            with sqlite3.connect(out/"lane_d_eia861_staging.sqlite") as db:
                rows=db.execute("SELECT county FROM source_observations WHERE utility_id='101' AND source_kind='service_territory' ORDER BY county").fetchall()
            self.assertEqual(rows,[("Cumberland",),("York",)])

    def test_invalid_state_year_and_duplicate_rows(self):
        rows = [
            ["Data Year", "Utility Number", "State", "SAIDI", "SAIFI"],
            ["2025","10","TX","100","2"],
            ["2025","10","TX","100","2"],
            ["2024","10","TX","101","3"],
            ["2025","12","Texas","10","1"],
        ]
        ok,bad,stat=process_sheet("Reliability_2025.csv","CSV",rows,2025,"reliability")
        self.assertEqual((len(ok),len(bad),stat["exact_duplicates"]),(1,3,1))
        self.assertEqual({r["reason"] for r in bad},{"duplicate_exact_row","invalid_reporting_year","invalid_state"})

    def test_missing_reliability_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as t:
            source=Path(t)/"sample.zip"
            with zipfile.ZipFile(source,"w") as z:
                z.writestr("Utility_2025.csv","Utility Number\n10\n")
            with self.assertRaisesRegex(ValueError,"No EIA-861 reliability workbook"):
                run(2025, Path(t)/"out", source)

    def test_worksheet_id_header_must_have_metrics(self):
        rows=[
            ["Notes about respondent","", ""],
            ["Data Year","Utility Number","State"],
            ["2025","101","ME"],
        ]
        _, _, stats=process_sheet("Reliability_2025.xlsx","Notes",rows,2025,"reliability")
        self.assertEqual(stats.get("skipped_reason"),"no_matching_header")


if __name__ == "__main__":
    unittest.main()
