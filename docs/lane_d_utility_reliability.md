# Lane D — utility reliability, grid disturbances and business-interruption evidence

**Scope:** all industries and all facility types. Isolated ingestion modules; no shared application, canonical site registry, report UI, or Source Health edits. Dedicated draft PR #77, coordinated in issue #73. All numbers below are **observed from real official-source GitHub Actions runs** on 2026-10-23, not synthetic test fixtures. All datasets are still **nonproduction staging**.

## Data types and permissible interpretation

| Evidence class | Primary source | What it can establish | What it cannot establish |
| --- | --- | --- | --- |
| Utility reliability averages | [EIA-861 final 2025](https://www.eia.gov/electricity/data/eia861/zip/f8612025.zip) `Reliability_2025.xlsx` | Utility-reported annual SAIDI, SAIFI, CAIDI, customer counts, IEEE/other standard and major-event-day conventions; as distinct utility/state observations | Insured property's outage history, actual serving utility, lost profits, carrier payments or complete outage incidence |
| State reliability averages | Same, `State Totals` worksheet | Published state-level context under source methods | A site observation or comparable facility risk score |
| Provider/service-territory *candidates* | Same, `Service_Territory_2025.xlsx` | Utility's reported county presence by native utility ID and original county/state | Exclusive franchise/actual metered service to a particular site; verified site geography |
| Major grid disturbances | [EIA EPM Table B.1](https://www.eia.gov/electricity/monthly/epm_table_grapher.php?t=epmt_b_1) and [B.2](https://www.eia.gov/electricity/monthly/epm_table_grapher.php?t=epmt_b_2), based on DOE-417 | Date/time, reported utility, affected area, reported disturbance type, service loss category, estimated customers, source table | Verified outage at particular insured site, precise start/end of its downtime, insurance losses or a comprehensive national customer outage census |
| Source financial disclosures | SEC issuer filings and official investor reports; **not yet ingested** | Dated source-attributed issuer disclosure, specific named site/event if actually stated, measured versus forecast financial impact and separately stated insurance proceeds | A third-party property claim or insured BI amount without explicit evidence and proper time/denominator context |

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
| Financial business interruption / claim recoveries | Not tested | — | No issuer accession or event-to-site outcome crosswalk yet | 0 | 0 / 0 |

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
```

Outputs: source-preserving JSONL accepted/rejected rows, `manifest.json`, and read-only *logical use* local SQLite query staging files `lane_d_eia861_staging.sqlite` / `events_staging.sqlite`. The pipelines preserve original raw workbook cell arrays and EPM HTML table row values; retain **complete source ZIP and downloaded EPM HTML in restricted persistent storage** with original SHA when deployed. EIA archives may be updated in place: compare retrieved source checksum against these tested hashes before assuming identical 2025 source vintage.

## Required coordinator & next-lane gates

1. **Private durable serving:** install source archives and local indexes under authenticated, backed-up backend; perform read-only SQL search and source ID sample checks. GitHub Pages/CI artifacts are not persistent data services. Coordinator Lane E owns common Source Health/UI/schema/report.
2. **Validate location/provider candidates:** source county-level coverage alone is insufficient for confirmed service to any insured physical site; corroborate utility account, meter, tariff or independently verified provider-to-site evidence. Keep different regulator/provider identities separate and review-only.
3. **Disturbance chronology:** track report time versus outage/restoration time and incomplete/estimated values. Do not infer zero from unknown. Distinguish full-year and partial B.1 and B.2 source windows; do not use as comparable national incident rates. EIA's EPM is not native DOE-417 event ID dataset.
4. **Business interruption cases:** obtain official issuer SEC filing accession, dated passage/financial table, event window, explicit site if reported and currency/unit. Separate direct physical damage, downtime, sales/revenue, margin/lost profit, extra expense, and insurance recoveries. Prevent repeated quarterly/annual disclosure amounts being added together. Never label losses insured without actual coverage evidence. Financial verification remains outstanding.
5. **Acceptance:** CI, actual source downloads with hashes, reconciliation, reviewed source licenses/terms, durable index benchmark, facility candidate review and a live backend/browser test before marking `DEPLOYED`. No score/ranking until independently validated outcomes and denominator.

No edits outside the Lane D importers, tests, workflow and this document; don't merge PR #77.
