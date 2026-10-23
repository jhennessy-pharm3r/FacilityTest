# Lane C — Official USCG NRC, CSB, and PHMSA source evidence

**Updated October 23, 2026. STATUS: PARTIALLY VALIDATED / NOT DEPLOYED.** Dedicated [DRAFT PR #79](https://github.com/jhennessy-pharm3r/FacilityTest/pull/79) remains **UNMERGED**; coordinator [Issue #73](https://github.com/jhennessy-pharm3r/FacilityTest/issues/73). Industrial incident coverage is for **all industries and facility types**, constrained only by each publisher's reporting jurisdiction and release availability. Do not describe regulator incident notifications or enforcement cases as a census of sites, confirmed incidents, insured losses, policy claims, or actual facility risk scores.

## Authoritative real-source validation (not fixtures)

- **Full NRC 2010–2026 plus CSB September 2026 run:** [GitHub Actions 39985606674](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39985606674) **SUCCESS**; [aggregate SHA/count/coordinate/index QA artifact 12515842149](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39985606674/artifacts/12515842149). The run downloaded actual USCG/CSB first-party XLSX files, checked content and publisher-native IDs, wrote deterministic normalized gzip twice per original byte stream, verified matching SHA-256 and source-only SQLite with `PRAGMA quick_check=ok`, source identity/count reconciliation and paged query checks. **24 tests passed**. No raw rows, raw XLSX or SQLite published as public GitHub artifacts.
- **Distinct first-party PHMSA WMS enforcement dataset:** [GitHub Actions 39985148724](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39985148724) **SUCCESS**, 5,089 real enforcement case rows; original and normalized checksums below. These are **NOT national PHMSA incident census records**.
- **CSB June vs September 2026 separate publisher snapshots:** [Actions 39985969191](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39985969191) **SUCCESS**. The June dataset is a comparison snapshot and is **not** added to September source event observations.
- **Standard repository CI** latest applicable importer build [39985613572](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39985613572) **SUCCESS**. The lane's latest full source run is independent of later documentation, PHMSA and quarter-snapshot commits.

## Observed NRC records, geospatial completeness and chronology

USCG publisher: `https://nrc.uscg.mil/FOIAFiles/CYYY.xlsx` (CY10 through CY26). **The year in CYXX is the *reporting/receipt workbook vintage*, NOT necessarily the incident occurrence year.** Older incidents can appear in later reports. CY2026 is an **open, partial annual release as of October 23** and not a finalized annual outcome count. NRC notifications are initially unverified.

| NRC receipt workbook | Accepted native SEQNOS notifications | Usable reported DMS pairs | Missing/invalid DMS | Missing/ambiguous child links | Invalid/missing incident dates | Observed incident date range |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 2010 | 29,817 | 4,454 | 25,363 | 0 | 1 | 1992-10-14 to 2010-12-31 |
| 2011 | 28,480 | 3,671 | 24,809 | 0 | 0 | 1991-08-12 to 2011-12-31 |
| 2012 | 28,596 | 4,036 | 24,560 | 1 | 0 | 1984-01-01 to 2013-03-02 |
| 2013 | 29,175 | 3,718 | 25,457 | 2 | 0 | 1985-07-01 to 2013-12-31 |
| 2014 | 30,139 | 4,001 | 26,138 | 0 | 0 | 1990-01-01 to 2015-04-15 |
| 2015 | 26,915 | 3,654 | 23,261 | 1 | 0 | 1986-11-05 to 2015-12-31 |
| 2016 | 24,193 | 3,050 | 21,143 | 0 | 0 | 1980-01-01 to 2016-12-31 |
| 2017 | 24,434 | 3,438 | 20,996 | 146 | 0 | 1979-12-31 to 2017-12-31 |
| 2018 | 25,592 | 3,519 | 22,073 | 103 | 0 | 2009-04-15 to 2018-12-31 |
| 2019 | 25,759 | 3,649 | 22,110 | 169 | 0 | 1989-07-31 to 2019-12-31 |
| 2020 | 22,503 | 2,864 | 19,639 | 0 | 0 | 1996-09-25 to 2020-12-31 |
| 2021 | 24,540 | 3,523 | 21,017 | 0 | 0 | 1997-01-01 to 2021-12-31 |
| 2022 | 23,510 | 3,269 | 20,241 | 0 | 0 | 2009-12-09 to 2022-12-31 |
| 2023 | 23,143 | 3,527 | 19,616 | 0 | 0 | 2004-12-03 to 2023-12-31 |
| 2024 | 22,966 | 3,865 | 19,101 | 0 | 0 | 1982-06-28 to 2024-12-31 |
| 2025 | 21,533 | 3,999 | 17,534 | 0 | 0 | 2008-07-15 to 2025-12-31 |
| 2026 (partial) | 17,827 | 4,039 | 13,788 | 0 | 2 | 2000-07-18 to 2026-10-18 |
| **NRC 2010–2026** | **429,122** | **62,276** | **366,846** | **422** | **3** | — |

Source schemas actually inspected: native `SEQNOS` across **CALLS** (`DATE_TIME_RECEIVED`, `RESPONSIBLE_COMPANY`), **INCIDENT_COMMONS** (`INCIDENT_DATE_TIME`, `LOCATION_NEAREST_CITY`, `LOCATION_STATE`, `LAT_DEG/LAT_MIN/LAT_SEC/LAT_QUAD`, `LONG_DEG/LONG_MIN/LONG_SEC/LONG_QUAD`) and **INCIDENT_DETAILS** (`NUMBER_FATALITIES`, `NUMBER_INJURED`, `NUMBER_EVACUATED`, `DAMAGE_AMOUNT`, `FIRE_INVOLVED`). Every per-year master SEQNOS is unique, with 0 rejected native master rows. **422 missing or ambiguous child links** are flagged per output row (`calls_link_quality`, `details_link_quality`); the importer **does not select conflicting fatality/injury/damage data from duplicate child rows**, and a missing number is never assumed zero. **3 native date values failed parsing** (2010: 1, 2026: 2); accepted source ID rows retain explicit missing date rather than inventing an occurrence date. Child row counting is separate from unique master report observations. The combined SQL audit found **0 duplicate native SEQNOS values spanning different receipt-year workbooks in these 17 sampled cohorts**, but keys are still namespaced by year and not presumed globally stable by design.

**Source-reported geography:** 62,276 valid publisher-supplied degrees/minutes/seconds coordinate pairs, 366,846 reports without a usable pair; source state labels include US states, territories, foreign/offshore and unknown/placeholder values. Publisher coordinates may refer to notification/incident location, not an affected insured physical property, and their positional uncertainty is not independently characterized. No imputation from city/state, company headquarters, ZIP or geocoding. Per-year bounding latitudes/longitudes, state-value counts, earliest/latest **incident** date and separate receipt year are in the Actions artifact. Source dates have no evidence of a verified insured loss.

### Original raw and reproducible normalized SHA-256 provenance

Original first-party downloads were hashed before staging, normalized source rows hashed after deterministic gzip encoding; identical raw inputs were reprocessed and matching compressed hashes independently checked. Original publisher files and source rows are not saved in public GitHub.

| NRC cohort | Actual original XLSX bytes | Raw SHA-256 | Deterministic normalized gzip SHA-256 |
| --- | ---: | --- | --- |
| 2010 | 17,797,346 | `d8fe9e4f8769e4d883f31e228a3856768cf44475789287872e067918de4d508e` | `5b5b20844a7a0b6439bad75a59092693496bdb0b7df3449e54f58984b9f8c6b6` |
| 2011 | 17,055,340 | `3b276967627a025490636c1d6bc9c085a2c7362fd6362274beb909c38afef333` | `2d7f79eec753207f9dba88ed2845328e7281d022d4e6b54e81680462149c776d` |
| 2012 | 16,588,219 | `4f8531112d46f3fe1401eb6c037a0c2d6f17853d5d975fe3cf599b1a82b10d85` | `aeda7550af9dfeb4e64396a3b35ec12c0abcd9583219bb4e07abecb32e3c8f39` |
| 2013 | 16,492,831 | `190260eeaf29d10f2f0f038faed75333d0d46bb217d004fc79a5c155cd8f02cf` | `76585601d23cead0184337454f93ebced3cdd74d12d580aa31b394e7ae1cae42` |
| 2014 | 16,765,178 | `5255c2dcf68f923b01ba62c4cebf27065101c12a623525071a851cc8628fd9c8` | `4918b0e9745959f315a998228f766b1b08217ca9b1972298912c66aaadcf712b` |
| 2015 | 14,938,247 | `c1e11c410e0ba9f5ca2acf26e50dce42337e518ad904af05c0d4133596a97beb` | `cac6d60fdba761806644eb9fda39f1e9c4346002b9c04af9afcd799108f04f92` |
| 2016 | 13,361,089 | `35fbdba3489692ba8c21f0405a64be808997b5b8ebb4f24128f72a65920e197e` | `cfcc927ee78ccfb59c58c1a9322ade4072cf37ccba538f2deeff7d2bafc6071a` |
| 2017 | 13,075,055 | `5ba9b5769d66c722ac76ef446ce95a9fa60cc4a4ab977c96277acd6083cf8ecd` | `a311ed91b4f30ab0523201bef6ade05420244edb92ca66e7145d0fadc8903e62` |
| 2018 | 13,392,842 | `c171be4808c772f1a4b901f993a0225d84cd0d87ce5a9c800cbbecb273dee9d5` | `303a4489f124c3505182bad6567bb7f3b52d9ed00f44efe39f7936eb5c6d639a` |
| 2019 | 13,545,702 | `dc84a0f1b234629b61276b10191beb2f14aea5a56ed28a4757d491f0a8b34f58` | `2e9903db62ac7145bf303ef0dc40e71ed3da597e97d297f9727591a4e8037944` |
| 2020 | 13,998,110 | `bde99b7eb6f2accf03e003af71396ecb9057dcf167b4065b2ded6da04b402de4` | `222b89a66bd2a8f98adfa8ec91495460cf604e4272a4f19f87705eb2b928cae5` |
| 2021 | 14,979,248 | `248e61b6335aa3e3411ebd5680fb48a6aa98a7aab6e21427a80430fc70d688c1` | `8326cd356cb12c76b142cfc505e586b8dcadec555bfc47560c11965fec9f60dc` |
| 2022 | 14,738,356 | `38736e0010cdb43c0fe4dd5d161b167d3c40f0767f4515d41c2145e5c95d759f` | `274a7f09e497d4414908e49f2b5ecf4b4d5e61acf2697dcfe945c8623e185b90` |
| 2023 | 14,703,606 | `c177d1b7352360c69a7c316ec2b1237e5af9e75b2e63caaa78bd3878e5687a82` | `3b41928a088cad3633d83e87525b3b0d1753c5c3bb15359e72442013a0466ef8` |
| 2024 | 15,151,431 | `3ec11e1c44a1a5c39fda9560018cacfd5a0dd8b9234056b896fb4d4ff97a26e1` | `d8069c13ca2bd8d42a3a4bd6e1e721406bb46827bae7fb1d77d0160ebbd4d179` |
| 2025 | 18,026,065 | `086da221569b5bbccb0f8170c54fd83c11cf8b7894258bfdea2c60a218407bda` | `3af2a32d666cb35a92709a487b933e25b9211d454f7dde8bb70cbcac08575880` |
| 2026 | 10,558,586 | `d4da14c0e8a67b230b2dcdd000b24df1e0e7f6ca30d422a8e49b4f3e80ba1155` | `825e33efd49626ea129c26acedf461c64853d219d587a428f8000b32fa85bfc9` |
| CSB Sep 2026 | 62,290 | `dbea875040e7ddfebfbe295c1731faab5f4c3829784c0c93dbb8d054c10b9dc1` | `63affa5d7fcf06adc6805f39673f1a4891e8f57f0406244b031c9745c102da12` |

## CSB current accident-release observations and revision controls

Official September 1, 2026 CSB accidental-release dataset `https://www.csb.gov/assets/1/6/Copy_of_Accidental_Release_Events_2026-09-01.xlsx`: **675 actual data rows**, **674 accepted/current-vintage indexed**, **1 rejected** (missing incident date); no duplicate `Number` IDs *within this release*. The **Public** sheet has official headers on row 2: `Number`, `Incident Date`, `Company`, `City`, `State`, `Fatality`, `Serious Injury`, `Substantial Property Damage`, `Report`. The `Number` is a release-scoped source row identifier, **not** proven an immutable event ID. Fatality, serious injury, property damage and report columns are preserved as **reported qualitative/categorical source values**, not count of injured, dollars lost, or verified liability. No native CSB coordinates imported (0 observed). Observed September event dates **2020-04-10 to 2026-08-29**.

**June 1, 2026 publisher vintage** at `https://www.csb.gov/assets/1/6/Copy_of_Accidental_Release_Events_2026-06-01.xlsx`: 60,621 bytes SHA `499f4e8afc9b9be51438c2d9314777a31fdbc47dfc669aaebbea4914543507db`; **652 historical release rows / 651 normalized / 1 missing date rejected**, normalized gzip SHA `6c6042e9f0d81e894342a28fa1ee737b797be9c324b4e8590d4f656c2882a8e2`. **DO NOT ADD** June's 651 rows to September's current incident count as independent events. All 652 prior Number values appear in September, but **19 Numbers carry changed combinations of event date, company, city or state** (date 16; company 19; city 19; state 17; 19 changed multiple fields). The quarterly `Number` cannot safely be used for automatic immutable cross-release event identity or physical-site attribution; preserve release and original source row, review differences manually.

## PHMSA — official primary-source enforcement *subset*, NOT report-census ingestion

**First-party case-only export** `https://primis.phmsa.dot.gov/enforcement-documents/PHMSA%20Pipeline%20Enforcement%20Raw%20Data.txt`, source dated October 2, 2026, 1,971,900 bytes, raw SHA `23d8d5c62dd93f848ba3f22d4fc24d0c7f3d90b750aea2ac7223168401725bb7`, normalized gzip SHA `b0f0481db314f387d0e7b464c2ebaceb2227d42cd0e283e9a69c0ee8be8f3deb`. Verified actual cp1252/tab-separated **5,089 published enforcement-case rows**, **5,089 accepted/temporarily source-indexed, 0 rejected**, native `CPF_Number` 5,089 unique, 0 duplicate `CPF_Number + WMS_Activity_Seq`. Opened date min 2002-01-02, max 2026-09-29, 0 invalid parsed dates. **453 rows** have `Report_Type + Report_Number`, **403 distinct typed references**; references may be cited by multiple enforcement cases and **are NOT 403 additional independent/verified accidents**. Extra schema includes `Operator_ID`, `Operator_Name`, `Pipeline_Type`, `Case_Status`, `Case_Type`, `Opened_Date`, `Data_as_of`. Offline fixture tests and real SQLite accepted/count/quick_check PASS. No physical location asserted and no insured site matches; case/status evidence is not confirmed financial policy claim.

**PHMSA incident census unresolved:** Multiple official PHMSA pipeline ZIP downloads (hazardous liquid 2010+, gas distribution, gas transmission/gathering, flagged files) responded **HTTP 403 Forbidden** from GitHub Actions Ubuntu runner despite publicly listed access. PHMSA separate DOT form 5800.1 hazmat report portal redirected to an inaccessible login via insecure HTTP; DOT Socrata metadata endpoint HTTP 200 returned **catalog information, not incident rows**; alternative official BTS national trend XLSX also 403 and would be *aggregate yearly context*, not event records. No bypass of access control, third-party file substitution or PHMSA census counts. **PHMSA pipeline incident/hazmat report rows, deduplication, report-specific geography/IDs, acceptance and index status = NOT TESTED**, not zero nationwide. Official publisher incident access with permissioned bulk ZIP or agency assistance is required; PHMSA Office of Pipeline Safety data contact on federal catalog: `phmsaphpdataandstatistics@dot.gov`; hazmat portal catalog contact `hmrequests@dot.gov`. Access method and usage must be verified before source publication.

## Actual source data counts at separate lifecycle stages

| Source cohort | Actual raw data rows downloaded | Accepted normalized source rows | Rejected master rows | Indexed on disposable CI SQLite | Persistently production indexed | Deployed app source observations | Verified insured physical sites |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NRC 2010–2026 (2026 is provisional) | 429,122 | 429,122 | 0 | 429,122 | **0** | **0** | **0** |
| CSB Sep-2026 current release | 675 | 674 | 1 | 674 | **0** | **0** | **0** |
| **Current NRC + CSB observations total** | **429,797** | **429,796** | **1** | **429,796** | **0** | **0** | **0** |
| PHMSA WMS *enforcement cases* (separate grain) | **5,089** | **5,089** | **0** | **5,089** *separate DB* | **0** | **0** | **0** |
| CSB June 2026 historical snapshot (NOT additional accidents) | 652 | 651 | 1 | 0 in current source DB | 0 | 0 | 0 |
| PHMSA operator/hazmat incident *census* | **NOT DOWNLOADED** | **NOT TESTED** | **NOT TESTED** | **NOT TESTED** | **0 AVAILABLE** | **0** | **0** |

One consolidated temporary NRC+CSB SQL index has **429,796 rows**, 18 independently versioned source namespaces, `PRAGMA quick_check=ok`, count-source identity consistency, paginated SQL queries and date/geo/receipt-year coverage audit PASS. Source-only reviewer candidates via strict reported date+company+city+state: **135 candidate pairs referencing 83 CSB rows**. **0** independently confirmed same event, facility footprint, official incident finding, insured property, or claims/loss. PHMSA enforcement WMS cases indexed in their own **different grain** temporary SQLite; never sum as independent accident/physical property incidence.

## Reproduce and hand off to Lane E

From checked-out PR #79 on an approved internet-enabled runner:
```bash
pip install -r requirements.txt -r requirements-dev.txt openpyxl requests
python -m pytest -q tests/test_industrial_incidents.py tests/test_nrc_enriched.py tests/test_csb_release.py tests/test_lane_c_index.py tests/test_lane_c_candidates.py tests/test_lane_c_private_handoff.py
python scripts/run_lane_c_verified.py --output /tmp/lane-c-source-qa
python -m pytest -q tests/test_phmsa_enforcement.py tests/test_lane_c_vintage.py
python scripts/probe_lane_c_phmsa_enforcement.py --output /tmp/lane-c-enforcement-qa
python scripts/probe_lane_c_current_vintages.py --output /tmp/lane-c-current-vintage-qa
```
To retain original raw files, normalized gzip, manifests and SQLite in a restricted authorized host directory **OUTSIDE public GitHub/Pages/repo**, coordinator can opt in to:
```bash
python scripts/run_lane_c_verified.py --output /secure/qa/lane-c \
  --private-bundle-dir /secure/private/lane-c-source-release
```
Pre-provision parent directory and enforce encryption, role auth, retention, audit and tenancy. This does **not** create a persistent authenticated production server. No public GitHub Actions artifact may include row-level NRC/CSB/PHMSA original files or the generated SQLite; the job publishes only aggregate JSON manifests. Candidate matches remain `review_candidate_not_corrob` and are not pushed into Lane E's canonical site registry.

### Remaining blockers and acceptance steps

1. **PHMSA:** permitted official incident operator ZIP and DOT 5800.1 transport report export still inaccessible; obtain ordinary authorized agency distribution and inspect native report grain, IDs, schema, coverage, checksums, duplicate commodity rows, reporter/incident geolocation and severity. Do not assert that case enforcement coverage substitutes for pipeline accident coverage.
2. **NRC:** 2010–2026 annual cohorts content/index QA pass in disposable CI; 2026 provisional, earlier than CY2010 **not inspected**. 422 child ambiguities and 3 missing dates must remain visible. Source country/offshore/coordinate uncertainty, independent event outcome corroboration and future refresh freshness require production monitoring.
3. **CSB:** June–September 19 altered Number/event attribute combinations must remain separately versioned; investigate with official corrections/changes before downstream longitudinal dedup/attribution.
4. **Coordinator Lane E owns persistent private index, authentication, scheduled refresh, common provenance/status, tenant-specific physical-site corroboration and review-only crosswalk, UI Source Health + live backend/browser deployment, release approval and final PR merge.** Lane C cannot claim complete until these issue #73 deployment/QA gates pass. No updates to another lane or shared files, no self-merge.

**Status: SOURCE DATA INGESTION AND QA FOR NRC/CSB AND PHMSA ENFORCEMENT VERIFIED IN EPHEMERAL CI; PRIMARY PHMSA INCIDENT REPORTS BLOCKED; PRODUCTION DATA SERVING/DEPLOYMENT NOT DONE.**
