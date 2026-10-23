# EPA Lane B — source-only import

Official sources: [EPA ECHO downloadable archives](https://echo.epa.gov/tools/data-downloads), [EPA TRI Basic annual CSV](https://www.epa.gov/toxics-release-inventory-tri-program/tri-basic-data-files-calendar-years-1987-present), [EPA RMP access restrictions](https://www.epa.gov/rmp/accessing-rmp-data).

Commands (Python 3.11+):

```bash
python -m unittest scripts.lane_b_epa.test_ingest scripts.lane_b_epa.test_rmp_public -v
python -m scripts.lane_b_epa.ingest --source echo --raw-dir /private/epa_raw --output /private/echo_run
python -m scripts.lane_b_epa.ingest --source rcra --raw-dir /private/epa_raw --output /private/rcra_run
python -m scripts.lane_b_epa.ingest --source tri --year 2024 --input /private/official_tri_2024.csv --output /private/tri_run
python -m scripts.lane_b_epa.rmp_public --output /private/rmp_public
```

- Import only officially acquired datasets. TRI needs selected year + official source CSV/ZIP and native TRIFD. EPA ZIPs may contain auxiliary tables whose facility ID is not present. Such members are explicitly skipped, not counted as covered. Audit all archive members before treating coverage as complete.
- Raw fields and native IDs remain distinct in a source-specific SQLite table; no automatic site/parcel or inter-source merges. Multiple rows for the same facility ID stay separate. Reports are not property losses and absent violations do not imply safety.
- Manifest includes raw download SHA256, retrieved UTC, accepted/rejected/indexed counts, duplicate IDs, coordinate presence, and skipped archive members. Use --raw-dir on a secure durable host to retain each downloaded original ZIP. Without --raw-dir URL acquisition uses a disposable temp file; CI only publishes short-lived manifests. Publish aggregates only after source-level validation.
- RMP offsite consequence analyses have controlled access. This importer explicitly refuses bulk RMP; obtain a lawful public non-OCA dataset and source-use review first.
- All industries/facility types in scope, no pharma-only filter. Shared UI and Source Health remain coordinator-owned.

## Actual validation state — 2026-10-23

| Source | Live download | Validated indexed records | Deployed |
| --- | --- | --- | --- |
| ECHO national exporter | **Full official ZIP SHA-reproduced; geospatial and rejects corrected/verified** in [39973733592](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39973733592) | **3,208,008 accepted/indexed; 21,303 missing REGISTRY_ID, no malformed CSV; 3,146,109 accepted coordinate pairs** | No |
| RCRAInfo | **Completed full national download, SHA256 + content QA** in [run 39971197481](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39971197481) | **7,022,589 source table rows, 0 rejected** across 6 tables; facilities table 1,630,839 | No |
| TRI Basic U.S. **1987–2024** | **38 full official annual source imports** [1987–2019 39985627343](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39985627343) / [2020–2024 39980692415](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39980692415), independent 33-year audit [39988067337](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39988067337) | **3,218,093** chemical reporting records, **0 rejected**, individual annual source hashes at `validation/tri_1987_2019.md` and `validation/tri_2020_2024.md` | No |
| RMP public FRS interests | **Full official FRS layer** [run 39971992625](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39971992625); restricted plan/OCA withheld | **21,853** public source records | No |

Next gates: network-enabled complete official run; verify real member schemas and table semantics, original archives and checksum retention, unit semantics, rejected rows, geographic bounds, indexed query examples, application-specific API and durable deployment. Never mark VERIFIED based on passing fixtures or HTTP probes.

## Verified national RCRA run — 2026-10-23
- Original EPA archive checksum: `babf48b1e2388b7f27cfc186cb1e9eb0ecfa26f53476fc81908712e41dfe09f3`.
- All 7,022,589 rows scanned/accepted/indexed; 0 rejected; SQLite integrity OK; 1,522,387 row coordinate pairs; 4,262,613 repeated facility IDs within table members (not an error: events/history are repeated by design).
- Native handler ID: `ID_NUMBER`; NAD83 coordinate fields: `LATITUDE83`, `LONGITUDE83`. Counts by native table in `validation/rcra_20261023.md`. 1,630,839 facility-table records; do not equate total cross-table observations with physical properties. Indexed source is a **disposable Actions artifact** and has not been loaded into durable private serving.

## Verified public RMP-linked source cohort (not restricted plan data)
- Official public EPA GeoPlatform FRS RMP programme-interest layer: **21,853** object IDs fully paginated, indexed and reconciled; all 21,853 have native registry/program identifiers and valid reported coordinate pairs. Validated in [run 39971992625](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39971992625); ledger at `validation/rmp_frs_public_20261023.md`.
- This is **not** a census of insurance properties, RMP plans, OCA, historical releases or hazards. Public FRS identities are separate from physical-site review; staging is not deployed.

## Official TRI 2024 U.S. endpoint
- EPA official page dynamically composes `https://data.epa.gov/efservice/downloads/tri/mv_tri_basic_download/2024_US/csv`; this is a **national, reporting-year-specific Basic dataset**, not a longitudinal release/violation census. The source discovery was validated in [Actions 39972350442](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39972350442).
- Full official 2024 ingestion and native TRI header verification **passed**: [Actions 39972946492](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39972946492). 77,295 accepted/indexed rows, 0 rejected, SHA256 `06dfa3a67bb4c5bd38d9e9f0f7b8bff10b95254a63169423632d7f6f251e1506`, 77,295 valid coordinate pairs; 55,813 repeated TRIFD occurrences due to per-chemical reporting rows. Verified ledger `validation/tri_2024_us_20261023.md`. Historic yearly revisions and amounts/units need separate analysis before underwriting use.

## ECHO national full-exporter validation and remaining QA
- Three full actual official archive runs reproduced 3,229,311 scanned; **3,208,008 accepted/indexed**; **21,303 rejected ONLY due missing native `REGISTRY_ID`**, zero malformed rows, SQLite integrity OK, ZIP SHA256 `116f6e53117b52f7891c6d2466d662f4ee5e29946b065fdb7b97eaf095615899`.
- The originally missed ECHO `FAC_LAT`/`FAC_LONG` fields were corrected; **3,146,109** accepted rows now have valid coordinate pairs; remaining 61,899 accepted rows have incomplete or invalid coordinate pairs. Official schema-vintage and content-level validation [39973733592](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39973733592). Rejected source records now preserve their native raw fields/fingerprint in quarantine, not assigned fabricated keys.
- A schema-version-2 official full-source re-import with original source ZIP, immutable SQLite SHA-256, actual native-ID queries and staged output archives is tracked by [39979755246](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39979755246). Any incomplete Actions run or artifact is NOT deployed.

## Integration-ready source-only query contract

- `python -m scripts.lane_b_epa.read_index --source rcra --index /private/lane_b/rcra.sqlite --manifest /private/lane_b/rcra.manifest.json --source-id <native-RCRA-ID> --activity-location TX`
- `python -m scripts.lane_b_epa.read_index --source echo --index /private/lane_b/echo.sqlite --manifest /private/lane_b/echo.manifest.json --source-id <native-FRS-REGISTRY-ID>`
- `python -m scripts.lane_b_epa.read_index --source tri --index /private/lane_b/tri_2024/tri.sqlite --manifest /private/lane_b/tri_2024/tri.manifest.json --source-id <native-TRIFD>`
- `python -m scripts.lane_b_epa.rmp_lookup --directory /private/lane_b/rmp_public --program-id <native-RMP-PGM_SYS_ID>`

Load matching immutable source-only indices and matching manifests together; hash validation, SQLite integrity, counts and private-data exclusions fail closed. Preserve original ZIP/CSV/JSONL archives outside public Pages. Source-specific RCRA event linkage requires `ID_NUMBER` **and** `ACTIVITY_LOCATION`, while external physical-site linkage requires independent review. The coordinator owns authentication, tenant permissions, private service routing, integration and deployment. See `QA_HANDOFF.md`.


**Integration release contract (authoritative):** [INTEGRATION_RELEASE.md](INTEGRATION_RELEASE.md) — all four real-source install rehearsals passed; how to mount immutable bundles, enable optional private endpoints, refresh safely, and distinguish source rows from insured properties. Current production-deployed source rows remain **0**.
