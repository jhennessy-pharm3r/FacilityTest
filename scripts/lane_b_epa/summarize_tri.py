"""Reconcile separately-published official TRI Basic annual QA artifacts.

Input QA JSON/SQLite manifests are produced ONLY by full official year ingestion.
No fabricated or summed unique physical site counts.
"""
import argparse
import hashlib
import json
from pathlib import Path

def _sha(value):
    return isinstance(value,str) and len(value)==64 and all(x in "0123456789abcdef" for x in value.lower())

def summarize(root,years):
    if not isinstance(years,(list,tuple)) or not years:
        raise ValueError("Explicit year list required")
    if any(type(y)!=int or y<1987 or y>2024 for y in years) or len(set(years))!=len(years):
        raise ValueError("Invalid duplicate or unsupported reporting year")
    root=Path(root)
    annual=[]
    for year in sorted(years):
        folder=root/("lane-b-tri-historical-"+str(year)+"-qa")
        qpath=folder/"year_qa.json"
        mpath=folder/"tri.manifest.json"
        if not qpath.is_file() or not mpath.is_file():
            raise ValueError("Official TRI year QA or source index manifest missing for "+str(year))
        q=json.loads(qpath.read_text())
        m=json.loads(mpath.read_text())
        if (q.get("reporting_year")!=year or m.get("year")!=year or
            m.get("source")!="tri" or m.get("schema_version")!=2 or
            m.get("state")!="INDEXED" or m.get("deployment_state")!="NOT_DEPLOYED" or
            q.get("scanned_downloaded_rows")!=m.get("scanned_rows") or
            q.get("accepted_normalized")!=m.get("accepted_rows") or
            q.get("source_indexed")!=m.get("indexed_rows") or
            q.get("rejected")!=m.get("rejected_rows") or
            q.get("coordinate_pairs")!=m.get("valid_coordinate_pairs") or
            q.get("source_sha256")!=m.get("archive_sha256") or
            q.get("index_sha256")!=m.get("index_sha256") or
            not _sha(m.get("archive_sha256")) or not _sha(m.get("index_sha256")) or
            not m.get("source_url","").endswith("/"+str(year)+"_US/csv") or
            q.get("deployed_records")!=0 or m["accepted_rows"]+m["rejected_rows"]!=m["scanned_rows"]):
            raise AssertionError("Provenance/data-count discrepancy in official TRI year "+str(year))
        annual.append(dict(year=year,downloaded_rows=q["scanned_downloaded_rows"],
            accepted_rows=q["accepted_normalized"],indexed_rows=q["source_indexed"],
            rejected_rows=q["rejected"],distinct_native_TRIFD=q["distinct_native_TRI_facility_ids"],
            reported_coordinate_pairs=q["coordinate_pairs"],
            reported_unit_counts=q["source_reported_units"],
            source_sha256=m["archive_sha256"],index_sha256=m["index_sha256"]))
    units={}
    for y in annual:
        for k,v in y["reported_unit_counts"].items():
            units[k]=units.get(k,0)+v
    downloaded=sum(v["downloaded_rows"] for v in annual)
    accepted=sum(v["accepted_rows"] for v in annual)
    rejected=sum(v["rejected_rows"] for v in annual)
    assert downloaded==accepted+rejected
    return dict(source="Official EPA TRI Basic US national annual reporting-year partitions",
        covered_reporting_years=sorted(years),source_years_count=len(years),
        source_downloaded_rows=downloaded,accepted_normalized_rows=accepted,
        source_indexed_staging_rows=sum(v["indexed_rows"] for v in annual),
        rejected_rows=rejected,coordinate_bearing_report_rows=sum(v["reported_coordinate_pairs"] for v in annual),
        reporting_unit_row_counts=units,annual=annual,
        cross_year_unique_facility_count=None,verified_insured_properties=0,
        deployed_private_service_rows=0,
        notice="Counts are chemical report rows across years, not distinct sites, emissions totals or insured losses")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--artifact-root",required=True)
    p.add_argument("--years",required=True,help="e.g. 1987-2019")
    p.add_argument("--output",required=True)
    a=p.parse_args()
    if "-" not in a.years: p.error("Year range FIRST-LAST required")
    first,last=map(int,a.years.split("-",1))
    if first>last:p.error("Year range inverted")
    report=summarize(a.artifact_root,list(range(first,last+1)))
    path=Path(a.output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("HISTORICAL_TRI_FULL_YEAR_SUMMARY",report["source_years_count"],
          report["source_downloaded_rows"],report["accepted_normalized_rows"],
          report["rejected_rows"],"DEPLOYED",report["deployed_private_service_rows"])
if __name__=="__main__":main()
