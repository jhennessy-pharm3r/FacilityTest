# Lane C — Industrial incident source intake (2026-10-23)

## Source boundaries

- **USCG NRC** — annual publisher FOIA workbook `https://nrc.uscg.mil/FOIAFiles/CY25.xlsx`. NRC reports are **initial notifications, unverified**, may be updated or duplicated across linked sheets. The pre-existing `scripts/probe_uscg_nrc.py` probes workbook layout only; a distinct report ID and correct master sheet must be confirmed in a real workbook before normalization. We do not substitute NOAA IncidentNews for NRC.
- **CSB** — quarterly Accidental Release Reporting Rule dataset, currently [official 2026-09-01 XLSX](https://www.csb.gov/assets/1/6/Copy_of_Accidental_Release_Events_2026-09-01.xlsx), covering reports under 40 CFR 1604 since 2020-03-23. Do not equate this with the selected investigated-accident portfolio or with the unverified CSB news feed. Confirm original row identifier in export; if no publisher-unique ID, do **not** synthesize a false regulator ID.
- **PHMSA pipeline** — official operator incident ZIP/TXT files, distinct report types and reporting vintages, [official source](https://www.phmsa.dot.gov/data-and-statistics/pipeline/source-data). Preserve report number + **dataset/report-type namespace** to prevent collision across pipeline subtypes. Separate operator submissions from flagged trend files.
- **PHMSA hazmat** — separate DOT Form 5800.1 transportation incident system; [official incident statistics](https://www.phmsa.dot.gov/hazmat-program-management-data-and-statistics/data-operations/incident-statistics). PHMSA advises multiple commodities/package types can produce multiple rows per report: group/report on source report ID, never count commodity rows as incidents.

All sectors and physical facility types can be candidates, but the above systems have *regulatory reporting scope*, not a full industry census. Transport incident location is not the address of the involved shipper or insured property.

## Reproducible local commands

Keep original agency downloads unchanged on restricted/private storage, and select source-native master sheet. Example (adjust verified column mapping as necessary):

```bash
python scripts/probe_uscg_nrc.py --year 2025 --output data/raw/nrc/CY25.xlsx --report data/qa/nrc-probe.json
python scripts/build_industrial_incidents.py --source nrc --raw data/raw/nrc/CY25.xlsx --sheet "VERIFIED_MASTER_SHEET" --source-url https://nrc.uscg.mil/FOIAFiles/CY25.xlsx --normalized data/staged/nrc.csv.gz --manifest data/qa/nrc.json --mapping data/config/nrc_verified_fields.json --min-rows 100
python scripts/build_industrial_incidents.py --source csb --raw data/raw/csb/Copy_of_Accidental_Release_Events_2026-09-01.xlsx --sheet "VERIFIED_SHEET" --source-url https://www.csb.gov/assets/1/6/Copy_of_Accidental_Release_Events_2026-09-01.xlsx --normalized data/staged/csb.csv.gz --manifest data/qa/csb.json --mapping data/config/csb_verified_fields.json
python scripts/build_industrial_incidents.py --source phmsa_pipeline --raw data/raw/phmsa/official-download.zip --member "VERIFIED_REPORT_DATA.txt" --source-url https://www.phmsa.dot.gov/data-and-statistics/pipeline/source-data --normalized data/staged/pipeline.csv.gz --manifest data/qa/pipeline.json --mapping data/config/pipeline_verified_fields.json
pytest -q tests/test_industrial_incidents.py
```

The source-specific mapping JSON keys are `id,date,name,city,state,lat,lon,fatal,injury,damage`, values are **actual official column labels**. No source is marked downloaded or normalized merely because its landing page responded. Failed ID, date, or schema checks must block ingestion. The `--min-rows` gate guards incomplete or empty downloads.

## Evidence rules and publish gate

Raw bytes and SHA-256, normalised gzip SHA-256, actual source rows, accepted/rejected/duplicate rows, missing coordinate count, field map, input table, fetch timestamp and publisher URL are recorded in a manifest. Source-specific records are not physical-site registry entries; no match is generated automatically. Coordinates are source-reported, not geocoded property footprints. Counts from CSV row-level PHMSA commodities cannot be described as distinct incidents unless the grain is verified.

**Observed work in this branch:** source URL/documentation verified, isolated parser/tests committed. **No live official file was downloaded into the execution environment for this lane** because the local execution container cannot resolve external hosts, and connector read access is not a filesystem download. Consequently, as of this write-up **actual official downloaded/accepted/normalized/indexed/deployed counts are NOT TESTED, not zero**. Fixture rows are only test rows. The existing NRC schema probe is not evidence of an imported incident cohort.

**Hard blockers:** execute the official file acquisition and inspect live NRC/CSB spreadsheet headers and PHMSA ZIP members on a network-capable CI runner; reconcile publisher unique IDs and report-grain; run source import with real counts; provide persistent private indexing and coordinator integration. Do not promote manifest state to VERIFIED or Source Health DEPLOYED until real content-level QA and live backend checks are complete.

**Ownership:** no A/B/D/E importer, global registry, Source Health, frontend or deployment file is modified in this lane. Coordinator owns the shared integration.
