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

**Observed work in this branch:** source URL/documentation verified, isolated parser/tests committed. **The local execution container could not download files**, but a subsequent GitHub-hosted Actions runner successfully downloaded and inventoried the NRC and CSB publisher files; PHMSA returned HTTP 403 (see the observed live probe below). Consequently, as of this write-up **actual official downloaded/accepted/normalized/indexed/deployed counts are NOT TESTED, not zero**. Fixture rows are only test rows. The existing NRC schema probe is not evidence of an imported incident cohort.

**Hard blockers:** execute the official file acquisition and inspect live NRC/CSB spreadsheet headers and PHMSA ZIP members on a network-capable CI runner; reconcile publisher unique IDs and report-grain; run source import with real counts; provide persistent private indexing and coordinator integration. Do not promote manifest state to VERIFIED or Source Health DEPLOYED until real content-level QA and live backend checks are complete.

**Ownership:** no A/B/D/E importer, global registry, Source Health, frontend or deployment file is modified in this lane. Coordinator owns the shared integration.

## Observed live official-source probe — GitHub Actions 39971177311

Actual publisher downloads on the 2026-10-23 GitHub-hosted runner, **not synthetic fixtures**:

| Publisher asset | Download | Bytes | Original SHA-256 | Content state |
| --- | --- | ---: | --- | --- |
| NRC CY25 XLSX | Success | 18,026,065 | `086da221569b5bbccb0f8170c54fd83c11cf8b7894258bfdea2c60a218407bda` | DOWNLOADED/INVENTORIED, not normalized |
| CSB 2026-09-01 XLSX | Success | 62,290 | `dbea875040e7ddfebfbe295c1731faab5f4c3829784c0c93dbb8d054c10b9dc1` | DOWNLOADED/INVENTORIED, not normalized |
| PHMSA hazardous liquids 2010+ ZIP | HTTP 403 Forbidden | — | — | BLOCKED by official publisher from this CI environment |

Run and provenance: https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39971177311; source metadata artifact ID `12509755805`. **Raw XLSX files are not published as GitHub artifacts**, to avoid copying source row-level personal information into public build outputs. A later probe version exposes actual worksheet nonempty row counts and headers in job logs, but worksheet counts must not be called distinct incidents without checking native report keys and grain. No verified accepted/rejected *real incident records*, indexed records or production deployments are claimed at this point.

This live evidence supersedes the earlier note that source download was unavailable *locally*: GitHub CI has real internet access for NRC/CSB, but PHMSA currently refuses the runner.

## NRC actual normalized run — GitHub Actions 39971717294

Official `CY25.xlsx`, `INCIDENT_COMMONS` source table, immutable source ID `SEQNOS`, incident datetime `INCIDENT_DATE_TIME`:

- Raw observed source rows **21,533**
- Normalized and checksum-validated records **21,533**
- Rejected **0**; duplicate source IDs **0**
- Missing normalized coordinates **21,533** (publisher uses split degrees/minutes/seconds/hemisphere fields; the first implementation did **not** silently guess geographic points)
- Normalized gzip SHA-256: `41e85052f2944ce3b54c20510c3ca7547f56a9019f77d651c1829eff4a10c1b9`
- Stage `STAGED_AND_CONTENT_VALIDATED_NOT_INDEXED`; private searchable index and deployed app **not done**.
- Verified run: https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39971717294

Rows are **source-reported NRC notifications**, initially unverified. A zero duplicate count applies to that exact workbook master table, not to cross-year or cross-agency real-world event de-duplication.

## Validated real NRC and CSB source cohorts — GitHub Actions 39972783353

**Real 2026-10-23 publisher fetch and deterministic per-source staging** (no fake examples):

| Official cohort | Observed data rows | Accepted | Rejected | Duplicate source IDs | Valid reported coordinates | Normalized SHA-256 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| NRC CY2025: joined CALLS/INCIDENT_COMMONS/INCIDENT_DETAILS on SEQNOS | 21,533 | **21,533** | **0** | **0** | **3,999**; missing 17,534 | `4fd46177b17751b656b90ff351b8b35962696e71e67db2c249db4d738c3a07b2` |
| CSB 2026-09-01 quarterly Accidental Release Events, Public sheet row 2 headers | 675 | **674** | **1** (missing incident date) | **0** | **0** in provided source fields | `74819c26dce16997bbca349961cadaa6732be194e4896172242b974f9b246df6` |
| PHMSA hazardous liquid pipeline | unavailable | **not tested** | **not tested** | **not tested** | **not tested** | No raw bytes — HTTP 403 |

Real validation logs: https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39972783353.
NRC native 2025 workbook includes exactly 21,533 source SEQNOS keys consistently found in all three joined 21,533-row tabs, **zero missing cross-table linkages**, **zero invalid/missing incident dates**; recovered 3,999 source-reported DMS positions (these are NOT known facility coordinates). NRC reported severity is unverified notification content. CSB 2026-09-01 `Number` is only known to be a unique identifier *within this release*; immutable cross-vintage identity and report status require further review. The CSB field `Substantial Property Damage` is not assumed to be a dollar amount, and any report-status flags require official interpretation. No candidate record has been cross-linked to a confirmed physical site, no verified property losses or insured claims are asserted.

**Important stage distinction:** download and reproducible source-content normalization pass for NRC and CSB; **indexed = not completed; served via private backend = not completed; deployed in app = not completed**. The network-capable runner still reports 403 for the official PHMSA pipeline ZIP. PHMSA hazmat has not yet been downloaded; a reported transport incident is not a physical insured site. All industries remain in scope for later linkage, while each federal source has its own reporting universe.

### Current CI gate
The repository's standard Python CI was green at commit `61d339e8` ([run 39972790290](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39972790290)). The lane's live-source probe is intentionally a **failed overall gate** because PHMSA's official publisher denies HTTP 403; its source-specific NRC and CSB subtasks both passed and the aggregate QA artifact is uploaded. The coordinator must not merge or label production-ready while external source coverage is incomplete.
