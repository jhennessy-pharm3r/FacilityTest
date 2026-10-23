"""Read-only EPA TRI reporting-year lookups; never infer insured physical-site identity."""
import argparse
import json
import re
from pathlib import Path
from .read_index import source_status, lookup, InvalidSourceIndex

def lookup_history(root, tri_facility_id, years, per_year_limit=20):
    if not isinstance(tri_facility_id,str) or not 1<=len(tri_facility_id.strip())<=160:
        raise ValueError("Exact TRI reporter identifier required")
    if not isinstance(years,(list,tuple)) or not years or len(years)>40:
        raise ValueError("Explicit reporting-year list required")
    if type(per_year_limit)!=int or not 1<=per_year_limit<=100:
        raise ValueError("Invalid per-year pagination")
    for year in years:
        if type(year)!=int or not 1987<=year<=2024:
            raise ValueError("Outside validated TRI Basic reporting-year scope")
    if len(years)!=len(set(years)):
        raise ValueError("Duplicate source reporting years")
    root=Path(root).expanduser().resolve()
    grouped=[]
    for year in sorted(years):
        folder=root/("tri_"+str(year))
        index=folder/"tri.sqlite"
        manifest=folder/"tri.manifest.json"
        if not index.is_file() or not manifest.is_file():
            raise InvalidSourceIndex("Missing TRI year "+str(year)+"; absence of index is NOT evidence of no facility reporting")
        m=json.loads(manifest.read_text())
        if m.get("year")!=year:
            raise InvalidSourceIndex("Requested TRI vintage mismatches source manifest")
        facts=source_status(index,manifest,"tri")
        results=lookup(index,manifest,"tri",tri_facility_id,limit=per_year_limit)
        if any(row["source_reported_findings"]["reporting_year"]!=str(year) for row in results["rows"]):
            raise InvalidSourceIndex("TRI observation year mismatches index")
        grouped.append({"year":year,"total_year_index_rows":facts["indexed_rows"],
            "matching_chemical_form_rows":results["observations_available"],
            "returned":results["returned"],"rows":results["rows"],
            "source_archive_sha256":facts["source_archive_sha256"],
            "source_index_sha256":facts["index_sha256"]})
    return {"source":"EPA TRI Basic","native_TRIFD":tri_facility_id.strip(),
        "all_requested_year_indices_validated":True,"years":grouped,
        "total_matched_reporting_forms":sum(r["matching_chemical_form_rows"] for r in grouped),
        "physical_site_linkage":"NOT_REVIEWED","deployment_state":"NOT_DEPLOYED",
        "notice":"Chemical forms, not physical plants, releases experienced by people, or insured losses. Missing/index-absent years fail closed."}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--index-root",required=True)
    p.add_argument("--trifd",required=True)
    p.add_argument("--years",required=True)
    p.add_argument("--limit",type=int,default=20)
    a=p.parse_args()
    if not re.fullmatch(r"[0-9]{4}(,[0-9]{4})*",a.years):
        p.error("Comma-separated years required")
    print(json.dumps(lookup_history(a.index_root,a.trifd,[int(x) for x in a.years.split(",")],a.limit),indent=2))
if __name__=="__main__":
    main()
