import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from scripts.lane_a_whp_summaries_index import ACRES, SHEETS, normalize, run, sheet1_rows


def colref(i):
    result = ""
    i += 1
    while i:
        i, rem = divmod(i - 1, 26)
        result = chr(65 + rem) + result
    return result


def workbook(geography, name, identifier, state, missing_area=False):
    member, id_field, state_field, name_field = SHEETS[geography]
    cols = [id_field, name_field, state_field] + list(ACRES) + ["Total Acres"]
    row = [identifier, name, state] + ([None] * 8 if missing_area else [10, 20, 30, 40, 50, 60, 70, 280])
    def xml_row(number, values):
        cells = []
        for i, val in enumerate(values):
            if val is None:
                continue
            ref = colref(i) + str(number)
            if isinstance(val, str):
                cells.append('<c r="' + ref + '" t="inlineStr"><is><t>' +
                             escape(val) + '</t></is></c>')
            else:
                cells.append('<c r="' + ref + '"><v>' + str(val) + '</v></c>')
        return '<row r="' + str(number) + '">' + "".join(cells) + "</row>"
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
           '<sheetData>' + xml_row(3, cols) + xml_row(4, row) +
           '</sheetData></worksheet>')
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as w:
        w.writestr("xl/worksheets/sheet1.xml", xml)
    return member, out.getvalue()


def sourcezip():
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as out:
        for args in (
            ("county", "Fulton", "13121", "GA", False),
            ("state", "Georgia", 13, "GA", False),
            ("zip", "Example ZIP", "00029", "CA", True),
        ):
            name, raw = workbook(*args)
            out.writestr(name, raw)
    return z.getvalue()


class OfficialUSDAAggregateIndexTests(unittest.TestCase):
    def test_preserves_leading_zero_and_source_unknown(self):
        record = normalize("zip", {
            "ZIP": "00029", "STATE": "CA", "PO_NAME": "Tahoe",
            **{a: None for a in ACRES}, "Total Acres": None
        }, 4)
        self.assertEqual(record["native_geographic_id"], "00029")
        self.assertEqual(record["source_coverage"], "UNKNOWN_NO_AREA_VALUES")
        self.assertIsNone(record["total_acres"])
        record = normalize("state", {"STATE_FIPS": 2, "STATE_ABBR": "AK",
             "STATE_NAME": "Alaska", **{a: 0 for a in ACRES}, "Total Acres": 0}, 4)
        self.assertEqual(record["native_geographic_id"], "02")
        self.assertEqual(record["source_coverage"], "AGGREGATE_AREA_VALUES")

    def test_source_zip_index_and_sha_reconcile(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "source.zip"
            source.write_bytes(sourcezip())
            output = Path(d) / "index"
            m = run(source, output)
            self.assertTrue(m["reconciled"])
            self.assertEqual(m["source_records_read"], 3)
            self.assertEqual(m["normalized_records"], 3)
            self.assertEqual(m["source_coverage_missing"], 1)
            self.assertEqual(m["rejected_records"], 0)
            self.assertEqual(m["source_unique_geography_counts"],
                             {"county": 1, "state": 1, "zip": 1})
            self.assertEqual(m["source_zip_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
            db = sqlite3.connect(output / "whp2023-source-geographies.sqlite")
            self.assertEqual(db.execute(
                "SELECT native_geographic_id FROM whp2023_geography WHERE geography_type='zip'"
            ).fetchone()[0], "00029")
            self.assertEqual(db.execute("PRAGMA quick_check").fetchone()[0], "ok")
            db.close()

    def test_repeatable_normalized_sha_without_timestamp_in_rows(self):
        with tempfile.TemporaryDirectory() as d:
            source = Path(d) / "official.zip"
            source.write_bytes(sourcezip())
            a = run(source, Path(d) / "run_a")
            b = run(source, Path(d) / "run_b")
            self.assertEqual(a["normalized_gzip_sha256"], b["normalized_gzip_sha256"])

    def test_invalid_partial_area_rejected(self):
        area = {a: 1 for a in ACRES}
        area["H Acres"] = None
        with self.assertRaisesRegex(ValueError, "Partially"):
            normalize("county", {"GEOID": "01001", "STUSPS": "AL",
                      "NAME": "Autauga", **area, "Total Acres": 6}, 4)

    def test_sheet_csv_like_column_decoding(self):
        _, book = workbook("zip", "Example", "00029", "CA", missing_area=True)
        rows = list(sheet1_rows(book))
        self.assertEqual(rows[0][0], 3)
        self.assertEqual(rows[1][1][0], "00029")
        self.assertEqual(rows[1][1][2], "CA")
        self.assertEqual(len(rows[1][1]), 3)  # XML omits trailing empty cells


if __name__ == "__main__":
    unittest.main()
