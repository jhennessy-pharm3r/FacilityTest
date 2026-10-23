"""EIA DOE-417-derived EPM published event table fixture tests."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from facilityrisk.lane_d.ingest_electric_events import parse_events, run

HEADER = (
    "Year","Month","Event Date and Time","Restoration Date and Time",
    "Duration","Utility/Power Pool","NERC Region","Area Affected",
    "Type of Disturbance","Loss (megawatts)","Number of Customers Affected",
)


def table_html(rows):
    tr = ["<tr>" + "".join("<th>"+x+"</th>" for x in HEADER) + "</tr>"]
    tr.extend("<tr>" + "".join("<td>"+x+"</td>" for x in row) + "</tr>" for row in rows)
    return ("<html><body><table><tr><td>Navigation</td></tr></table>"
            "<table>" + "".join(tr) + "</table></body></html>").encode()


class DisturbanceTests(unittest.TestCase):
    def test_parse_counts_and_uncertainty(self):
        raw=table_html([
            ("2024","1","01/09/2024 12:45 AM","01/10/2024 4:41 PM","39 Hours, 56 Minutes",
             "Utility A", "WECC", "WA: King County;", "Loss of electric service to more than 50,000 customers", "Unknown", "75180"),
            ("2024","1","01/10/2024 9:00 AM",". .",". Hours, . Minutes",
             "Utility B","N/A","State of WA;","Physical threat, no interruption confirmed","Unknown","Unknown"),
            ("2023","1","01/03/2023 1:00 AM",". .","", "Outdated Utility","N/A","WA:","Incident","", ""),
        ])
        accepted,bad,columns=parse_events(raw,"b1")
        self.assertEqual((len(accepted),len(bad)),(2,1))
        self.assertEqual(len(columns),11)
        self.assertEqual(accepted[0]["customers_affected_number"],75180)
        self.assertIsNone(accepted[0]["loss_mw_number"])
        self.assertTrue(accepted[0]["reported_service_loss_category"])
        self.assertFalse(accepted[1]["reported_service_loss_category"])
        self.assertFalse(accepted[0]["site_specific_outage_verified"])
        self.assertIsNone(accepted[0]["source_event_id"])
        self.assertEqual(bad[0]["reason"],"incorrect_or_missing_reporting_year")
        self.assertNotEqual(accepted[0]["derived_source_row_key"],accepted[1]["derived_source_row_key"])

    def test_eia_b2_year_and_stage_index(self):
        raw=table_html([
            ("2023","2","02/02/2023 10:00 AM","02/02/2023 2:00 PM","4 Hours, 0 Minutes",
             "Regional Operator","RFC","PA: County X;","Reported disturbance","0","0"),
        ])
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            path=root/"source.html"
            path.write_bytes(raw)
            result=run("b2",path,root/"stage")
            self.assertEqual((result["accepted_source_rows"],result["rejected_source_rows"],result["indexed_local_staging"]), (1,0,1))
            self.assertEqual(result["verified_facility_outages"],0)
            self.assertEqual(result["indexed_durable_backend"],0)
            self.assertEqual(result["coverage"],"ANNUAL_2023")
            with sqlite3.connect(root/"stage"/"events_staging.sqlite") as c:
                self.assertEqual(c.execute("SELECT COUNT(*) FROM source_events").fetchone()[0],1)
            event=json.loads((root/"stage"/"events.jsonl").read_text().strip())
            self.assertEqual(event["reported_start"],"02/02/2023 10:00 AM")

    def test_fails_closed_when_event_table_missing(self):
        with self.assertRaisesRegex(ValueError,"Expected one official event table"):
            parse_events(b"<html><table><tr><td>fake</td></tr></table></html>","b1")

    def test_fails_closed_when_table_duplicated(self):
        html=table_html([("2024","1","01/01/2024 1:00 AM",". .","",
                          "Operator","N/A","NY","Incident","0","0")])
        # Two exact event tables in one document must be reviewed, never double counted.
        duplicated=html.replace(b"</body>",b"<table><tr>"+b"".join(b"<th>"+x.encode()+b"</th>" for x in HEADER)+b"</tr></table></body>")
        with self.assertRaisesRegex(ValueError,"Expected one official event table"):
            parse_events(duplicated,"b1")


if __name__ == "__main__":
    unittest.main()
