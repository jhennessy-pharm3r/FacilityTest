# Lane C — USCG NRC, CSB and PHMSA industrial incident source evidence

> **Latest supplemental evidence (October 23, 2026):** The historical 2015–2025 NRC and September CSB cohorts total **265,762 accepted and temporarily indexed observations**, with zero production deployment ([run 39982322011](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39982322011)). A *separate current-year probe* downloaded and staged the **provisional NRC CY2026 workbook with 17,827 notifications**, 4,039 source-reported DMS coordinates, 0 missing child joins, raw SHA-256 `d4da14c0e8a67b230b2dcdd000b24df1e0e7f6ca30d422a8e49b4f3e80ba1155`; this 2026 cohort awaits incorporation into the consolidated source index ([run 39984710623](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39984710623)). Official CSB June and September 2026 XLSX were both downloaded: June **652** rows, September **675** raw rows, same published Number value for 652 records, but **19** Numbers carry changed date/company/city/state attributes; all 19 differ on multiple fields. **Number is NOT safely cross-vintage permanent** ([run 39984891183](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39984891183)). Also recovered official **PHMSA Pipeline Enforcement Raw Data** on a different first-party host: **5,089 genuine enforcement-case rows downloaded, 5,089 normalized, 5,089 indexed only in disposable CI SQLite, 0 rejected, 0 duplicate CPF_Number, 453 linked-report references (403 distinct typed identifiers)**, raw SHA-256 `23d8d5c62dd93f848ba3f22d4fc24d0c7f3d90b750aea2ac7223168401725bb7`, normalized SHA-256 `b0f0481db314f387d0e7b464c2ebaceb2227d42cd0e283e9a69c0ee8be8f3deb`. This **is NOT a PHMSA accident census**, never mix with NRC/CSB incidents ([run 39985148724](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39985148724)).

**Additional official NRC 2010–2014 cohorts are being validated independently; no counts claimed pending completed real run.** The original direct PHMSA pipeline/hazmat report ZIPs remain blocked by HTTP 403/login; production indexed/deployed incident observations and verified insured properties remain **0**. For integration, Lane E may run `python scripts/run_lane_c_verified.py --output /secure/qa/lane-c --private-bundle-dir /secure/private/lane-c-release` on an explicitly pre-provisioned private mount **outside** the repository to retain source originals, normalized files, source manifests and SQLite; this opt-in export is still not a production service or insured-site crosswalk. The default CI run publishes **aggregate-only** JSON evidence.

**Last real validation:** 2026-10-23. **Current state:** NRC CY2020–CY2025 and CSB 2026-09 release downloaded, normalized, content validated and **indexed in a temporary source-only SQLite database**. PHMSA source incident files remain inaccessible from the GitHub Actions runner. **Nothing has been deployed in a durable private service or in the app.** PR #79 stays DRAFT / UNMERGED; Lane E alone owns cross-lane UI, common registry, production serving and merge approval.

- Real official-source + combined SQLite + review-candidate verification: [GitHub Actions run 39979735899](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39979735899), **SUCCESS**; aggregate-only QA artifact **12512054497**. 
- Repo-wide CI: [run 39979745165](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39979745165), **SUCCESS**.
- Earlier verified annual source check: [run 39979162538](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39979162538), **SUCCESS**. Counts below are regulator **source observations**, not independently corroborated accidents, properties, insured losses or claims.

## Real source ingestion ledger

| Source and vintage | Official raw bytes | Raw source rows | Accepted | Rejected | Distinct native IDs within vintage | Reported DMS coordinates | Missing coordinates |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NRC 2020 | 13,998,110 | 22,503 | 22,503 | 0 | 22,503 | 2,864 | 19,639 |
| NRC 2021 | 14,979,248 | 24,540 | 24,540 | 0 | 24,540 | 3,523 | 21,017 |
| NRC 2022 | 14,738,356 | 23,510 | 23,510 | 0 | 23,510 | 3,269 | 20,241 |
| NRC 2023 | 14,703,606 | 23,143 | 23,143 | 0 | 23,143 | 3,527 | 19,616 |
| NRC 2024 | 15,151,431 | 22,966 | 22,966 | 0 | 22,966 | 3,865 | 19,101 |
| NRC 2025 | 18,026,065 | 21,533 | 21,533 | 0 | 21,533 | 3,999 | 17,534 |
| CSB 2026-09-01 | 62,290 | 675 | 674 | 1 | 674 release-scoped IDs | 0 | 674 |
| **Combined** | — | **138,870** | **138,869** | **1** | 138,869 source-vintage IDs | **21,047** | **117,822** |

The CSB rejection is **1 missing/invalid incident date**. Each NRC annual workbook's CALLS / INCIDENT_COMMONS / INCIDENT_DETAILS sheets joined completely by `SEQNOS`; no missing cross-table keys or invalid/missing incident dates were reported. All NRC annual normalizations passed repeat-byte SHA validation and had zero duplicate `SEQNOS` in their respective master sheets. NRC coordinates derived from the official degree/minute/second/hemisphere fields are **approximate source-reported locations**, not insured-property points or known impact footprints. Missing does not mean no incident or no site risk.

### Official provenance: original and normalized SHA-256

| Agency/vintage | Original XLSX SHA-256 | Deterministic normalized gzip SHA-256 |
| --- | --- | --- |
| NRC CY2020 | `bde99b7eb6f2accf03e003af71396ecb9057dcf167b4065b2ded6da04b402de4` | `3603df6d00ab2e01022b2d70b6d27f86d8f1c268de0e7aaa303342947d4569c7` |
| NRC CY2021 | `248e61b6335aa3e3411ebd5680fb48a6aa98a7aab6e21427a80430fc70d688c1` | `a1c672bb23986bbedc8b76308f2132fe108420d00037719d08c2f798366e984f` |
| NRC CY2022 | `38736e0010cdb43c0fe4dd5d161b167d3c40f0767f4515d41c2145e5c95d759f` | `7939a4924b96d2293fb572a0af68e9a713f88911c6335906fa77ddc74f150260` |
| NRC CY2023 | `c177d1b7352360c69a7c316ec2b1237e5af9e75b2e63caaa78bd3878e5687a82` | `4848087ef72cd9f9b0dfd8e8873a4b27ab6a4c54de1863385d0f96c76f881d2c` |
| NRC CY2024 | `3ec11e1c44a1a5c39fda9560018cacfd5a0dd8b9234056b896fb4d4ff97a26e1` | `86e490333ce9479a3fee9dd1eeb53a0ea3de223146fb019930a1a2c7a48efcee` |
| NRC CY2025 | `086da221569b5bbccb0f8170c54fd83c11cf8b7894258bfdea2c60a218407bda` | `f7421c83699933b1970eb777aae680ba3165b4bdf453ffd2c8004ae3e5042dde` |
| CSB 2026-09 | `dbea875040e7ddfebfbe295c1731faab5f4c3829784c0c93dbb8d054c10b9dc1` | `63affa5d7fcf06adc6805f39673f1a4891e8f57f0406244b031c9745c102da12` |

Upstream NRC: `https://nrc.uscg.mil/FOIAFiles/CYYY.xlsx` (2020–2025 correspond to CY20–CY25). CSB: `https://www.csb.gov/assets/1/6/Copy_of_Accidental_Release_Events_2026-09-01.xlsx`. Both original unmodified source bytes and row-level transforms are **kept on the disposable Actions runner only**; public GitHub artifacts contain **aggregate JSON manifests**, not report rows, personal names or database contents. Repeated transformations of the same official byte stream generate identical normalized hashes, verified in CI. The deterministic gzip intentionally changes the SHA relative to earlier non-deterministic staging; those older SHA claims are superseded by the table above.

## Indexed, served and deployed counts: separate gates

| Stage | NRC CY2020–2025 | CSB | PHMSA |
| --- | ---: | ---: | --- |
| Official source downloaded (rows) | 138,195 | 675 | **NOT DOWNLOADED** |
| Normalized/accepted | **138,195** | **674** | **NOT TESTED** |
| Indexed in **disposable CI source-only SQLite** | **138,195** | **674** | **NOT TESTED** |
| Persistently indexed and authenticated in production | **0** | **0** | **0 deployed/available (coverage unverified)** |
| Verified live app deployment | **0** | **0** | **0** |
| Independently corroborated source-to-insured-site links | **0** | **0** | **0** |

One consolidated temporary SQLite contains **138,869 source observations** split into seven namespaces (six NRC annual cohorts plus CSB). Validated SQL indexes on source/native ID, dates, state and coordinates; `PRAGMA quick_check=ok`, all source row counts reconcile, query paging/count checks **PASS**. The ephemeral source database has **no tenant/client data, no automatic canonical physical-site mapping** and is **not uploaded to a publicly accessible artifact**. Runtime hosting/private authentication/integration on real assets is coordinator Lane E's task.

### Cross-agency source candidates, not automatic matches

The strict `scripts/lane_c_review_candidates.py` checks independently reported **exact calendar day, normalized US state, city, and non-generic company name**, never geocoding unknown properties or equating organizations automatically. Live run found **119 NRC–CSB candidate pairs referencing 74 distinct CSB release rows**. These may be multiple NRC notifications for one reported event, unrelated observations, shared corporate names, or bad source text: **0 pairs were manually confirmed**, **0 physical sites verified**, **0 loss or injury outcomes corroborated**. Review-table status is `review_candidate_not_corrob`; an index row is not a confirmed facility, insured claim or coverage decision.

## PHMSA: real official distribution diagnostics and hard blocker

Official pipeline reporting: [PHMSA source data](https://www.phmsa.dot.gov/data-and-statistics/pipeline/source-data) / [operator submissions and publication ZIPs](https://www.phmsa.dot.gov/data-and-statistics/pipeline/distribution-transmission-gathering-lng-and-liquid-accident-and-incident-data). These operator-submitted incidents have different report types and reporting-vintage semantics from NRC notifications or CSB 40 CFR Part 1604 reports.

On networked GitHub Actions, tried **four separate PHMSA official ZIP URLs**: hazardous liquid accidents 2010-present, gas distribution incidents 2010-present, gas transmission/gathering incidents 2010-present, and flagged incidents. All responded **HTTP 403 Forbidden** to the automated runner. Tried separate [PHMSA hazmat incident report portal](https://portalpublic.phmsa.dot.gov/analytics/saw.dll?Portal); it redirected to an inaccessible login endpoint with an HTTP (not HTTPS) redirect; no authentication/circumvention was attempted. Official DOT Socrata `data.transportation.gov/api/views/27nc-rsge.json` returned **HTTP 200 metadata only**, **not** individual PHMSA incident rows; likewise the DOT hazmat public catalog points to an interactive export portal, not a verified programmatic source of report rows. All failures and exact official endpoints appear in the [live run QA artifact](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39979735899/artifacts/12512054497).

**PHMSA accepted, rejected, indexed, longitudinal coverage, native incident IDs and loss amounts remain NOT TESTED**; do not represent a 403 as zero reported incidents. Appropriate resolution: obtain ordinary agency-permitted file access from an approved environment or documented redistribution contract; then inspect actual ZIP member schema, choose operator-submission report grain, validate source-native operator/report numbers and dates, handle commodity subrows without double counting, preserve raw source bytes/checksum, and run QA into this lane-owned source index before any coordinator integration. **No bypass of access controls or unverified third-party mirror.** Historical PHMSA archive years, LNG/UNGS and hazmat exports remain uncovered until that approval/access is resolved.

## Reproducibility and integration contract

From the repository root on a network-enabled authorized runner:

```bash
pip install -r requirements.txt -r requirements-dev.txt openpyxl requests
python -m pytest -q tests/test_industrial_incidents.py tests/test_nrc_enriched.py tests/test_csb_release.py tests/test_lane_c_index.py tests/test_lane_c_candidates.py
python scripts/run_lane_c_verified.py --output output/lane-c-validation
```

- Source download, multi-sheet NRC source-key join, CSB row-2 header parser, DMS precision guards, null/duplicate/date/schema checks, original and normalized SHA-256, repeatability, acceptance ledger, **separate indexed count**, combined query/reconciliation and reviewed-candidate-only rules execute together.
- `scripts/build_industrial_incidents.py` supports explicit `--source`/`--raw`/`--sheet` or `--member` and verified publisher header mapping for future PHMSA CSV/TXT/ZIP import. **Do not use unverified default mappings as evidence that a PHMSA source was ingested.** The targeted NRC and CSB modules above have actual verified live publisher mappings.
- Public CI artifact `output/*.json` publishes only aggregate source status/QA fields, no raw NRC free text, incident personnel identifiers, raw incident rows or SQLite. For production, a coordinator-managed authenticated and tenant-isolated read-only source index must persist the stage output and provide an audit-controlled, reversible site-candidate review workflow.
- All industries/facility types are in downstream candidate scope; no pharma-only filtering, no inference that absence of regulatory report means low risk, no insurance loss or parametric payout inferred from incident reports.

## Open acceptance gates (do NOT mark Lane C complete)

1. **PHMSA:** official downloadable or otherwise authorized operator and hazmat report-row access, schemas, IDs, accepted/rejected/included years and hashes, standalone verified indexed runs. Currently external 403/login hard blocker. Reported pipeline severity outcomes are not insured losses.
2. **CSB:** release `Number` uniqueness only verified **within September 2026 release**. Cross-quarter identifier stability/corrections and actual semantics of categorical Fatality/Injury/Property Damage/Report markers not independently established; no casualty/dollar amounts inferred.
3. **NRC:** six recent annual cohorts are content validated; earlier history and current 2026 partials are **NOT TESTED**. Raw source records and onshore/offshore coordinate uncertainty must remain visible; no national facility coverage claim.
4. **Coordinator-owned Lane E:** persistent private source index with auth, scheduled freshness checks, common provenance manifest, review-only physical-site crosswalk, evidence/outcome corroboration, app Source Health status and live backend deployment checks. None performed in Lane C.
5. **Final release:** verified cross-regulator physical location corroboration and independent safety/outcome evidence. No source-only row can automatically become a risk score or claims-based damage record. PR [#79](https://github.com/jhennessy-pharm3r/FacilityTest/pull/79) remains **DRAFT / DO NOT MERGE** until coordinator confirms gates.

### Ownership and evidence boundaries

Only Lane C-owned scripts, tests, runbook and standalone GitHub workflow are changed. Lane A FEMA/wildfire, Lane B EPA, Lane D utilities, Lane E common registry/UI/Source Health and the existing NOAA IncidentNews importer remain untouched. Public USCG NRC data and publicly released CSB list are government source records, but their report contents are not automatically verified or safe to re-publish in client/public portals. Each deployment must review license/use/attribution and redact unnecessary personal data.
