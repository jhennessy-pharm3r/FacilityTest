# Lane D — utility reliability, grid disturbances and business-interruption evidence

**Scope:** all industries and all facility types. Isolated ingestion modules; no shared application, canonical site registry, report UI, or Source Health edits. Dedicated draft PR #77, coordinated in issue #73. All numbers below are **observed from real official-source GitHub Actions runs** on 2026-10-23, not synthetic test fixtures. All datasets are still **nonproduction staging**.

## Current Lane E handoff — real source ingestion, read-only queries and unresolved deployment (2026-10-23)

**Source intake has been content-validated, but Lane D is PARTIALLY VALIDATED / NOT DEPLOYED.** All numbers below are original **source-observation grain**, not unique physical facilities, insured outage events or paid claims. Every source has an original URL/vintage, publisher-specific IDs, accepted/rejected ledger and original archive/document SHA-256. Do not sum these streams across sources, across duplicate rows, or across ODIN snapshots.

| Original publisher source and grain | Actual downloaded source rows/documents | Normalized / accepted source observations | Rejected | Temporary source SQLite indexed | Durable backend / application deployed |
| --- | ---: | ---: | ---: | ---: | ---: |
| EIA-861 2025 utility reliability/state/county source rows | 12,926 rows | 12,923 | 3 | 12,923 | 0 / 0 |
| EIA Electric Power Monthly 2023 annual plus partial 2024 disturbances | 230 publisher table rows | 230 | 0 | 230 | 0 / 0 |
| **DOE CESER OE-417 original annual summary dataset, 2023 discovery vintage** | **341 original published report rows** | **341** (309 dated; **32 unknown event start dates retained**) | **0** | **341** | **0 / 0** |
| DOE/PNNL 2014–2023 historical outage research table rows | 2,124,183 | 2,124,183, of which **277,360 literal same-table row repeats flagged** | 0 | 2,124,183 | 0 / 0 |
| ORNL **direct** first-party county-status feed, 17:53 UTC public snapshot | 484 source status rows | 484 (2 exact repeats flagged) | 0 | 484 | 0 / 0 |
| ORNL OpenEnergyHub **mirror**, separately observed 15:42 UTC snapshot | 424 separate mirror status rows | 423 | 1 invalid timestamp | 423 | 0 / 0 |
| ORNL direct participating utility feed statuses at 16:18 UTC | 157 utility feed records | 157 | 0 | 157 | 0 / 0 |
| Baxter North Cove first-party issuer press releases | 3 dated source HTML documents | 3 publication observations covering **one** issuer-reported storm interruption | 0 | 3 | 0 / 0 |
| Crane Marion first-party issuer financial reports | 2 publisher PDF documents (2024 FY/2025 Q2) | 7 typed financial facts, **one** underlying storm event | 0 | 7 | 0 / 0 |
| Pebblebrook LaPlaya first-party investor results | 2 publisher HTML documents (2024 FY/2025 FY) | 5 typed financial facts, **two** issuer-reported storm/event groups | 0 | 5 | 0 / 0 |
| SEC EDGAR directly hosted filing documents | 0 (official archive HTTP 403 from authorized CI) | 0 | Not an ingested source; blocked | 0 | 0 / 0 |

**Source-specific multiplicity:** PNNL has 1,385,389 merged county outage episode observations, **none literal same-table duplicated**; across all 50 historical CSVs 277,360 source-content duplicates and 1,846,823 distinct source-table row contents (not unique events). The PNNL 8h and 24h correlation variants are alternate relationships. ORNL **direct** and **mirror** are overlapping distributions of active county outage status, and *individual snapshots may gain/lose rows over minutes*: never add 484 + 423, nor accumulate a fresh ODIN snapshot as independent historic outages. ORNL participant statuses are utility *feed health*, not property or outage counts: **10 of 157 source feeds reported error flags**. Current source-provider candidates such as 15 EIA utilities in WA/Pierce are county/utility reporting context, not an automatic physical property service connection.

### Additional authorized primary DOE OE-417 annual disturbance distribution — public domain

Official DOE CESER dataset mirrored by ORNL Open Energy Hub, **dataset ID \`oe-417-annual-summaries\`**: [original public publisher page](https://openenergyhub.ornl.gov/explore/dataset/oe-417-annual-summaries/), original source export \`https://openenergyhub.ornl.gov/api/explore/v2.1/catalog/datasets/oe-417-annual-summaries/exports/json\`, original metadata \`https://openenergyhub.ornl.gov/api/explore/v2.1/catalog/datasets/oe-417-annual-summaries\`. Metadata explicitly says **Public Domain**, publication describing a **2023 data-discovery vintage**, not a national 2024–2026 census. [Official 2023 original-source ingest/row-by-row SHA/index/reproducible SQL + real index query gate 40000353894](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/40000353894) PASS.

Original official JSON **165,640 bytes, SHA256 \`5329d272544e9164692f08b34a5079d3f89a2095f1a77a8fa8dfca8923b06d18\`**, publisher metadata **7,192 bytes, SHA256 \`603e1eeba802e50b7f2f0ea6069e896db0010481a147ee3247bd4e658e1bdee1\`**. **341 source rows downloaded, 341 accepted and separately temporary SQLite indexed, 0 rejected, 0 exact duplicates**; original/accepted/rejected/SQL counts and row hashes reconciled; rerunning the saved original source produced byte-identical normalized JSONL and SQL source-only index. **309 rows report a 2023 incident start date; 32 contain NULL source event start date**. Initial strict importer had rejected all 32; corrected and independently rerun to *retain* them as \`NOT_REPORTED\`, without inventing a year or zero-day outage. Original source additionally contains **47 missing restoration dates, 34 missing affected-customer counts, 78 missing MW demand-loss values**, and **no geocoded site coordinates**. It has only original free-text affected area, reported NERC region/type/alert, event/start/restoration fields; **no official native stable incident ID**. Position+original row hash is a DERIVED source row key, not an incident ID.

New \`facilityrisk/lane_d/query_oe417_annual.py\` supports bounded read-only exact original event type, explicit event year and **undated-only** queries: genuine 341-row official SQL returned **309 2023-dated, 32 source-undated and 40 source event_type "Vandalism"** observations when queried separately; zero site power-outage claims. It is separate from EPM disturbance 2023 table **158 records**: both are DOE-417-derived distributions, coverage criteria differ, and **event counts must not be summed or considered independent without case-level corroboration**. This supplementary annual source is not a facility dataset, utility-provider-to-building proof, insurer loss file, or complete all-industry power interruption census.

\`\`\`bash
python -m facilityrisk.lane_d.ingest_oe417_annual --output /private/lane-d/doe-oe417-2023
python -m facilityrisk.lane_d.query_oe417_annual --db /private/lane-d/doe-oe417-2023/oe417_annual_staging.sqlite --date-state undated --limit 50
\`\`\`

### Cross-distributor DOE-417 potential duplicate-incident QA, 2023 — real original-source comparison

Both original publisher distributions were re-downloaded and parsed: **341 DOE OE417 annual source rows (309 dated/32 unknown starts)** and **158 EIA EPM B.2 2023 source rows (17 literal publisher start-date ". ." unknown)**. DOE original annual JSON SHA256 `5329d272544e9164692f08b34a5079d3f89a2095f1a77a8fa8dfca8923b06d18`, EIA B.2 original HTML SHA256 `53d9b85bb4b3f2c89b666e0059326becb874c268ddad58527b2240dcb872e78d`. Publisher HTML raw checksum can vary due site markup; each download-specific original digest is retained. [Independent original source candidate comparison and deterministic replay #40001255947](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/40001255947) **PASS**.

The conservative review-only method matches **identical originally reported calendar day AND alphanumeric-normalized publisher affected-area string**, never fuzzy insured facility/utility names. Both sources lack original native stable event IDs. **117 possible date/area overlap groups** include **120 DOE OE417 original rows and 122 EIA EPM source rows**. Of those, **112 are 1-to-1 candidate groups; 5 groups contain multiple possible associations (128 total cross-product pairs)**. No proposed associations have been independently verified to be identical real-world incidents: **0 independently verified same-event links, 0 verified property electric outages, 0 insurance claim evidence, 0 deployed**. The 17 unknown EPM start dates and 32 unknown annual dates are preserved and are never imputed as 2023 or zero downtime.

The original 341 and 158 rows MUST NOT be added as 499 independent disturbances; likely overlapping distribution sources and the candidate matches demand review. Source row nonmatches also do not prove distinct events. Original rows and derived publication-position IDs remain untouched. Reproduce using `python -m facilityrisk.lane_d.audit_oe417_epm_overlap --eia-b2-html /approved/b2.html --oe417-json /approved/annual_2023.json --oe417-metadata /approved/metadata.json --output /private/lane-d/overlap` and official `.github/workflows/lane-d-oe417-epm-overlap.yml`. This is Lane D source-only analysis for coordinator, not site-risk model input.

### Verified financial evidence by interpretation, NOT a common insured-loss denominator

- **Crane manufacturing, Marion, NC:** original 2024 10-K issuer PDF (111 pages; SHA-256 \`0fdecf744b2a414316322de37ee5a7288e8932e617a3394a4372f5a5a02da546\`) and 2025 Q2 10-Q (47 pages; SHA-256 \`e759a4eb321ff90387de6d69ed6f370cf9db4a1ffe2085b211922fe5704b4bde\`) are source-authentic original public issuer links distributed on its recognized Q4 CDN. **$4.0m issuer-reported *received insurance proceeds for lost profits* in 2025 Q2**. Separately source-reported FY2024 $23.3m site remediation/damage expenses, $20.0m hurricane recoveries and $2.8m receivable; through 2025 Q2 cumulative $29.1m damage expenses, $25.0m recoveries and a $3.6m receivable. **Receivable balances and cumulative recoveries are not additive across fiscal statements**. Source check [run 39988125741](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39988125741) PASS.
- **Pebblebrook hospitality, LaPlaya Beach Resort & Club, Naples, FL:** official issuer FY2024 results source (HTML SHA-256 \`033d6905706683e5bbe28ad2a30e32a5907bb5ca00bc3d6cb245048081fe5523\`) includes **$23.8m Hurricane Ian-related recognized BI insurance income for 2024**, of which the $5.4m fourth-quarter increment is included in the FY total; and historic separate 2023 amount $33m. Source FY2025 results (HTML SHA-256 \`b9d27363b9172a45f17980f99a9a2ee8a3d66f0876ed125e551a191c24d7c61b\`) report **$12.7m FY2025 Helene/Milton-related recognized BI insurance income**, of which $3.1m Q4 is included. These are recognized-accounting-income disclosures, **not independently corroborated insurer cash paid**. [Run 39988412370](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39988412370) PASS.
- **Baxter North Cove, NC:** three issuer release documents, one event; a November 2024 prospective **~$200m company-wide 2024-Q4 negative sales outlook** was published at that time. This was a **forward sales forecast**, not verified realized site profits lost, incurred insured loss, actual electric outage or paid claim. Source case [run 39982196570](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39982196570) PASS.

**First-party issuer facts are not independent insurance carrier confirmations.** Verified original-source receipt and accounting classification do not independently prove insurer policy terms, payment confirmation, or a property/meter match. Verified carrier paid-claim records **0**; independently confirmed site utility outage **0**; verified site utility-meter associations **0**; persistent backend indexed **0** and client app data deployed **0**.

### Tested coordinator-ready read-only staging contracts

1. \`facilityrisk/lane_d/query_staging.py\`: independently reviewed five-digit county FIPS; historical PNNL source episodes or **one** ORNL active county distribution, never both official ODIN direct and OpenEnergyHub mirror simultaneously. Direct feed query filters only *literal exact repeated same-snapshot source rows*, returns original native EIA-authority utility identifiers and nullable MRIDs, does not infer provider-to-building link. Real direct publisher SQLite integration [run 39998825287](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39998825287) PASS: source county \`48201\`, 62 original public status rows, 2 literal repeats withheld, 60 separate source-only findings, zero insured-site assertions.
2. \`facilityrisk/lane_d/query_eia_service_territory.py\`: exact EIA native state + county-text candidate lookup, preserving all 15 utility entities for WA/Pierce and 4 for AK/Aleutians East. Original EIA SHA/native provider evidence; no street, meter or feeder inference.
3. \`facilityrisk/lane_d/audit_native_eia_ids.py\`: source-authority utility-ID crosswalk only, not a facility-site crosswalk. In [2026-10-23 source snapshot run 39986392193](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39986392193), 77 of 86 **then-observed** ORNL source utility IDs exactly matched EIA 2025; nine absent and 12 publisher-name disagreement candidates flagged. Numbers are snapshot-specific, not permanent coverage.
4. \`facilityrisk/lane_d/query_issuer_bi_context.py\`: bounded, read-only Crane/Pebblebrook financial evidence retriever by **explicit issuer/event key**; retains accounting periods, annual/quarter inclusion, original document SHA and source categories. Real first-party downloader + two separate original-source indexes + query [run 39998559740](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39998559740) **PASS**: 4 authentic issuer documents, **12** typed indexed financial observations and provenance SHA across two companies; explicitly **0** independently confirmed carrier paid-claims or site power outages. [Short-retention safe receipt artifact 12520428472](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39998559740/artifacts/12520428472).

Reproducible staging commands:

\`\`\`bash
python -m facilityrisk.lane_d.ingest_odin_direct --output /private/lane-d/direct-current
python -m facilityrisk.lane_d.ingest_crane_bi_pdf --output /private/lane-d/crane --min-sources 2
python -m facilityrisk.lane_d.ingest_pebblebrook_bi --output /private/lane-d/pebblebrook --min-sources 2
python -m facilityrisk.lane_d.query_staging --fips 48201 --odin-direct-db /private/lane-d/direct-current/odin_direct_county_staging.sqlite
python -m facilityrisk.lane_d.query_issuer_bi_context --crane-db /private/lane-d/crane/crane_issuer_financial_staging.sqlite --pebblebrook-db /private/lane-d/pebblebrook/issuer_bi_income_staging.sqlite
\`\`\`

**Coordinator Lane E still owns deployment:** independently approved property-to-utility service evidence, site coordinate/address review, authenticated persistent server and source file storage with backups, query benchmarking, licensed ORNL redistribution, tenant isolation, shared Source Health/UI status labels and release smoke. CI artifacts are expiring staging only. SEC official archive returned 403; issuer-public filing PDFs are separate first-party distributions and have NOT been misrepresented as SEC EDGAR-origin files. No direct changes by Lane D to shared app, other lanes or \`main\`; PR #77 remains draft/unmerged.


## Data types and permissible interpretation

| Evidence class | Primary source | What it can establish | What it cannot establish |
| --- | --- | --- | --- |
| Utility reliability averages | [EIA-861 final 2025](https://www.eia.gov/electricity/data/eia861/zip/f8612025.zip) `Reliability_2025.xlsx` | Utility-reported annual SAIDI, SAIFI, CAIDI, customer counts, IEEE/other standard and major-event-day conventions; as distinct utility/state observations | Insured property's outage history, actual serving utility, lost profits, carrier payments or complete outage incidence |
| State reliability averages | Same, `State Totals` worksheet | Published state-level context under source methods | A site observation or comparable facility risk score |
| Provider/service-territory *candidates* | Same, `Service_Territory_2025.xlsx` | Utility's reported county presence by native utility ID and original county/state | Exclusive franchise/actual metered service to a particular site; verified site geography |
| Major grid disturbances | [EIA EPM Table B.1](https://www.eia.gov/electricity/monthly/epm_table_grapher.php?t=epmt_b_1) and [B.2](https://www.eia.gov/electricity/monthly/epm_table_grapher.php?t=epmt_b_2), based on DOE-417 | Date/time, reported utility, affected area, reported disturbance type, service loss category, estimated customers, source table | Verified outage at particular insured site, precise start/end of its downtime, insurance losses or a comprehensive national customer outage census |
| Financial interruption source disclosures | Crane and Pebblebrook first-party issuer PDFs/results **ingested and validated**; Baxter releases validated; SEC **original EDGAR archive remains HTTP 403** | Dated first-party site/event claims; distinctly reported insurance proceeds received, recognized BI income, forward sales forecasts, outstanding receivables | Independent insurer payment validation, policy coverage limits/wording, confirmed site electricity outage or insured physical-site crosswalk |

EIA DOE-417-derived **EPM Table B.1 is a partial 2024 table**, not a full year. Table B.2 is the published 2023 annual cohort. Neither publishes a native stable event ID; ingestion creates a **derived source-row key** consisting of URL/table/source row/raw values. Preserve no-native-ID status; never present a derived key as an official incident number.

## Real source acquisition and QA ledger — October 23, 2026

Official EIA-861 ZIP: **4,756,816 bytes**, archive SHA-256:
`f59f6c732bf685fe0a1591b32227f5ce572dc0dfd26bb5caaeed128ac4e3a396`.

| Source cohort | Real rows accepted | Rejected | Original source identity/known boundaries | Staging indexed | Durable indexed/deployed |
| --- | ---: | ---: | --- | ---: | ---: |
| EIA 2025 utility reliability (two worksheets) | **979** | 2 | 913 distinct utility IDs; source state/row/worksheet; 3 rows missing numeric SAIDI/SAIFI/CAIDI | 979 | 0 / 0 |
| EIA 2025 state aggregate reliability | **51** | 1 | State only, no utility/site ID | 51 | 0 / 0 |
| EIA 2025 county service-territory | **11,893** | 0 | 2,909 distinct utility IDs; county/state candidates | 11,893 | 0 / 0 |
| **EIA-861 total** | **12,923** | **3** | 3 rejected reporting-year rows | **12,923** | **0 / 0** |
| EIA EPM B.1 (partial 2024) | **72** | **0** | 25 source descriptions explicitly mention electric-service loss; 62 have numeric estimated customer count; 7 omit restoration timestamp | **72** | **0 / 0** |
| EIA EPM B.2 (annual 2023) | **158** | **0** | 67 source descriptions explicitly mention electric-service loss; 132 have numeric customer count; 29 omit restoration timestamp | **158** | **0 / 0** |
| **DOE-417-derived EPM total** | **230** | **0** | Source table/row provenance, no native EPM event ID | **230** | **0 / 0** |
| Site-specific outage evidence | Not tested | — | No published meter/site connection verified | 0 | 0 / 0 |
| SEC issuer interruption filings | Official EIA/SEC-independent primary source network probe **HTTP 403** | — | Three public accessions cataloged; no SEC filing bytes authenticated or issuer financial values accepted | 0 | 0 / 0 |
| Independently reconciled financial interruption / claims | Not tested | — | No issuer outcome-to-property/insured-claim match | 0 | 0 / 0 |

**Total source records staged: 13,153** = 12,923 EIA utility/state/territory records + 230 disturbance events. **Distinct inspected or insured physical sites: 0.** Staging index counts refer to *separate ephemeral SQLite databases*, not one deduplicated national facility table; cross-dataset summing does not produce facility count.

Checks: EIA-861 rejects 3 mismatched year rows; workbook sheets retained individually; repeated SAIDI/SAIFI/CAIDI headings preserved as positional columns along with `group` (IEEE/other) and `condition` (with/without major-event days/loss-of-supply treatment). Exact row duplicate handling only; never coalesce by native utility ID. Reliability workbook member SHA-256 `44384751553f4d6b17723331a8e68b03c166ad2e7a81b97659ae08d79fe91e45`; service territory member SHA-256 `0ccb4a61df01846967f765116bafe837101bddd4466d47e737eea197aa05c6d3`.

Real EIA EPM page hashes:
- B.1: 105,713-byte HTML, SHA-256 `33157ccff40391e3ca0ce07f12fe515b0c577f7a6e4f27f334bf327a62da1112`.
- B.2: 180,264-byte HTML, SHA-256 `65aadf5062687f1179302983d4cd53489d5d948bfb9f83d189e2d95ed571fecb`.

**Successful real official-source workflow:** [GitHub Actions #39973972145](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39973972145). Both `official-eia861` and `official-eia-disturbances` jobs succeeded. Separate source-only fixture tests also passed in those jobs. Machine-readable provenance/count/schema manifests are available in two short-lived GitHub Actions artifacts, **not durable hosting**. General suite run for latest head should also be checked before coordinator approval.

## Reproduction

```bash
pip install openpyxl
python -m unittest discover -s tests -p 'test_lane_d_*.py' -v
# Downloads official 2025 final ZIP; requires network access:
python -m facilityrisk.lane_d.ingest_eia861 --year 2025 --output ./private/lane-d/eia861-2025
# Or the exact official archive copied by authorized staff:
python -m facilityrisk.lane_d.ingest_eia861 --year 2025 --zip /path/to/f8612025.zip --output ./private/lane-d/eia861-2025
curl -fLS 'https://www.eia.gov/electricity/monthly/epm_table_grapher.php?t=epmt_b_1' -o /tmp/eia-b1.html
curl -fLS 'https://www.eia.gov/electricity/monthly/epm_table_grapher.php?t=epmt_b_2' -o /tmp/eia-b2.html
python -m facilityrisk.lane_d.ingest_electric_events --table b1 --html /tmp/eia-b1.html --output ./private/lane-d/events-2024-partial
python -m facilityrisk.lane_d.ingest_electric_events --table b2 --html /tmp/eia-b2.html --output ./private/lane-d/events-2023
# SEC filing HTML must originate from an authorized first-party retrieval; never claim authenticity of arbitrary local copies.
python -m facilityrisk.lane_d.ingest_sec_bi --catalog facilityrisk/lane_d/public_sec_filing_cases.toml --case baxter-helene-north-cove-2024q3 --html /path/to/approved-official-baxter-10q.html --output ./private/lane-d/sec-baxter-review
```

Outputs: source-preserving JSONL accepted/rejected rows, `manifest.json`, and read-only *logical use* local SQLite query staging files `lane_d_eia861_staging.sqlite` / `events_staging.sqlite`. The pipelines preserve original raw workbook cell arrays and EPM HTML table row values; retain **complete source ZIP and downloaded EPM HTML in restricted persistent storage** with original SHA when deployed. EIA archives may be updated in place: compare retrieved source checksum against these tested hashes before assuming identical 2025 source vintage.


## Public issuer business-interruption evidence — access validation outcome

To assess whether real facilities have experienced operating interruptions and explicitly reported costs, we identified **three primary-source SEC filing candidates** with filing-native issuer CIK, accession, original document name and text anchors. These span medical-products manufacturing, hospitality and industrial manufacturing. They are **not verified loss records** in this data pipeline.

| Sample issuer/event | Native filing identity (CIK / accession) | Source / factual boundary | Live input |
| --- | --- | --- | --- |
| [Baxter North Cove, September 2024 Helene](https://www.sec.gov/Archives/edgar/data/10456/000162828024047221/bax-20240930.htm) | 10456 / 0001628280-24-047221 | Issuer describes flood-related facility operations disruption; distinguish preliminary sales impact forecast, charges, loss and insurance recoveries | SEC 403; **not normalized** |
| [Pebblebrook LaPlaya, 2025 Q3](https://www.sec.gov/Archives/edgar/data/1474098/000147409825000138/peb-20250930.htm) | 1474098 / 0001474098-25-000138 | Property closure/damage and insurance provisions for two hurricanes; one property cannot be inferred as a utility outage | Not requested after same-origin HTTP 403 |
| [Crane Marion, 2026 Q1](https://www.sec.gov/Archives/edgar/data/1944013/000194401326000161/cr-20260331.htm) | 1944013 / 0001944013-26-000161 | Hurricane-related manufacturing site damage and insured recovery updates; keep repeated period/cumulative disclosures separate | Not requested after same-origin HTTP 403 |

Source-specific code: `facilityrisk/lane_d/ingest_sec_bi.py` and `public_sec_filing_cases.toml`; **six** offline fixture/identity/financial non-attribution tests. The importer requires official SEC accession-aligned HTTPS URL, document text and co-located event/site/BI wording. It preserves a bounded evidence excerpt, source/text hashes, issuer CIK, accession and source URL. **It deliberately extracts zero verified financial amounts and zero insured claims**; a provided local copy does not automatically prove SEC provenance. True source validation needs an allowed official response or a separately verified archival copy/checksum.

At [Actions #39975705946](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39975705946), issuer regression tests passed, but a polite official HTTPS request to Baxter's SEC EDGAR archive yielded **HTTP 403**. Rather than treating SEC as downloaded, the job uploaded `source_access.csv` and `validation_status.json` with `status=blocked`, `verified_source_documents=0`, and `verified_insured_losses=0`. The workflow job can succeed because **the access gate and its negative evidence were recorded successfully**, not because SEC filings were ingested. Subsequent same-host downloads were not attempted. EIA 13,153 staging rows remain unaffected.

**Hard blocker:** SEC EDGAR denies this GitHub-hosted runner. A compliant authorized retrieval or externally verified official filing archive is required before any financial statement is promoted to SOURCE_CONTENT_CHECKED. SEC source access must not be bypassed. No dollar amounts should be merged across quarterly/annual disclosures or classified as property/BI insurance payments without explicit coverage and payment evidence.

## Required coordinator & next-lane gates

1. **Private durable serving:** install source archives and local indexes under authenticated, backed-up backend; perform read-only SQL search and source ID sample checks. GitHub Pages/CI artifacts are not persistent data services. Coordinator Lane E owns common Source Health/UI/schema/report.
2. **Validate location/provider candidates:** source county-level coverage alone is insufficient for confirmed service to any insured physical site; corroborate utility account, meter, tariff or independently verified provider-to-site evidence. Keep different regulator/provider identities separate and review-only.
3. **Disturbance chronology:** track report time versus outage/restoration time and incomplete/estimated values. Do not infer zero from unknown. Distinguish full-year and partial B.1 and B.2 source windows; do not use as comparable national incident rates. EIA's EPM is not native DOE-417 event ID dataset.
4. **Business interruption cases:** obtain official issuer SEC filing accession, dated passage/financial table, event window, explicit site if reported and currency/unit. Separate direct physical damage, downtime, sales/revenue, margin/lost profit, extra expense, and insurance recoveries. Prevent repeated quarterly/annual disclosure amounts being added together. Never label losses insured without actual coverage evidence. Financial verification remains outstanding.
5. **Acceptance:** CI, actual source downloads with hashes, reconciliation, reviewed source licenses/terms, durable index benchmark, facility candidate review and a live backend/browser test before marking `DEPLOYED`. No score/ranking until independently validated outcomes and denominator.

No edits outside the Lane D importers, tests, workflow and this document; don't merge PR #77.


---

## Additional official-source validation — 23 October 2026 (Lane D continuation)

The following are actual publisher downloads executed in the official-source GitHub Actions runners, with original-source provenance and SQLite count checks. Counts are observations of different source kinds and cannot be summed as unique outage incidents, utility customers or insured facilities.

### DOE/PNNL Event-correlated Outage Dataset in America (2014–2023)

Primary source: https://data.openei.org/submissions/6458 . Exact publisher ZIP: https://data.openei.org/files/6458/Outage_Dataset_R1.zip . PNNL (She, Adetola & Yun, 2024), CC BY 4.0 per https://catalog.data.gov/dataset/event-correlated-outage-dataset-in-america . Retain author/source credit and attribution in all redistributions. Dataset is produced from historical EAGLE-I and DOE-417 event correlation; NOT an insurer property claim census.

- Archive: 31,260,449 bytes; SHA-256 44557bae7a5c8e02c611a14f75fe9e123d81d286f700b9fd88ac538edd910fe7 ; 51 archive members, of which 50 distinct source CSVs.
- Source records: downloaded/scanned 2,124,183; normalized 2,124,183; rejected 0; indexed in local transient SQLite 2,124,183; durable backend indexed 0; insured-site outages verified 0; deployed 0.
- 2014–2023 accepted row partitions: 1,385,389 county outage episodes (MERGED); 526,165 DOE-event-correlated county observations; 91,402 eight-hour correlation-lag variants; 114,610 twenty-four-hour correlation-lag variants; 6,617 state/month aggregate rows. Month=0 in the last category is a publisher aggregate, NOT a calendar month.
- Geographic coverage: 2,985 unique five-digit county FIPS and 54 distinct source state/territory NAME strings (includes two aliases for U.S. Virgin Islands). Source times: 2014-11-01 through 2023-12-31, no original timezone imputed.
- Native event identities: 2,922 distinct (source-year, event_id) pairs in event-correlation families. Event ID repeats across counties; merged county outages have NO published native event ID. 288,519 candidate repeated county/time/event-key occurrences retained: NOT 288,519 confirmed duplicates and NOT separately countable losses.
- QA: 50/50 publisher table schemas recognized; each original CSV recount exactly agrees with importer, manifest and SQLite by type; member SHA-256s recorded; SQLite integrity_check=ok, original archive checksum verified. No invalid rows rejected in this publisher ZIP.
- Actual CI and provenance receipt: https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39980242383
- Reproducible command: python -m facilityrisk.lane_d.ingest_pnnl_county_outages --zip /path/Outage_Dataset_R1.zip --output /private/lane-d/pnnl

### DOE/ORNL ODIN public near-real-time county outage snapshot

ORNL ODIN official public dataset https://openenergyhub.ornl.gov/explore/dataset/odin-real-time-outages-county/ and export https://openenergyhub.ornl.gov/api/explore/v2.1/catalog/datasets/odin-real-time-outages-county/exports/json . Snapshot source is changing, so every collection must preserve its own observed time/hash and must not be summed across refreshes. Public availability does NOT establish unrestricted redistribution or commercial-use terms; policy review remains open.

- Observed official 2026-10-23 15:42 UTC JSON export: 1,782,901 bytes; SHA-256 2e23afd647119793b15499c3210508142faca8de5f7aae014d7af502abf4366f.
- Downloaded 424 source records, accepted 423, rejected 1 due nonempty invalid date, transient SQLite indexed 423. Durable backend indexed/deployed 0/0. There were 160 legitimate publisher NULL start times, recorded as UNKNOWN instead of falsely rejecting or inferring zero downtime.
- Geographic scope of this particular snapshot: 241 county FIPS, 37 source states, 89 native utility IDs. No duplicate complete raw-row fingerprints among 423 accepted observations. FIPS geometry is county context, NOT facility coordinates or a verified metered-utility link. Insured facility outage and business-interruption amount verification both zero.
- Official row-by-row source JSON/hash versus SQLite query validation: https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39980518977
- Reproduce: python -m facilityrisk.lane_d.ingest_odin --output /private/lane-d/odin-snapshot

### First-party Baxter corporate operations interruption case

SEC EDGAR remains access blocked with HTTP 403 from the GitHub Actions runner. Rather than bypass this restriction, the importer uses three actual first-party Baxter issuer investor-relations publications dated September 29 2024, November 8 2024 and February 20 2025 relating to the North Cove manufacturing facility interruption. They are ONE underlying company-reported hurricane-related interruption, NOT three unrelated insured losses and NOT evidence of an independently confirmed electric utility power outage. All issuer publication title/date/event/site/interruption anchors validated, original exact HTTPS URLs and HTML SHA-256 preserved.

- Actual source documents: 3 downloaded / 3 normalized / 3 staged SQLite / 0 rejected; one underlying issuer-reported operational event; financial insured claims amounts verified 0; deployed 0.
- HTML source hashes (same release-date order): a7f6e83f2f3cdb7b6135e4316c6bb9add083e5b73ff12ba69e7af9ddfb8668a6 ; ab45a54c091f4bb1f66def24521168a28a29018281d6026c43ff35d7f24161e3 ; 93b90a697ce9110a0e69dcb64b2e47b0f85dc3f3dd91caa6d4627630314c4781.
- Official first-party validation run: https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39978131475 . Original publisher URL references and permitted provenance fields are defined in facilityrisk/lane_d/ingest_issuer_release.py. No financial loss, sales disruption cost, insurance proceeds, claim payment or outage duration is auto-inferred.

### Read-only county context contract for Lane E

facilityrisk/lane_d/query_staging.py has an isolated, bounded county-FIPS query against PNNL and ODIN SQLite source-only stores, with category-specific results and SHA/row IDs. It prevents input injection and does NOT assign power providers, verify a property/meter, score an insured risk, or equate county events with insured premises. Example:

python -m facilityrisk.lane_d.query_staging --fips 01001 --pnnl-db /private/lane-d/pnnl/pnnl_county_outage_staging.sqlite --odin-db /private/lane-d/odin-snapshot/odin_county_outage_staging.sqlite --limit 10

Run tests: python -m unittest discover -s tests -p 'test_lane_d_*.py' -v . CI validates SQLite row counts, source-row provenance and in-source rejections; no table is merged with other workstreams. Coordinator must separately import a reviewed Lane D source-only index into private durable serving and set shared Source Health from REAL deployed/queried evidence, not from local staging.

### Unresolved hard blockers (do not mark Lane D complete yet)

1. Persistent backed-up server-side storage for all official archives and normalized source-only indexes; cannot use GitHub Pages or expiring Actions artifacts as long-lived backend. Durable indexed/deployed rows all ZERO.
2. Independently verified insured physical-site to serving-utility connection, and independent site power outage corroboration. No automatic provider assignment from source county or utility name; insurer facility-verified rows ZERO.
3. Actual financial interruption, revenue margin/downtime, coverage and paid-insurance-claim evidence, with source accession and consistent accounting periods. SEC original archive returned HTTP 403 from Actions; do not bypass. Public EAGLE-I 2014 Opendatasoft endpoint likewise returned HTTP 403, addressed with authorized official PNNL archive instead.
4. Publisher data-use/redistribution policy for ORNL ODIN current snapshots; explicit public API access alone is not a distribution license.
5. Shared backend interface integration, actual service query benchmark, authentication and live browser smoke. These belong to coordinator Lane E; this branch changes no other lane/shared UI/registry files.

All recorded counts distinguish downloaded, accepted/rejected, ephemeral SQLite indexed, durable backend indexed, facility verified, and deployed. Success of synthetic tests, official data download or staging does not satisfy deployment or insured-claim verification.


### Quantified issuer guidance is NOT an insured interruption claim

The issuer November 8, 2024 Baxter Q3 results source explicitly forecasts that Hurricane Helene would negatively affect its **total company 2024 Q4 sales by approximately USD 200 million** (not necessarily North Cove alone). The source was independently downloaded with original publisher title/date and event/site/operational-disruption anchors, and the source text quantitative anchor was confirmed using explicit near-text matching for hurricane + company fourth-quarter sales + negative forecast. Actual CI [issuer forecast evidence #39982196570](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39982196570) PASS.

The value is published MANAGEMENT GUIDANCE AS OF NOVEMBER 8, 2024, not retrospectively verified lost profit, property damage, insurer reserve, covered business-interruption amount, or claim paid. The February 2025 annual release notes a smaller adverse impact than anticipated; the November estimate must not be reinterpreted as realized full-year results. Original November source: https://investor.baxter.com/investors/events-and-news/news/press-release-details/2024/Baxter-Reports-Third-Quarter-2024-Results/default.aspx . Later 2025 source: https://investor.baxter.com/investors/events-and-news/news/press-release-details/2025/Baxter-Reports-Fourth-Quarter-and-Full-Year-2024-Results/default.aspx .

There is **one** anchored companywide negative SALES forecast (approximately USD 200m) across the three Baxter releases, **zero independently confirmed realized margin losses, and zero insured loss payments**. Issuer-release HTML may include dynamically changing page elements: even with the same publisher URL/byte count a later original HTML SHA-256 can differ. Preserve download-specific archive hash, URL/date and source extracted text/excerpt hashes on each run; do not assume an old HTML hash is immutable while publication text remains unchanged.

---

## Corrected deduplication, primary ODIN API and provider source coverage (2026-10-23 follow-up)

### Historical DOE/PNNL source rows include 277,360 literal same-table duplicates

Official source-vintage counts remain unchanged: 2,124,183 downloaded and accepted original CSV records, 0 rejected, 2,124,183 temporary SQLite rows, 0 durable indexed and 0 deployed. An independent SHA-256 census of each original CSV table detected **277,360 exact repeated complete source rows in a single original table**. Therefore **1,846,823 source-table-content-distinct rows** remain after fingerprinting within each table. This is not a count of unique outage episodes or unique insured properties. Duplicates occur in 273,291 correlated event rows, 2,094 twenty-four-hour lag rows and 1,975 eight-hour lag rows; merged county episode files (1,385,389 rows) and state/month aggregate files (6,617) contain zero exact row duplicates. Source event-correlation joins can repeat observations, especially in 2021–2023.

All official source-position records are retained. The importer now writes **is_exact_duplicate_source_row** and **duplicate_of_source_line** into normalized JSONL and SQLite, with member-local first occurrence, and checks total duplicate flags against 50 per-member counts. Do not silently deduplicate/merge canonical sites or count repetitive join rows as additional outages. Latest original ZIP/SQLite/duplicate gate: https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39984734680 (PASS). Archive SHA256 44557bae7a5c8e02c611a14f75fe9e123d81d286f700b9fd88ac538edd910fe7. Original historical source license is explicitly CC BY 4.0 on https://data.openei.org/submissions/6458; credit Buxin She, Veronica Adetola and Ji Young Yun (2024), link license and identify changes when reusing. Repetitions and lag variants are not 277,360 extra losses or sites.

### Native ORNL ODIN direct public county feed

First-party, non-authenticated endpoint https://odin.ornl.gov/odi . Authoritative ORNL documentation describes this as county-level public current outage information; more granular data require authentication and agency approval. This is **separate distribution of partly overlapping information** from the Open Energy Hub ODIN county dataset, not an independent outage series. Source identity includes original **MRID / mrid** (which may be null or repeat across county), the original **communityDescriptor** five-character county FIPS, and **EIA-authority UtilityId / UtilityName** annotations from the **names** array. Native identity is not an insured site meter/service connection.

Verified 2026-10-23 16:15:38 UTC first-party original JSON: 498,015 bytes, SHA-256 19ca8e195ac765159168b0a32d459e3bf171fc058de84b3db148db1734025a9a. **558 source rows downloaded / 558 accepted and indexed in separate temporary SQLite / 0 rejected**. Actual observed: 248 distinct county FIPS, 89 native EIA provider IDs, 6 exact repeated source rows flagged without removal, 170 unavailable native MRID, 157 absent publisher start timestamps preserved as UNKNOWN, only county publisher geometry resolution. Source-raw byte and per-record SHA, original position, snapshot time and all original fields retained; independent source-to-staging SQLite checks pass. Genuine CI: https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39985271905 . Reproduce via python -m facilityrisk.lane_d.ingest_odin_direct --output /private/lane-d/odin-direct .

**DO NOT ADD** this 558-row direct first-party feed to the older 423-row mirror snapshot or to later direct snapshots as distinct physical outages. Snapshot timing and reported active states differ. No insured facility outage, affected insured meter or paid interruption claim was verified. The independent official-publisher source must be retained privately until ORNL distribution terms and permitted commercial reuse are reviewed.

### ORNL participating utility status is NOT a service-provider assignment

First-party endpoint https://odin.ornl.gov/odi/status . Current actual official 2026-10-23 16:18 UTC response: 37,460 bytes, SHA-256 2ee5f692d225db5a0d8b9ec35b93100d9609817b0d231cc38ee2416ee462d096; **157 rows downloaded / 157 normalized / 157 temporary SQLite indexed / 0 rejected**. Source provided 157 distinct native dataId values, 157 EIA-identifier values, and reported `hasError` true for **10**, false for **147**. This is a **feed participation and source-health inventory**. A status row is not an insured property, power outage, or confirmation of a utility serving a specific building; hasError=false does not guarantee current completeness. Original utility data ID, reported data resolution, receivedDate, vendor/source name and original raw row/checksum preserved; outageFeed links were NOT followed. QA source row and index check PASS: https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39985698922 . Reproduce: python -m facilityrisk.lane_d.ingest_odin_participants --output /private/lane-d/odin-participants .

### EIA-861 exact native utility provider candidates

Separate module **facilityrisk/lane_d/query_eia_service_territory.py** enables safe, read-only 2025 EIA electrical utility provider *candidates* by exact state abbreviation and official source county text, preserving native EIA Utility Number, source utility name, original workbook row SHA, and zero or more same-state source-native utility reliability rows with original positional measurements. It returns every provider candidate rather than choosing one for an insured location; it does not fuzzy-match counties, infer a site-to-utility service connection, or cover gas/water/comms service. Live official-source QA on real 2025 EIA SQLite PASS: https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39983816113 : Washington/Pierce County **15 EIA source utility candidates**; Alaska/Aleutians East **4**. Both observations leave independently verified insured utility assignments **0**.

### Source licensing and release gate

The PNNL OEDI publication explicitly links Creative Commons Attribution 4.0 (https://creativecommons.org/licenses/by/4.0/), allowing commercial reuse subject to attribution, license link and marking changes; no claim of producer endorsement. The ORNL ODIN Subscriber Guide (https://odin.ornl.gov/downloadables/ODIN_Subscriber_Guide.pdf) documents public county access versus approved granular subscription. The Open Energy Hub domain's general terms (https://openenergyhub.ornl.gov/terms/terms-and-conditions/) require checking applicable per-dataset license and attribution, so **ORNL direct/mirror reuse rights are NOT treated as automatically unrestricted for customer-facing commercial redistribution**. Use temporary private validation until source-specific licensing is confirmed.

Source-only coordinator staging handoff artifact: EIA-861 2025 SQLite (5,996,544 bytes, SHA256 ff0b25fac8f0fb2508b598ec4aea5697481a854509e4d77ba24b5685611de39b, 12,923 rows) from https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39982594723/artifacts/12514425884 (independently downloaded and tested SQLite integrity OK). PNNL latest 2,124,183-row duplicate-flagged SQLite is produced under https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39984734680 with 3-day artifact expiration, original source archive SHA and separate provenance manifest. Historical source files and private SQLite must be installed on durable backed-up authenticated infrastructure by Lane E; no staging artifact is itself DEPLOYED.

**Remaining independently verified insured site-to-meter utility connections 0; independently proven insured site power outages 0; claims/loss amounts and actual claim payments 0; durable private service indexed 0; app data deployed 0.** SEC issuer primary filing retrieval still returns HTTP 403 from GitHub-hosted runner; first-party Baxter issuer disclosures support operations interruption and a 2024 Q4 prospective sales estimate, not retrospectively verified covered claims. Coordinator Lane E remains sole owner of shared Source Health files, production serving/index migration, client/report UX, site-review evidence and merging.
