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
| ECHO | Official national ZIP import initiated in GitHub Actions; large-cohort run incomplete as of this ledger update | **Not validated** | No |
| RCRAInfo | **Completed full national download, SHA256 + content QA** in [run 39971197481](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39971197481) | **7,022,589 source table rows, 0 rejected** across 6 tables; facilities table 1,630,839 | No |
| TRI Basic 2024 U.S. | **Full official 60,550,684-byte download + content QA** in [run 39972946492](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39972946492) | **77,295** chemical reporting records, 0 rejected, 77,295 with coordinates | No |
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

## Scope of remaining ECHO gate
- Official ECHO national exporter full-source ingest launched through GitHub Actions runs [39970808792](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39970808792), [39970938436](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39970938436), and [39971100330](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39971100330). National accepted/indexed count remains unverified until these jobs finish and content manifests are inspected. Treat extended ingest processing as an **outstanding validation gate**, not a positive source health state.
