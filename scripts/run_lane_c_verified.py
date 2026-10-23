"""Run real official NRC+CSB downloads, repeatable transforms, and source-only SQLite QA.

PHMSA official endpoints are tested independently; access failures remain a
visible BLOCKED flag, not false zero incident counts. Only aggregate manifests
are stored as workflow artifacts. Source row files and temp SQLite stay private.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import requests

try:
    from scripts.probe_lane_c_sources import download
    from scripts.build_nrc_enriched import stage_nrc
    from scripts.build_csb_incidents import stage_csb
    from scripts.index_lane_c_incidents import index_sources, search_source, audit_multiyear_source_coverage
    from scripts.lane_c_review_candidates import build_review_candidates
    from scripts.lane_c_private_handoff import private_bundle
except ModuleNotFoundError:  # direct script
    from probe_lane_c_sources import download
    from build_nrc_enriched import stage_nrc
    from build_csb_incidents import stage_csb
    from index_lane_c_incidents import index_sources, search_source, audit_multiyear_source_coverage
    from lane_c_review_candidates import build_review_candidates
    from lane_c_private_handoff import private_bundle

URLS = {
    "nrc": "https://nrc.uscg.mil/FOIAFiles/CY25.xlsx",
    "csb": "https://www.csb.gov/assets/1/6/Copy_of_Accidental_Release_Events_2026-09-01.xlsx",
}
PHMSA_OFFICIAL_URLS = {
    "pipeline_hazardous_liquid_operator_submissions_2010_present":
        "https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/data_statistics/pipeline/accident_hazardous_liquid_jan2010_present.zip",
    "pipeline_gas_distribution_2010_present":
        "https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/data_statistics/pipeline/incident_gas_distribution_jan2010_present.zip",
    "pipeline_gas_transmission_gathering_2010_present":
        "https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/data_statistics/pipeline/incident_gas_transmission_gathering_jan2010_present.zip",
    "pipeline_flagged_incidents":
        "https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/data_statistics/pipeline/PHMSA_Pipeline_Safety_Flagged_Incidents.zip",
    "hazmat_public_reporting_portal":
        "https://portalpublic.phmsa.dot.gov/analytics/saw.dll?Portal%3FPortalPath=%2Fshared%2FPublic%20Website%20Pages%2F_portal%2FHazmat%20Incident%20Report%20Search",
    "official_dot_catalog_metadata":
        "https://data.transportation.gov/api/views/27nc-rsge.json",
}
def fetch_official_phmsa(name, url, work):
    """Probe only published official distribution paths; never bypass access controls."""
    report = {"url": url, "state": "NOT_TESTED", "is_incident_rows": False}
    temp = work / ("phmsa-" + name + ".zip")
    try:
        if not url.endswith(".zip"):
            with requests.get(url, timeout=(15,35), stream=True, allow_redirects=True,
                              headers={"User-Agent":"FacilityRisk-Industrial-Sources/1.0"}) as response:
                report["http_status"] = response.status_code
                report["content_type"] = response.headers.get("Content-Type","")
                if response.status_code != 200:
                    report["state"] = "BLOCKED_HTTP_" + str(response.status_code)
                else:
                    report["state"] = "OFFICIAL_LANDING_OR_METADATA_ONLY_NO_EVENT_ROWS"
            return report
        downloaded, checksum = download(url, 160_000_000, temp)
        report.update({"state": "DOWNLOADED_ZIP_PENDING_REPORT_GRAIN_VERIFICATION",
                       "bytes": downloaded, "sha256": checksum, "is_incident_rows": False})
        from zipfile import ZipFile
        with ZipFile(temp) as z:
            members = [i for i in z.infolist() if not i.is_dir()]
            if any(i.file_size > 700_000_000 or ".." in Path(i.filename).parts
                   or i.filename.startswith("/") for i in members):
                raise ValueError("Unsafe official zip members")
            report["members"] = [{"file":i.filename, "size":i.file_size} for i in members[:20]]
    except Exception as e:
        report["state"] = "BLOCKED_OFFICIAL_DISTRIBUTION"
        report["error"] = type(e).__name__ + ": " + str(e)[:400]
    finally:
        temp.unlink(missing_ok=True)
    return report

def run(output,*,private_bundle_dir=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    audit = {"run_started_at":datetime.now(timezone.utc).isoformat(),
             "scope": "USCG NRC CY2025 / CSB 2026-09-01 / PHMSA official access diagnostics",
             "all_industries_supported_for_candidate_review": True,
             "source_cohorts":{}, "phmsa":{}, "blocked_items":[],
             "indexed_durable": 0, "deployed": 0, "verified_physical_site_links":0}
    success = False
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        raw_nrc = work / "nrc-CY25.xlsx"
        raw_csb = work / "csb-2026-09-01.xlsx"
        try:
            for key, target, limit in (("nrc",raw_nrc,60_000_000),("csb",raw_csb,30_000_000)):
                size, sha = download(URLS[key],limit,target)
                audit["source_cohorts"][key] = {
                    "official_url":URLS[key], "raw_bytes":size, "raw_sha256":sha,
                    "access_state":"DOWNLOADED"}
            nrc = stage_nrc(raw_nrc, work/"nrc.csv.gz",output/"nrc-manifest.json",
                            year=2025,minimum_rows=10000)
            csb = stage_csb(raw_csb, work/"csb.csv.gz",output/"csb-manifest.json",
                            release="2026-09-01",minimum_rows=500)
            # Repeated transform of the exact same official original bytes MUST
            # be bit-for-bit identical, independent of the output filename/time.
            nrc_second = stage_nrc(raw_nrc, work/"nrc-repeat.csv.gz",work/"nrc-repeat.json",
                                  year=2025,minimum_rows=10000)
            csb_second = stage_csb(raw_csb, work/"csb-repeat.csv.gz",work/"csb-repeat.json",
                                  release="2026-09-01",minimum_rows=500)
            if (nrc["normalized_sha256"] != nrc_second["normalized_sha256"] or
                csb["normalized_sha256"] != csb_second["normalized_sha256"]):
                raise ValueError("FAIL: same official source gave non-deterministic normalized SHA")
            audit["deterministic_repeated_sha256"] = "PASS"
            audit["source_cohorts"]["nrc"].update({
                "accepted":nrc["accepted_rows"],"rejected":nrc["rejected_rows"],
                "observed_native_ids":nrc["nrc_reports"],
                "source_coordinates":nrc["coordinate_records"],
                "missing_coordinates":nrc["missing_coordinates"],
                "missing_join_links":nrc["missing_cross_table_links"],
                "date_missing":nrc["invalid_or_missing_incident_dates"],
                "normalized_sha256":nrc["normalized_sha256"],
                "status":"CONTENT_VALIDATED"})
            audit["source_cohorts"]["csb"].update({
                "raw_data_rows":csb["raw_data_rows"],"accepted":csb["accepted_rows"],
                "rejected":csb["rejected_rows"],"reject_breakdown":csb["rejection_reasons"],
                "state_counts":csb["state_counts"],
                "first_date":csb["first_incident_date"],"last_date":csb["last_incident_date"],
                "qualitative_marker_counts":csb["qualitative_marker_counts"],
                "normalized_sha256":csb["normalized_sha256"],
                "status":"CONTENT_VALIDATED_VINTAGE_SCOPED_KEYS"})
            source_index = index_sources(work/"lane-c-source.sqlite",[
                ("nrc",work/"nrc.csv.gz",output/"nrc-manifest.json"),
                ("csb",work/"csb.csv.gz",output/"csb-manifest.json")
            ],output/"ephemeral-index-audit.json")
            audit["source_index"] = source_index
            for src in ("nrc","csb"):
                result = search_source(work/"lane-c-source.sqlite",source=src,page_size=10)
                if result["total"] != source_index["sources"][src]["indexed_rows_ephemeral"] or len(result["items"])!=10:
                    raise ValueError("SOURCE QUERY count/sample failed: "+src)
            audit["source_query_paging"] = "PASS"
            success = True
        except Exception as e:
            audit["blocked_items"].append({"source":"nrc_csb_content_or_index","error":type(e).__name__ + ": "+str(e)})
        # Expand beyond a single annual report. Each NRC annual workbook has
        # its own source-native SEQNOS namespace, so do NOT coalesce identical
        # identifiers from different years or silently double count events.
        audit["additional_nrc_cohorts"] = {}
        for year in (2026, 2024, 2023, 2022, 2021, 2020, 2019, 2018, 2017, 2016, 2015, 2014, 2013, 2012, 2011, 2010):
            url = f"https://nrc.uscg.mil/FOIAFiles/CY{year%100:02d}.xlsx"
            yearly = {"source_url":url, "year":year, "dataset_role":"annual_report_cohort",
                      "cross_year_auto_dedup":"NOT_PERFORMED",
                      "year_completeness":"PROVISIONAL_OPEN_2026" if year == 2026 else "ANNUAL_PUBLISHED_SNAPSHOT"}
            try:
                yr_raw=work/f"nrc-CY{year%100:02d}.xlsx"
                bytes_count, raw_sha = download(url, 60_000_000, yr_raw)
                yearly["raw_bytes"]=bytes_count
                yearly["raw_sha256"]=raw_sha
                yr_file=work/f"nrc-{year}.csv.gz"
                yr_manifest=output/f"nrc-{year}-manifest.json"
                result=stage_nrc(yr_raw,yr_file,yr_manifest,year=year,minimum_rows=1000)
                yr_second=stage_nrc(yr_raw,work/f"nrc-{year}-again.csv.gz",
                                     work/f"nrc-{year}-again.json",year=year,minimum_rows=1000)
                if result["normalized_sha256"] != yr_second["normalized_sha256"]:
                    raise ValueError("NRC annual normalized SHA differed across same source rerun")
                indexed=index_sources(work/f"nrc-{year}-source.sqlite",
                    [("nrc",yr_file,yr_manifest)],work/f"nrc-{year}-index-audit.json")
                query=search_source(work/f"nrc-{year}-source.sqlite",source="nrc",page_size=10)
                if query["total"] != result["accepted_rows"]:
                    raise ValueError("Annual source query count mismatch")
                yearly.update({
                    "state":"INDEXED_EPHEMERAL_NOT_DEPLOYED",
                    "source_rows": result["nrc_reports"],
                    "accepted":result["accepted_rows"],"rejected":result["rejected_rows"],
                    "source_coordinates":result["coordinate_records"],
                    "missing_coordinates":result["missing_coordinates"],
                    "missing_joins":result["missing_cross_table_links"],
                    "invalid_or_missing_dates":result["invalid_or_missing_incident_dates"],
                    "normalized_sha256":result["normalized_sha256"],
                    "ephemeral_indexed":indexed["total_indexed_ephemeral"],
                    "repeatable_normalization":"PASS"
                })
            except Exception as error:
                yearly["state"]="BLOCKED_INDEPENDENT_YEAR"
                yearly["error"]=type(error).__name__+": "+str(error)[:350]
                audit["blocked_items"].append({"source":f"nrc_{year}","error":yearly["error"]})
            audit["additional_nrc_cohorts"][str(year)]=yearly
        audit["total_ephemeral_indexed_all_independent_cohorts"] = (
            audit.get("source_index",{}).get("total_indexed_ephemeral",0)
            + sum(x.get("ephemeral_indexed",0) for x in audit["additional_nrc_cohorts"].values())
        )
        # Consolidated *source-only* SQLite: primary key (source_namespace,
        # publisher_native_id) retains years independently when NRC numbers
        # repeat. This is for Lane E integration readiness, NOT an insured
        # property index, and is never uploaded as a public build artifact.
        try:
            inputs=[
                ("nrc_2025",work/"nrc.csv.gz",output/"nrc-manifest.json"),
                ("csb",work/"csb.csv.gz",output/"csb-manifest.json"),
            ]
            for year in (2026,2024,2023,2022,2021,2020,2019,2018,2017,2016,2015,2014,2013,2012,2011,2010):
                if audit["additional_nrc_cohorts"].get(str(year),{}).get("ephemeral_indexed"):
                    inputs.append((f"nrc_{year}",work/f"nrc-{year}.csv.gz",
                                   output/f"nrc-{year}-manifest.json"))
            consolidated=index_sources(work/"lane-c-multiyear.sqlite",inputs,
                                  output/"all-cohorts-index-audit.json")
            for name in [item[0] for item in inputs]:
                query=search_source(work/"lane-c-multiyear.sqlite",
                                     source=name,page_size=10)
                if query["total"] != consolidated["sources"][name]["indexed_rows_ephemeral"]:
                    raise ValueError("Consolidated source namespace/count mismatch: "+name)
            if (consolidated["total_indexed_ephemeral"] !=
                audit["total_ephemeral_indexed_all_independent_cohorts"]):
                raise ValueError("Consolidated index counts differ from separately checked source indices")
            audit["nrc_geography_and_incident_year_audit"]=audit_multiyear_source_coverage(work/"lane-c-multiyear.sqlite")
            candidates=build_review_candidates(work/"lane-c-multiyear.sqlite")
            audit["cross_agency_review_candidates"]=candidates
            if private_bundle_dir:
                raw_sources={"nrc_2025":raw_nrc,"csb":raw_csb}
                for source_name,_,_ in inputs:
                    if source_name.startswith("nrc_") and source_name!="nrc_2025":
                        vintage=int(source_name[4:])
                        raw_sources[source_name]=work/f"nrc-CY{vintage%100:02d}.xlsx"
                audit["opt_in_private_handoff"]=private_bundle(
                    work/"lane-c-multiyear.sqlite",inputs,raw_sources,
                    private_bundle_dir,repo_root=Path(__file__).resolve().parents[1])
            audit["consolidated_multi_year_index"]={
                "state":"INDEXED_EPHEMERAL_NOT_DEPLOYED",
                "total_rows":consolidated["total_indexed_ephemeral"],
                "source_keys":[x[0] for x in inputs],
                "source_counts":{k:v["indexed_rows_ephemeral"]
                    for k,v in consolidated["sources"].items()},
                "quick_check":consolidated["quick_check"],
                "source_native_ids_preserved_and_namespaced":True,
                "source_query_paging":"PASS",
                "deployment":"NOT_DEPLOYED"
            }
        except Exception as error:
            audit["blocked_items"].append({
                "source":"consolidated_source_index",
                "error":type(error).__name__+": "+str(error)[:400]})
            success=False
        # External access attempts do not prevent the two successful source
        # cohorts from being independently usable as staging.
        for name, url in PHMSA_OFFICIAL_URLS.items():
            check = fetch_official_phmsa(name,url,work)
            audit["phmsa"][name] = check
            if check["state"].startswith("BLOCKED"):
                audit["blocked_items"].append({"source":name,
                                               "error":check.get("error",check["state"])})
        audit["run_completed_at"] = datetime.now(timezone.utc).isoformat()
        audit["nrc_csb_content_and_ephemeral_index_gate"] = "PASS" if success else "FAIL"
        audit["phmsa_accepted_rows"] = None
        audit["phmsa_indexed_rows"] = None
        audit["phmsa_deployed_rows"] = None
        audit["phmsa_lane_status"] = "BLOCKED_OR_UNVERIFIED"
        (output/"lane-c-run-audit.json").write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
        print(json.dumps({
            "nrc_csb_gate":audit["nrc_csb_content_and_ephemeral_index_gate"],
            "nrc":audit["source_cohorts"].get("nrc"),
            "csb":audit["source_cohorts"].get("csb"),
            "ephemeral_index":audit.get("source_index",{}).get("total_indexed_ephemeral"),
            "additional_nrc_cohorts":audit.get("additional_nrc_cohorts"),
            "current_year_2026_state":audit.get("additional_nrc_cohorts",{}).get("2026",{}).get("state","NOT_TESTED"),
            "total_ephemeral_indexed":audit.get("total_ephemeral_indexed_all_independent_cohorts"),
            "consolidated_index":audit.get("consolidated_multi_year_index"),
            "cross_agency_review_candidates":audit.get("cross_agency_review_candidates"),
            "nrc_geography_and_incident_year_audit":audit.get("nrc_geography_and_incident_year_audit"),
            "deterministic":audit.get("deterministic_repeated_sha256"),
            "phmsa":audit["phmsa"],
            "blocked_items":audit["blocked_items"],
            "deployed":0
        },indent=2))
    if not success:
        raise SystemExit("Official NRC/CSB reproducibility/index gate failed; see run artifact")
    return audit

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--private-bundle-dir",type=Path,
        help="Explicit pre-provisioned secure outside-repository path for original XLSX, normalized gzip, manifests, and SQLite; NEVER under public Pages/CI artifact directory")
    a=ap.parse_args()
    run(a.output,private_bundle_dir=a.private_bundle_dir)

if __name__=="__main__":
    main()
