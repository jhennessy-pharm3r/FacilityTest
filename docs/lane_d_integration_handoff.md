# Lane D — production integration handoff

Updated October 23, 2026. [PR #77](https://github.com/jhennessy-pharm3r/FacilityTest/pull/77), [coordination Issue #73](https://github.com/jhennessy-pharm3r/FacilityTest/issues/73).

**State: REAL SOURCE DATA VALIDATED, TEMPORARY INDEXES BUILT, LIVE APP DEPLOYMENT NOT VERIFIED.** All industries and facility types are in scope. Original utility/incident source rows must not be equated with insured facilities, insured outages or paid claims. Lane E owns shared registry, Source Health, live API, protected storage, browser testing and merge.

## 1. Source ledger — counts are NOT additive unique incidents

| Real source / vintage | Downloaded publisher records | Accepted | Rejected | Local SQLite rows | Durable backend / live app |
| --- | ---: | ---: | ---: | ---: | ---: |
| [EIA-861 final 2025](https://www.eia.gov/electricity/data/eia861/zip/f8612025.zip), utility reliability/state totals/county territory | 12,926 | 12,923 | 3 | 12,923 | 0 / 0 |
| [EIA EPM Table B.1](https://www.eia.gov/electricity/monthly/epm_table_grapher.php?t=epmt_b_1), PARTIAL 2024 | 72 | 72 | 0 | 72 | 0 / 0 |
| [EIA EPM Table B.2](https://www.eia.gov/electricity/monthly/epm_table_grapher.php?t=epmt_b_2), annual 2023 | 158 | 158 | 0 | 158 | 0 / 0 |
| [DOE CESER OE-417 2023 annual discovery dataset](https://openenergyhub.ornl.gov/explore/dataset/oe-417-annual-summaries/), ORNL original public-domain publisher export | 341 | 341 | 0 | 341 | 0 / 0 |
| [DOE/PNNL Event-correlated Outages 2014–2023](https://data.openei.org/files/6458/Outage_Dataset_R1.zip), 50 original CSVs | 2,124,183 | 2,124,183 | 0 | 2,124,183 | 0 / 0 |
| [ORNL ODIN original /odi](https://odin.ornl.gov/odi), current county-only snapshot at 16:15 UTC | 558 | 558 | 0 | 558 | 0 / 0 |
| [OpenEnergyHub ODIN mirror export](https://openenergyhub.ornl.gov/api/explore/v2.1/catalog/datasets/odin-real-time-outages-county/exports/json), a DIFFERENT 15:42 UTC snapshot of overlapping feed | 424 | 423 | 1 | 423 | 0 / 0 |
| [ORNL ODIN feed status](https://odin.ornl.gov/odi/status), 16:18 UTC | 157 | 157 | 0 | 157 | 0 / 0 |
| Baxter original investor announcements about one North Cove event | 3 publications | 3 | 0 | 3 | 0 / 0 |
| Crane issuer-hosted annual/interim original reports | 2 reports | 7 period-typed financial observations | 0 | 7 | 0 / 0 |
| Pebblebrook original investor releases | 2 reports | 5 period-typed financial observations | 0 | 5 | 0 / 0 |
| SEC EDGAR native filing retrieval | blocked HTTP 403 | 0 | N/A | 0 | 0 / 0 |

The 2,124,183 PNNL **source observations** contain 1,385,389 merged county episodes, 526,165 event-correlated county rows, 91,402 eight-hour lag sensitivity rows, 114,610 twenty-four-hour lag sensitivity rows, and 6,617 state/month aggregate rows. There are **277,360 exact duplicate source-row contents within individual CSV tables**, retained but explicitly flagged, yielding 1,846,823 within-table content-distinct rows. Neither count is a national unique power-outage census. Lag variants and aggregates are NOT additive episodes.

## 2. Original source provenance, identifiers and coverage

| Source | Original downloaded file SHA-256 | Identity / spatial / temporal notes |
| --- | --- | --- |
| EIA 2025 ZIP | f59f6c732bf685fe0a1591b32227f5ce572dc0dfd26bb5caaeed128ac4e3a396 | 4,756,816 bytes. 913 reliability utility IDs; 2,909 county territory utility IDs. 56 state/territory codes and 3,229 state/county pairs. Preserve original utility number, source workbook/sheet/row, SAIDI/SAIFI/CAIDI IEEE/other and MED columns |
| EIA EPM B.1 HTML | 33157ccff40391e3ca0ce07f12fe515b0c577f7a6e4f27f334bf327a62da1112 | 105,713 bytes; only partial 2024. Original tables lack native event IDs, so source-row digests are labeled derived |
| EIA EPM B.2 HTML | 65aadf5062687f1179302983d4cd53489d5d948bfb9f83d189e2d95ed571fecb | 180,264 bytes; original annual 2023 |
| PNNL R1 ZIP | 44557bae7a5c8e02c611a14f75fe9e123d81d286f700b9fd88ac538edd910fe7 | 31,260,449 bytes; 50 accepted CSV schemas. 2,985 five-digit FIPS and 54 source state/territory *name strings* (including aliases). Published event IDs only in correlated family and repeat by county; original member/line/digest preserved |
| ODIN direct JSON | 19ca8e195ac765159168b0a32d459e3bf171fc058de84b3db148db1734025a9a | 498,015 bytes. 248 county FIPS, 89 source EIA utility IDs, 6 exact duplicates flagged, 170 missing native MRID, 157 unknown reported starts. Snapshot changes continuously |
| ODIN OpenEnergyHub mirror JSON | 2e23afd647119793b15499c3210508142faca8de5f7aae014d7af502abf4366f | 1,782,901 bytes; 241 county FIPS, 37 state names; 160 unknown starts; one nonempty malformed timestamp rejected. DO NOT sum with direct feed |
| ODIN participant inventory | 2ee5f692d225db5a0d8b9ec35b93100d9609817b0d231cc38ee2416ee462d096 | 37,460 bytes, native dataId/eiaId and receivedDate retained. 10 feed records report hasError, not a verified site outage |
| Issuer-specific reports | Per-document source PDF or HTML SHA in individual original-source manifests | Issuer CIK/URL/date, named site, original event key, reporting period/financial kind. Neither cash received, accounting income nor preliminary sales guidance alone is a carrier-confirmed claim |

Independent real-source concordance linked 77 of 86 ORNL utility IDs to EIA 2025 source IDs and left 9 unmatched, with 12 source-name differences for review. [Source-native ID CI](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39986392193). Exact ID matches confirm utility reporter identity, **not physical site servicing**.

## 3. Install verified source-only indexes into a PRIVATE protected volume

The source and index must be transferred through authenticated, controlled storage to a persistent, backed-up backend. Original archives, normalized output, rejected rows, original HTML/PDFs and all SHA manifests must be separately retained privately. GitHub Pages is static and short-retention Actions artifacts are **not** a production datastore.

From a checked-out PR branch with Python 3.12:

    gh run download 39999761323 --repo jhennessy-pharm3r/FacilityTest -n lane-d-eia861-2025-readonly-staging-index -D /secure/transfers/eia2025
    python -m facilityrisk.lane_d.install_source_index install --bundle /secure/transfers/eia2025 --dest /srv/facilityrisk/private/sources/lane-d --dataset eia861_2025 --source-sha256 f59f6c732bf685fe0a1591b32227f5ce572dc0dfd26bb5caaeed128ac4e3a396 --role private-backend-candidate
    python -m facilityrisk.lane_d.install_source_index verify --dest /srv/facilityrisk/private/sources/lane-d --dataset eia861_2025
    python -m facilityrisk.lane_d.install_source_index query --dest /srv/facilityrisk/private/sources/lane-d --dataset eia861_2025 --state WA --county Pierce --limit 25

PNNL uses the same CLI, but a **successful latest** full-source Actions run and its large attached artifact (1.59 GB uncompressed SQLite):

    gh run download 39999800430 --repo jhennessy-pharm3r/FacilityTest -n lane-d-pnnl-2014-2023-readonly-staging-index -D /secure/transfers/pnnl
    python -m facilityrisk.lane_d.install_source_index install --bundle /secure/transfers/pnnl --dest /srv/facilityrisk/private/sources/lane-d --dataset pnnl_2014_2023 --source-sha256 44557bae7a5c8e02c611a14f75fe9e123d81d286f700b9fd88ac538edd910fe7 --role private-backend-candidate
    python -m facilityrisk.lane_d.install_source_index verify --dest /srv/facilityrisk/private/sources/lane-d --dataset pnnl_2014_2023
    python -m facilityrisk.lane_d.install_source_index query --dest /srv/facilityrisk/private/sources/lane-d --dataset pnnl_2014_2023 --fips 01001 --year 2023 --limit 10

**Versioning/rollback:** installer independently checks caller-pinned *original source ZIP* SHA-256 against publisher manifest AND coordinator receipt, copied SQLite SHA-256/size, accepted/rejected totals/source categories, full SQLite integrity and required source ID/duplicate schema. It creates a versioned, read-only SQLite directory under DEST/dataset/versions, then atomically replaces DEST/dataset/current.json only after verified copy. A SHA mismatch, malformed source, incomplete version or concurrent lock blocks promotion and leaves previous pointer unchanged. Re-running the same package is idempotent. SQL is opened in immutable read-only mode. **The CLI deliberately does not assert live app deployment.**

### Read-only SQL and query contracts

| Database / source table | Primary source identifiers | Query function |
| --- | --- | --- |
| EIA: lane_d_eia861_staging.sqlite / source_observations | ingestion_row_key PK, source_kind, utility_id, state, county, source_member/sheet/row, row_sha256, original_row_json | facilityrisk.lane_d.query_eia_service_territory.service_territory_candidates(db, state, county), exact-source county text; multiple candidates |
| PNNL: pnnl_county_outage_staging.sqlite / source_observations | source_row_key PK, source_kind, dataset_year, county_fips, source_member/line/sha, original raw JSON, is_exact_duplicate_source_row, duplicate_of_source_line | facilityrisk.lane_d.query_staging.get_county_context(fips, pnnl_db=..., year=..., limit=...), **county_episode only**, not lag or aggregate rows |
| ORNL direct: odin_direct_county_staging.sqlite / source_observations (still source-only staging; publishing rights pending) | source_row_key, native MRID, county FIPS, EIA-authority utility ID, snapshot time, original row, duplicate flags | get_county_context(fips, odin_direct_db=..., limit=...), source-only; never combine mirror and direct snapshot |
| Crane/Pebblebrook separate financial source indexes / source_financial_observations | evidence_key, issuer CIK, native report, source document SHA, accounting period, monetary type, event key | facilityrisk.lane_d.query_issuer_bi_context.get_issuer_bi_context(crane_db=..., pebblebrook_db=..., limit=...), no annual/quarter double count |

**EIA-861, PNNL and public-domain DOE OE-417 annual** have complete independent GitHub artifact-transfer plus atomic installation/query acceptance runs; **ORNL direct public /odi** has isolated source-pinned atomic installation/query acceptance (without publishing a raw ODIN artifact pending rights review). Financial, legacy EPM, participant and mirror indexes remain independent staging/query contexts. None is approved for live production serving without coordinator storage/security and source-use gates.

### DOE CESER OE-417 public-domain 2023 annual source — artifact-to-index installation

The publisher's original 2023 OE-417 discovery catalog contains **341 source rows, all accepted, zero rejected, zero exact duplicate source rows**; **309 have reported 2023 event start dates and 32 have unknown dates**. The original publisher records have **no native event ID** and only free-text affected area, without verified insured-site coordinates. These may **overlap the EIA EPM DOE-417-derived tables** above and must NEVER be added as independent emergency incidents or insured outages. The OpenEnergyHub original dataset metadata declares **Public Domain**. The approved distribution source SHA-256 is **5329d272544e9164692f08b34a5079d3f89a2095f1a77a8fa8dfca8923b06d18**, and the locally indexed 409,600-byte SQLite SHA-256 is **f7d13108d3ed9f0ee7bebfc7d152c20d2209b704ac395b68721257456f753957**.

[Actual original data → schema and metadata license audit → normalized index → deterministic replay → artifact upload/download → atomic read-only installation/query, run #40001818924](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/40001818924) **PASS**. [Source-only SQLite handoff artifact 12522093009](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/40001818924/artifacts/12522093009), [install acceptance artifact](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/40001818924/artifacts/12523105614).

    gh run download 40001818924 --repo jhennessy-pharm3r/FacilityTest -n lane-d-oe417-2023-public-domain-readonly-staging-index -D /secure/transfers/oe417
    python -m facilityrisk.lane_d.install_source_index install --bundle /secure/transfers/oe417 --dest /srv/facilityrisk/private/sources/lane-d --dataset oe417_annual_public --source-sha256 5329d272544e9164692f08b34a5079d3f89a2095f1a77a8fa8dfca8923b06d18 --role private-backend-candidate
    python -m facilityrisk.lane_d.install_source_index verify --dest /srv/facilityrisk/private/sources/lane-d --dataset oe417_annual_public
    python -m facilityrisk.lane_d.install_source_index query --dest /srv/facilityrisk/private/sources/lane-d --dataset oe417_annual_public --year 2023 --limit 10

The installer rejects changes to the original publisher-source SHA, license declaration, count/duplicate flags or SQLite SHA. An undated original event stays undated and queryable by the original annual-context adapter. **No insured-site outage, commercial claim, utility meter, or deployed app source is validated.**

### Native ORNL active county outage private-install test (rights gate still applies)

The current ODIN source data change between runs. The original ORNL public GET /odi snapshot captured during [Actions run #40001295225](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/40001295225) has **481 accepted actual source observations** with official publisher raw JSON SHA-256 **260682b6872aff22319a54773a2a5f14bcfea022227caf796f69a04e58246fd0**. The job independently verifies original first-party HTTP, original JSON row hashes, missing/native MRID and county FIPS, accepted/rejected totals, SQLite, and a bounded source-only county query. It now also **creates a source-pinned handoff receipt, performs atomic read-only installation into an isolated CI private path, verifies the installed index and performs an installed FIPS query**, without uploading the raw ORNL dataset as a public artifact. [Safe installation acceptance pointer artifact](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/40001295225/artifacts/12522585933).

The installer additionally supports the dataset option **odin_direct_public**. The same installation method applies to a publisher-approved private dataset transfer, but commercial use/redistribution and production serving are explicitly **NOT licensed or accepted by this CI test**. First-party ODIN direct and the OpenEnergyHub mirror are **overlapping alternate distributions**; only one should be selected for current outage context, and 481 must NOT be added to any previous 558/423-row snapshots. **Insured facility outages remain 0 verified.**

### Proposed coordinator-only API (not implemented or deployed)

- GET /api/source-context/utility-candidates?state=WA&county=Pierce : multiple EIA source reporters and reliability context, reviewed-site-link status **false**.
- GET /api/source-context/historical-outages?county_fips=01001&year=2023 : bounded county outage episodes with original PNNL row IDs and dates, not individual property downtime.
- GET /api/source-context/current-outages?county_fips=01001 : one approved source/snapshot only, as-of/freshness/staleness and unknown timestamps.
- GET /api/source-context/issuer-bi?issuer=Crane%20Company : issuer accounting-period classified results, carrier confirmation **false**.

Authentication, tenant authorization, request logging, site locality corroboration, provider/meter crosswalk review, caching/pagination, response sanitization and Source Health states remain exclusively Lane E implementation. Responses must preserve original publisher URL/SHA/source kind, vintage and unknown/missing qualifiers. No actual site-meter/outage claim follows from county or utility-name proximity.

## 4. Production refresh, error and data-use policy

- **EIA-861** annual final after publication: verify original ZIP SHA against last approved vintage, check source sheets and positional column headers, rerun full original-row audit and reproducibility; new SHA requires reviewed new version. Do not overwrite current on failure.
- **PNNL** is a published 2014–2023 historical study, not real-time. Check for approved future archive revisions, require pinned full source archive SHA and 50 schema/reconciliation checks. Keep source families separate and exact repeated content flagged, never sum lag joins as additional losses.
- **ODIN** current county snapshots are time-varying. Suggested operational evaluation interval is 30 minutes (NOT an official claimed source cadence); preserve original snapshot UTC and source receivedDate; on HTTP failures, stale feeds, unknown dates, schema drift or license restriction, keep last approved snapshot and label **STALE/BLOCKED** rather than claim current or zero outage. Do not query authenticated finer-grain endpoints without ORNL approval. **Commercial redistribution rights for direct ODIN and OpenEnergyHub mirror need explicit review.**
- **EIA EPM partial 2024 vs full 2023** must not be compared as equal reporting windows; event area cannot prove a site outage; original tables do not publish a stable event number.
- **Issuer BI**: keep forecast sales vs property repair expense vs cumulative recoveries vs receivable balance vs recognized insurance income vs issuer-reported BI proceeds **distinct**. Q4 is a subset of FY; don't add it again. Crane reports USD 4.0m of received lost-profit proceeds; this remains **issuer-reported, not carrier independently confirmed**. Pebblebrook FY2024 Ian USD 23.8m and FY2025 Helene/Milton USD 12.7m are income recognized, not separately confirmed payments. SEC EDGAR archive returned HTTP 403; never bypass.
- **Failure modes**: unexpected source hash/size/columns, invalid native IDs, unreconciled source rows, duplicate lineage drift, missing full original, tenant/data permission mismatch and unsuccessful index copy all block version promotion. Record precise failure, preserve last known-good current.json, retain original files/hashes in restricted backup, and show accurate Source Health.

PNNL publisher OEDI page https://data.openei.org/submissions/6458 links to **CC BY 4.0**; credit Buxin She, Veronica Adetola, Ji Young Yun (2024), link license, mark derivative edits. ORNL uses a public county endpoint but needs a separate source-specific redistribution review before commercial client serving.

## 5. Remaining coordinator gates — do not declare DEPLOYED early

- [x] PNNL complete original-source → upload/download artifact → SHA-verified immutable SQLite installation → FIPS query passed ([run #39999800430](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39999800430)).
- Deploy these transferred private indexes plus verified original-source archives to a **durable backed-up authenticated backend**, not an Actions runner or static GitHub Pages.
- Review ORNL licensing; keep live current feeds separate and freshness-aware.
- Independently corroborate insured location, meter/circuit/service provider and outages before physical-site scoring. Current verified site-to-meter links **zero**.
- Seek independent carrier/policy evidence before marking issuer receipts as verified insured paid claims. Independently carrier-confirmed payments **zero**.
- Coordinator merges after review, integrates proposed API/Source Health/UI and confirms live browser/tenant smoke with actual backend queries. **Worker does not merge or edit shared app.**

Detailed source sheets, member SHA, original rejections and CI links: [Lane D source ledger](lane_d_utility_reliability.md).

**Release state: REAL OFFICIAL SOURCE + EIA, PNNL AND DOE OE-417 PUBLIC-DOMAIN ARTIFACT TRANSFER/READ-ONLY INSTALL/QUERY VALIDATED, PLUS FIRST-PARTY ORNL PRIVATE INSTALL SMOKE VALIDATED. Production backend/app deployed source rows = 0.**
