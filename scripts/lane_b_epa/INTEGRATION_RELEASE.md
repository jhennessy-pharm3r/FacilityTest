# Lane B — EPA environmental compliance, production-integration handoff

**Branch:** `ingest/epa-echo-tri-rcra-rmp-lane-b-20261023`  
**Coordinator:** Issue [#73](https://github.com/jhennessy-pharm3r/FacilityTest/issues/73), draft PR [#76](https://github.com/jhennessy-pharm3r/FacilityTest/pull/76); durable private host prerequisite [#39](https://github.com/jhennessy-pharm3r/FacilityTest/issues/39).  
**Last audited:** October 23, 2026. **Lane B integration status: SOURCE-VALIDATED AND REAL PRIVATE INSTALLATION REHEARSED, NOT PRODUCTION DEPLOYED.** All facility types/industries eligible for source catalog review; no manufacturing-only filter.

## A. Independently reconciled official data counts

| Data source and grain | Downloaded source rows | Accepted/normalized | Rejected, retained source exceptions | Ephemeral SQLite indexed | Production deployed |
| --- | ---: | ---: | ---: | ---: | ---: |
| **EPA ECHO national exporter** — source-registry summary rows | **3,229,311** | **3,208,008** | **21,303** blank `REGISTRY_ID` (quarantined with raw attributes and SHA); malformed CSV 0 | **3,208,008** | **0** |
| **EPA RCRAInfo** — six regulatory source tables | **7,022,589** | **7,022,589** | **0** | **7,022,589** | **0** |
| **EPA TRI Basic U.S., all 38 reporting years 1987–2024** — year × chemical form | **3,218,093** | **3,218,093** | **0** | **3,218,093** in 38 separately validated year indexes | **0** |
| **Public EPA FRS RMP program-interest registry** — layer/object records | **21,853** | **21,853** | **0** | **21,853** | **0** |
| **Restricted RMP plans/off-site consequence** | **Not accessed** | N/A | N/A | 0 | 0 |

**These counts have fundamentally different grains. Do not sum them as physical properties, incidents, emissions outcomes, insurance claims or risk exposure.** Temporary, checksum-verified private *installation* was exercised and cleaned up in CI. Production's independently verified, authenticated deploy count remains **zero**.

### Source vintage, identifiers, geography and original SHA-256

| Publisher | Official URL / version | Original SHA-256 | Native keys and measured geographic coverage |
| --- | --- | --- | --- |
| ECHO | `https://echo.epa.gov/files/echodownloads/echo_exporter.zip`; retrieved Oct 23, publisher ZIP Last-Modified Oct 18, 2026 | `116f6e53117b52f7891c6d2466d662f4ee5e29946b065fdb7b97eaf095615899` | `REGISTRY_ID`; **3,146,109** accepted georeferenced rows. Publisher coordinate fields `FAC_LAT`/`FAC_LONG`, not confirmed parcels. Complete source lat -14.356083–74.256738, lon -180–179.28679; states, territories, foreign/special values |
| RCRAInfo | `https://echo.epa.gov/files/echodownloads/rcra_downloads.zip`; retrieved Oct 23, publisher ZIP Last-Modified Oct 18, 2026 | `babf48b1e2388b7f27cfc186cb1e9eb0ecfa26f53476fc81908712e41dfe09f3` | `ID_NUMBER` **plus `ACTIVITY_LOCATION`** for same-regulator joins; **1,630,839** distinct native facility-table rows, **1,522,387** with reported facility coordinate pairs; NAD83 lat -14.33666–80, lon -179.28679–145.809342 |
| TRI Basic U.S. | `https://data.epa.gov/efservice/downloads/tri/mv_tri_basic_download/{YEAR}_US/csv`, YEAR=1987..2024; publisher-year reporting and later source revisions distinct | **38 original file hashes**, individually in [1987–2019 ledger](validation/tri_1987_2019.md) and [2020–2024 ledger](validation/tri_2020_2024.md) | `2. TRIFD` reporting site + `1. YEAR` + `36. DOC_CTRL_NUM` / `39. TRI_CHEMICAL_COMPOUND_ID`. 2024 reports 77,295 rows from 21,482 TRIFDs, all 77,295 with reported coordinates; U.S. states/territories, not an insured parcel census |
| Public FRS RMP | `https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/FRS_INTERESTS_RMP/FeatureServer/0/query` retrieved Oct 23 | raw JSONL SHA `a2ae6195b1e20096b8b21faed57e4ed840fcc753f6775624aadb292e0d3a4272` (earlier canonical public snapshot; see matching installed manifest for current replay) | `OBJECTID` + `PGM_SYS_ID` (21,853 distinct program keys) + `REGISTRY_ID` (**21,567** distinct FRS keys); all **21,853** source-reported coordinate pairs. Public program-interest list, **not** RMP plans/OCA |

RCRA native member tables and row counts: `RCRA_FACILITIES.csv` **1,630,839**; `RCRA_ENFORCEMENTS.csv` **385,084**; `RCRA_EVALUATIONS.csv` **1,170,763**; `RCRA_NAICS.csv` **435,908**; `RCRA_VIOLATIONS.csv` **712,377**; `RCRA_VIOSNC_HISTORY.csv` **2,687,618**. Exactly **11,212** candidate related-table rows lacked a two-key RCRA handler match in the full original data audit and remain **UNLINKED**. Never join by company name, address, geocoordinate, or ID_NUMBER alone.

TRI 2025 Basic's attempted national endpoint returned **HTTP 404** [official probe](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39985303945): treat as **publisher release unavailable**, not an empty reporting-year cohort. Restricted RMP offsite-consequence data is excluded from unrestricted ingestion by EPA source-access requirements.

## B. Exactly what is indexed and how to query it

**Source-only schema v2**, stable across native ECHO, RCRA and TRI partitions:

```sql
CREATE TABLE observation(
  source TEXT, source_id TEXT, member TEXT, row_number INTEGER,
  payload TEXT, row_sha256 TEXT, latitude REAL, longitude REAL,
  activity_location TEXT,
  PRIMARY KEY(source,member,row_number)
);
CREATE INDEX idx_sourceid ON observation(source,source_id,activity_location);
CREATE TABLE rejected(
  member TEXT,row_number INTEGER,reason TEXT,row_sha256 TEXT,payload_json TEXT
);
```

Original source fields remain normalized by **column name only** in `payload`, without fabricating physical-site IDs. `rejected` preserves unkeyed ECHO attributes and their SHA-256. `RCRA_FACILITIES.csv` coordinate context is attached to an RCRA enforcement/evaluation only if both regulator keys match; there is no approved insured-property attribution. TRI is **one source index per reporting year**; repeated TRIFDs across chemicals/years are not dropped. Exact reported grams/pounds are retained; kg per *one chemical filing* is a separately labeled conversion, not combined release, exposure or loss.

Public RMP schema: `rmp_frs_public(object_id INTEGER PRIMARY KEY, registry_id TEXT, program_id TEXT, raw_sha256 TEXT, latitude REAL, longitude REAL, attributes_json TEXT)` with dedicated registry/program indexes. Original public records retained as canonical JSONL. `PRAGMA integrity_check`, source-archive, database and/or JSONL SHA-256, native IDs, duplicate and null coverage are independently checked.

Private source-only read commands, after versioned installation:

```bash
python -m scripts.lane_b_epa.read_index --source echo --index /app/source-index/epa-echo-20261023/echo.sqlite --manifest /app/source-index/epa-echo-20261023/echo.manifest.json --source-id 110000000000
python -m scripts.lane_b_epa.read_index --source rcra --index /app/source-index/epa-rcra-20261023/rcra.sqlite --manifest /app/source-index/epa-rcra-20261023/rcra.manifest.json --source-id TXD123456789 --activity-location TX
python -m scripts.lane_b_epa.tri_history --index-root /app/source-index/epa-tri --trifd 000000000000000 --years 2023,2024
python -m scripts.lane_b_epa.rmp_lookup --directory /app/source-index/epa-rmp-public-20261023 --program-id 1234567
```

**Illustrative arguments only:** the ID strings above are not independently verified source examples. Validate query response `source_provenance` and `physical_site_linkage: NOT_REVIEWED`; a zero match is **unassessed, never clean**.

## C. Install exactly matching publisher/archive/index artifacts on private host

Retrieve original source assets, manifests and staged chunk artifacts from the source-verified producer [Actions run 39982893655](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39982893655), **before Actions artifact expiry**. Do not mix producer vintages across files. Run the following commands in a restricted, encrypted storage host with sufficient free disk space and an independently authenticated server. Prepare `/app/source-index` manually; never include source files in Git or public Pages.

For ECHO (3.2 million accepted + 21,303 quarantined) and RCRA (seven million source-table rows), the reproducible built-in installer reconstructs and verifies all cryptographic chunks and the original official publisher ZIP:

```bash
python -m scripts.lane_b_epa.install_snapshot --source echo --official-zip /private/epa_raw/echo_exporter.zip --manifest /private/epa_staging/echo.manifest.json --parts-dir /private/epa_staging/echo_parts --chunks-manifest /private/epa_staging/echo_chunk-manifest.json --destination /app/source-index/epa-echo-20261023
python -m scripts.lane_b_epa.install_snapshot --source rcra --official-zip /private/epa_raw/rcra_downloads.zip --manifest /private/epa_staging/rcra.manifest.json --parts-dir /private/epa_staging/rcra_parts --chunks-manifest /private/epa_staging/rcra_chunk-manifest.json --destination /app/source-index/epa-rcra-20261023
```

TRI annual year-partition paths must match `/app/source-index/epa-tri/tri_YEAR/`. **All 38** original CSV/SQLite-gzip/manifest bundles must be fetched from [2020–24 source producer 39980692415](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39980692415) and [1987–2019 source producer 39985627343](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39985627343). Example per partition:

```bash
python -m scripts.lane_b_epa.install_auxiliary tri --year 2024 --official-csv /private/epa_raw/tri_2024_US.csv --index-gz /private/epa_staging/tri_2024/tri.sqlite.gz --manifest /private/epa_staging/tri_2024/tri.manifest.json --destination /app/source-index/epa-tri/tri_2024
python -m scripts.lane_b_epa.install_auxiliary rmp-public --original-jsonl /private/epa_staging/rmp_frs_public.raw.jsonl --index /private/epa_staging/rmp_frs_public.sqlite --manifest /private/epa_staging/rmp_frs_public.manifest.json --destination /app/source-index/epa-rmp-public-20261023
```

Public RMP original JSONL/index/manifests are in [real public source run 39981171808](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39981171808). Every installer writes a versioned **read-only, source-only** directory atomically, refuses to overwrite previous snapshots, validates native keys and returns an `install-receipt.json` with **0 asserted production deployed records**. ECHO requires substantial temporary disk: ~13.72 GB uncompressed SQLite + chunk downloads and original ZIP. Deploy only with a sufficient disk/memory budget and backups.

## D. Coordinator's private API integration (this PR does NOT edit app.py)

**One optional, isolated integration module:** `scripts.lane_b_epa.integration_api`. It never starts a public server. It produces fail-closed mounted-source status and bounded, exact-native-ID query results. To expose **only after authentication and tenant authorization review**, Lane E adds the following to existing `facilityrisk/app.py`, which already calls `add_security(app)`:

```python
from scripts.lane_b_epa.integration_api import build_router
app.include_router(build_router())
```

Set private service environment *only after immutable source mounts are installed*:

```dotenv
FACILITY_RISK_LANE_B_ECHO_DIRECTORY=/app/source-index/epa-echo-20261023
FACILITY_RISK_LANE_B_RCRA_DIRECTORY=/app/source-index/epa-rcra-20261023
FACILITY_RISK_LANE_B_TRI_ROOT=/app/source-index/epa-tri
FACILITY_RISK_LANE_B_TRI_YEARS=1987-2024
FACILITY_RISK_LANE_B_RMP_DIRECTORY=/app/source-index/epa-rmp-public-20261023
FACILITY_RISK_LANE_B_ROUTES_ENABLED=1
```

**Explicit private GET contracts (all require the existing authentication middleware):**

| Endpoint | Source lookup and response |
| --- | --- |
| `GET /api/epa/lane-b/status` | Validates separately mounted ECHO, RCRA, TRI year cohort and public RMP; reports `not_configured`, `unavailable` or `mounted_source_only`; **never** equates mounted with production deployment |
| `GET /api/epa/lane-b/echo/identity?native_id={REGISTRY_ID}` | Exact ECHO registry record and reported compliance summary, checksum, reported coordinates |
| `GET /api/epa/lane-b/rcra/identity?native_id={ID_NUMBER}&activity_location={CODE}` | Exact RCRA two-key handler/event records, original source table, dates and same-regulator (unverified physical-site) context |
| `GET /api/epa/lane-b/tri/identity?native_id={TRIFD}&year=2024` | **One validated reporting-year** chemical forms; explicit grams/pounds unit, no false cross-year property merge |
| `GET /api/epa/lane-b/rmp_public/identity?native_id={PGM_SYS_ID}` | Exact public program/FRS interest identities; no restricted RMP plans, chemicals/OCA or accident assertions |

Bound `limit` 1–50 and `offset` 0–100,000 for supported source datasets. Responses include source provenance, row SHA-256 and unverified location status. Original full `raw_attributes` are suppressed by default; `include_raw=true` requires independently authenticated `researcher/reviewer/admin` role. If missing/mismatched/wrong-year, service must return **503 source unavailable** instead of a misleading no-risk result; malformed queries return 422. Authentication failures return 401 and raw unauthorized access 403. No non-idempotent write endpoints. **Lane E must supply tenant isolation, TLS/SSO, approved path mounting, host rollout and report wiring.**

## E. Real official-source end-to-end validation evidence

| Dataflow gate | Outcome / evidence |
| --- | --- |
| ECHO full national download, schema and geo remediation, 21,303 quarantined keys | [Official importer 39973733592](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39973733592); [13.72GB index source producer 39982893655](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39982893655) |
| ECHO artifact download in **fresh Actions runner**, streamed reassembly and original index SHA match | [Independent replay 39985749332](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39985749332) PASS |
| **Real ECHO private read-only snapshot installation**, 3,208,008 accepted + 21,303 quarantined, native query | [Separate-run installer 39999518064](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39999518064) PASS, source bytes cleaned |
| RCRA full official six-table ingestion and 2-key query | [Original source 39979755246](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39979755246) |
| Independent RCRA published index reconstruction | [39984660816](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39984660816) PASS |
| **Real RCRA private read-only snapshot installation**, all six tables, checksums, source-key queries | [Separate-run installer 39998734713](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39998734713) PASS, source bytes cleaned |
| TRI 1987–2019 all 33 official national year partitions, plus 2020–2024 five partitions | [33 official-year jobs 39985627343](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39985627343); [independent 33-year checksum/year/row reconciliation 39988067337](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39988067337); [five modern official years 39980692415](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39980692415) all PASS |
| TRI restored from independent 2023 & 2024 year artifacts and same native TRIFD query without cross-year merge | [39986571987](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39986571987) PASS |
| **Real TRI 2024 private immutable index** + **real public RMP source index** installed and queried | [Separate-run double-source installer 39999641452](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39999641452) BOTH PASS, source bytes cleaned |
| Full source field/coordinate/date/jurisdiction/flag profiling and authority-ID candidate relations | [39980093306](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39980093306); [ECHO–TRI exact native FRS-ID audit 39987583584](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39987583584) PASS, **75,336** TRI chemical form rows with a reported FRS key also present in ECHO, **0** physical property matches verified |
| FastAPI auth/role and source-failure HTTP contract | [Private app repository CI at PR head](https://github.com/jhennessy-pharm3r/FacilityTest/pull/76/checks); isolated stdlib tests in `lane-b-epa-tests.yml` |

## F. Refresh, rollback, and failure behavior

1. **Discover, don't overwrite.** On reviewed cadence (weekly publisher-drift check for ECHO/RCRA/RMP and annual TRI publication/revision check), download from the listed **official** endpoints into an isolated new versioned staging directory. Keep the old approved source snapshot and original SHA. Do not silently imply a 2025 TRI release exists.
2. **Verify source, not HTTP status alone.** Capture original bytes, SHA-256, response Last-Modified/retrieval time; inspect exact source member/header schema, source IDs, scanned/accepted/rejected/duplicates, date sentinels, coordinate bounds, state codes, TRI chemical reporting units and published year. Recheck RCRA two-key orphan counts and ECHO missing `REGISTRY_ID` quarantine. A schema change, missing year, data deletion, excessive drift, truncated API paging or checksum mismatch is a **FAIL/CHECK**, never an empty clean-risk conclusion.
3. **Normalize and seal.** Rerun `python -m scripts.lane_b_epa.ingest` for ECHO/RCRA and each TRI year, or `python -m scripts.lane_b_epa.rmp_public` for the public RMP layer. Validate `PRAGMA integrity_check`, SHA-256, native-ID lookup and `downloaded == accepted + rejected`. Protect original sources, row fingerprints and quarantine.
4. **Stage and test independently.** Publish short-lived QA plus source-only artifacts; reconstruct each chunk on a **different runner**. Run `install_snapshot` / `install_auxiliary` to a NEW private versioned directory. Verify read-only queries, auth (401), authorized context (200), invalid index (503), raw role restrictions (403) and all reporting partitions. Prevent write access from serving process.
5. **Coordinator-only promotion.** After independent private TLS/SSO/tenant, host durability/backup/restore and >=25 physical-site review tests, Lane E atomically changes environment mounts to approved new paths and restarts the authenticated service. Recheck statuses, full counts, browser and report provenance. Update shared Source Health/coordination ledger only with actual mounted/deployed counts validated from the **real server**; never from CI jobs alone.
6. **Failure/rollback.** If original checksum, manifest, ECHO rejects, missing TRI year, SQLite integrity, auth, source keys or reviewed site coordinates fail, leave old mounted snapshot unchanged; surface `unavailable` / 503. Revert env/mount paths to previous approved immutable snapshot, restart, verify its hashes/counts, then separately investigate. Preserve incident log and original official bytes without exposing private research records.

## G. Explicit blockers/owner

**Merge-review package:** no known lane-owned data-ingestion or source identity validation blocker for published official cohorts; all four actual-source pipelines have successful ephemeral private install tests. **Not production complete**, as mandated by Issue #73.

**Coordinator Lane E must:** review/merge PR #76 without overwriting other lane branches; provide durable authenticated source host/private storage/backup, mount all source-year partitions and source-only indexes, enable router under existing middleware after tenant/role review, reconcile official counts against live API, approve physical site matches independently, update shared Source Health and test >=25 actual facilities across sectors. Do not report 13.4M different facilities or positive risk simply because rows exist. **Production deployed: 0, reviewed insured-site matches: 0.**

**Restricted/unknown:** source laws exclude unapproved RMP plan/offsite-consequence bulk; 2025 TRI Basic endpoint currently 404; ECHO missing key rows remain quarantined; RCRA 11,212 two-key unlinked rows remain unassigned; EPA date placeholders and compliance status flags cannot become audited incident or damage claims without corroboration. CI artifacts expire, so permanent installation requires a coordinator-owned secured destination.
