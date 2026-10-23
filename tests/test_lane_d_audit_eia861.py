"""Independent EIA-861 raw-to-index gate: synthetic corruption tests only."""
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from openpyxl import Workbook
from facilityrisk.lane_d.ingest_eia861 import run
from facilityrisk.lane_d.audit_eia861 import audit


class SourceChainAuditorTests(unittest.TestCase):
    def source(self, root):
        original = root/"official.zip"
        wb=Workbook()
        sheet=wb.active
        sheet.title="Reliability_States"
        sheet.append(["Utility Characteristics",None,None,None,"IEEE Standard"])
        sheet.append(["",None,None,None,"All Events With Major Event Days"])
        sheet.append(["Data Year","Utility Number","Utility Name","State","SAIDI (minutes per year)"])
        sheet.append([2025,17,"First Utility","ME",42.5])
        sheet.append([2025,17,"First Utility","NY",39.7])
        sheet.append([2024,18,"Other Utility","MA",21.0])
        buff=io.BytesIO()
        wb.save(buff)
        wb.close()
        with zipfile.ZipFile(original,"w") as z:
            z.writestr("Reliability_2025.xlsx",buff.getvalue())
            z.writestr("Service_Territory_2025.csv",
                       "Data Year,Utility Number,Utility Name,State,County\n"
                       "2025,17,First Utility,ME,Cumberland\n"
                       "2025,17,First Utility,ME,York\n")
        return original

    def test_verify_source_row_evidence_and_staging(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            archive=self.source(root)
            output=root/"normalized"
            m=run(2025,output,archive)
            a=audit(archive,output)
            self.assertEqual(a["actual_accepted"],{"reliability":2,"state_total":0,"service_territory":2})
            self.assertEqual(a["actual_rejected"],1)
            self.assertEqual(a["rejected_reasons"],{"invalid_reporting_year":1})
            self.assertEqual(a["distinct_state_codes"],2)
            self.assertEqual(a["distinct_state_county_pairs"],2)
            self.assertEqual(a["local_index_integrity_check"],"ok")
            self.assertEqual(a["source_or_index_mismatches"],0)
            self.assertEqual(a["physical_insured_site_matches_verified"],0)
            self.assertEqual(a["deployed"],0)

    def test_modified_accepted_row_cannot_pass_origin_verification(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            archive=self.source(root)
            output=root/"normalized"
            run(2025,output,archive)
            path=output/"eia861_reliability.jsonl"
            records=[json.loads(line) for line in path.read_text().splitlines()]
            records[0]["raw_cells"][4]="99999"
            path.write_text("".join(json.dumps(item)+"\n" for item in records))
            with self.assertRaisesRegex(ValueError,"does not match original"):
                audit(archive,output)

    def test_changed_original_zip_detected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            archive=self.source(root)
            output=root/"normalized"
            run(2025,output,archive)
            with zipfile.ZipFile(archive,"a") as z:
                z.writestr("unexpected.txt","new")
            with self.assertRaisesRegex(ValueError,"archive hash"):
                audit(archive,output)


if __name__=="__main__":
    unittest.main()
