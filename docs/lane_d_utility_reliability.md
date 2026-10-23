# Lane D — utility reliability, grid disturbances and business-interruption evidence

**Scope:** all industries and all facility types. Isolated ingestion modules; no shared application, canonical site registry, report UI, or Source Health edits. Dedicated draft PR #77, coordinated in issue #73. All numbers below are **observed from real official-source GitHub Actions runs** on 2026-10-23, not synthetic test fixtures. All datasets are still **nonproduction staging**.

## Data types and permissible interpretation

| Evidence class | Primary source | What it can establish | What it cannot establish |
| --- | --- | --- | --- |
| Utility reliability averages | [EIA-861 final 2025](https://www.eia.gov/electricity/data/eia861/zip/f8612025.zip) `Reliability_2025.xlsx` | Utility-reported annual SAIDI, SAIFI, CAIDI, customer counts, IEEE/other standard and major-event-day conventions; as distinct utility/state observations | Insured property's outage history, actual serving utility, lost profits, carrier payments or complete outage incidence |
| State reliability averages | Same, `State Totals` worksheet | Published state-level context under source methods | A site observation or comparable facility risk score |
| Provider/service-territory *candidates* | Same, `Service_Territory_2025.xlsx` | Utility's reported county presence by native utility ID and original county/state | Exclusive franchise/actual metered service to a particular site; verified site geography |
| Major grid disturbances | [EIA EPM Table B.1](https://www.eia.gov/electricity/monthly/epm_table_grapher.php?t=epmt_b_1) and [B.2](https://www.eia.gov/electricity/monthly/epm_table_grapher.php?t=epmt_b_2), based on DOE-417 | Date/time, reported utility, affected area, reported disturbance type, service loss category, estimated customers, source table | Verified outage at particular insured site, precise start/end of its downtime, insurance losses or a comprehensive national customer outage census |
| Source financial disclosures | SEC issuer filings and official investor reports; **source access probed, blocked by HTTP 403 in CI** | Dated source-attributed issuer disclosure, specific named site/event if actually stated, measured versus forecast financial impact and separately stated insurance proceeds | A third-party property claim or insured BI amount without explicit evidence and proper time/denominator context |

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
