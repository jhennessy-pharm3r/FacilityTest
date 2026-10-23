"""PNNL original CSV archive regression; synthetic rows deliberately excluded from live counts."""
import csv
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile
from facilityrisk.lane_d.ingest_pnnl_county_outages import COLUMNS, normalize,validate_row,typed_metrics


def rows(kind,year):
    if kind=="county_episode":
        return [
            ["1001","Alabama","Autauga",f"{year}-12-01 00:45:00","1.25","25","44","31.1"],
            ["12086","Florida","Miami-Dade",f"{year}-01-02 09:00:00","0.25","99","999","400.5"],
        ]
    if kind=="state_month_aggregate":
        return [["Alabama",str(year),"0","33","26.5","51208.25"],
                ["Alabama",str(year),"1","0","0","0"]]
    base=["100","Alabama",f"{year}-12-01 00:30:00",f"{year}-12-01 02:15:00",
          "Weather","1001","Alabama","Autauga",f"{year}-12-01 00:45:00",
          "1.25"]
    if kind=="correlated_event":
        base+= [f"{year}-12-01 02:00:00"]
    return [base+["25","44","31.1"]]


def sample_zip(path,years=(2014,)):
    with zipfile.ZipFile(path,"w") as z:
        for year in years:
            for kind,cols in COLUMNS.items():
                if kind=="county_episode":
                    name=f"eaglei_outages_{year}_merged.csv"
                elif kind=="state_month_aggregate":
                    name=f"eaglei_outages_{year}_group.csv"
                elif kind=="correlated_event":
                    name=f"eaglei_outages_with_events_{year}.csv"
                elif kind=="correlation_8h_sensitivity":
                    name=f"eaglei_outages_with_events_{year}_8_hours_lag.csv"
                else:
                    name=f"eaglei_outages_with_events_{year}_24_hours_lag.csv"
                out=io.StringIO(newline="")
                w=csv.writer(out)
                w.writerow(cols)
                w.writerows(rows(kind,year))
                z.writestr("Outage_Dataset/"+name,out.getvalue())


class PNNLTests(unittest.TestCase):
    def test_fips_padding_native_id_and_sensitivity_separation(self):
        fips,start,eid,num=validate_row(
            dict(zip(COLUMNS["correlated_event"],rows("correlated_event",2014)[0])),
            "correlated_event",2014)
        self.assertEqual((fips,eid,start),("01001","100","2014-12-01T00:45:00"))
        self.assertEqual(num["duration"],1.25)
        self.assertEqual(validate_row(dict(zip(COLUMNS["county_episode"],rows("county_episode",2014)[0])),
                                      "county_episode",2014)[2],None)

    def test_complete_original_five_member_sample_normalizes(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);p=root/"source.zip";sample_zip(p)
            m=normalize(p,root/"out",years=(2014,))
            self.assertEqual(m["published_csv_members"],5)
            self.assertEqual(m["accepted_by_source_kind"],{
                "county_episode":2,"state_month_aggregate":2,
                "correlated_event":1,"correlation_8h_sensitivity":1,
                "correlation_24h_sensitivity":1})
            self.assertEqual((m["source_rows_scanned"],m["accepted"],m["rejected"],m["locally_indexed"]), (7,7,0,7))
            self.assertEqual(m["unique_county_fips"],2)
            self.assertEqual(m["exact_duplicate_source_rows_within_same_table"],0)
            self.assertEqual(m["unique_native_correlated_event_id_year_pairs"],1)
            self.assertEqual(m["durable_backend_indexed"],0)
            self.assertEqual(m["verified_insured_facility_outages"],0)
            with sqlite3.connect(root/"out"/"pnnl_county_outage_staging.sqlite") as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0],"ok")
                self.assertEqual(db.execute("select count(*) from source_observations").fetchone()[0],7)
                self.assertEqual(db.execute("select count(*) from source_observations where county_fips='01001'").fetchone()[0],4)

    def test_invalid_native_county_and_numeric_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);p=root/"source.zip";sample_zip(p)
            with zipfile.ZipFile(p,"a") as z:
                out=io.StringIO(newline="")
                w=csv.writer(out)
                w.writerow(COLUMNS["county_episode"])
                w.writerow(["bogus","Alabama","Autauga","2014-01-01 00:00:00","12","2","3","2.5"])
                w.writerow(["1001","Alabama","Autauga","2014-01-01 00:00:00","-1","2","3","2.5"])
                z.writestr("Outage_Dataset/eaglei_outages_2014_merged.csv",out.getvalue())
            m=normalize(p,root/"out",years=(2014,))
            self.assertEqual(m["rejected"],2)
            self.assertEqual(m["accepted"],5)
            self.assertEqual(set(m["rejection_reasons"]),{"invalid_county_fips","invalid_metric_duration"})
            self.assertEqual(len((root/"out"/"rejected.jsonl").read_text().splitlines()),2)

    def test_exact_duplicate_source_rows_tracked_but_not_auto_dropped(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);original=root/"original.zip";modified=root/"duplicate.zip"
            sample_zip(original)
            with zipfile.ZipFile(original) as src, zipfile.ZipFile(modified,"w") as dst:
                for info in src.infolist():
                    contents=src.read(info.filename)
                    if info.filename.endswith("eaglei_outages_2014_merged.csv"):
                        first_data_line=contents.splitlines(keepends=True)[1]
                        contents+=first_data_line
                    dst.writestr(info.filename,contents)
            result=normalize(modified,root/"out",years=(2014,))
            self.assertEqual(result["accepted"],8)
            self.assertEqual(result["locally_indexed"],8)
            self.assertEqual(result["exact_duplicate_source_rows_within_same_table"],1)
            self.assertEqual(result["rejected"],0)
            self.assertEqual(sum(s["exact_duplicate_source_rows_in_member"] for s in result["source_members"]),1)

    def test_missing_published_member_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);p=root/"source.zip";sample_zip(p)
            with self.assertRaisesRegex(ValueError,"Missing/duplicated expected"):
                normalize(p,root/"out",years=(2014,2015))

    def test_source_schema_change_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);p=root/"source.zip";sample_zip(p)
            with zipfile.ZipFile(p,"a") as z:
                z.writestr("Outage_Dataset/eaglei_outages_2014_group.csv",
                           "year,month,state\n2014,1,Alabama\n")
            with self.assertRaisesRegex(ValueError,"schema drift"):
                normalize(p,root/"out",years=(2014,))


if __name__=="__main__":
    unittest.main()
