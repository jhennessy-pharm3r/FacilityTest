# EPA Lane B — source-only import

Official sources: [EPA ECHO downloadable archives](https://echo.epa.gov/tools/data-downloads), [EPA TRI Basic annual CSV](https://www.epa.gov/toxics-release-inventory-tri-program/tri-basic-data-files-calendar-years-1987-present), [EPA RMP access restrictions](https://www.epa.gov/rmp/accessing-rmp-data).

Commands (Python 3.11+):

```bash
python -m unittest scripts.lane_b_epa.test_ingest -v
python -m scripts.lane_b_epa.ingest --source echo --raw-dir /private/epa_raw --output /private/echo_run
python -m scripts.lane_b_epa.ingest --source rcra --raw-dir /private/epa_raw --output /private/rcra_run
python -m scripts.lane_b_epa.ingest --source tri --year 2024 --input /private/official_tri_2024.csv --output /private/tri_run
```

- Import only officially acquired datasets. TRI needs selected year + official source CSV/ZIP and native TRIFD. EPA ZIPs may contain auxiliary tables whose facility ID is not present. Such members are explicitly skipped, not counted as covered. Audit all archive members before treating coverage as complete.
- Raw fields and native IDs remain distinct in a source-specific SQLite table; no automatic site/parcel or inter-source merges. Multiple rows for the same facility ID stay separate. Reports are not property losses and absent violations do not imply safety.
- Manifest includes raw download SHA256, retrieved UTC, accepted/rejected/indexed counts, duplicate IDs, coordinate presence, and skipped archive members. Use --raw-dir on a secure durable host to retain each downloaded original ZIP. Without --raw-dir URL acquisition uses a disposable temp file; CI only publishes short-lived manifests. Publish aggregates only after source-level validation.
- RMP offsite consequence analyses have controlled access. This importer explicitly refuses bulk RMP; obtain a lawful public non-OCA dataset and source-use review first.
- All industries/facility types in scope, no pharma-only filter. Shared UI and Source Health remain coordinator-owned.

## Actual validation state — 2026-10-23

| Source | Live download | Validated indexed records | Deployed |
| --- | --- | --- | --- |
| ECHO | NOT TESTED in this runtime (DNS/network blocked) | Unknown | No |
| RCRAInfo | **Completed full national download, SHA256 + content QA** in [run 39971197481](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39971197481) | **7,022,589 source table rows, 0 rejected** across 6 tables; facilities table 1,630,839 | No |
| TRI | Official year-specific file not acquired in this runtime | Unknown | No |
| RMP | Bulk download deliberately blocked by access constraints | 0 | No |

Next gates: network-enabled complete official run; verify real member schemas and table semantics, original archives and checksum retention, unit semantics, rejected rows, geographic bounds, indexed query examples, application-specific API and durable deployment. Never mark VERIFIED based on passing fixtures or HTTP probes.

## Verified national RCRA run — 2026-10-23
- Original EPA archive checksum: `babf48b1e2388b7f27cfc186cb1e9eb0ecfa26f53476fc81908712e41dfe09f3`.
- All 7,022,589 rows scanned/accepted/indexed; 0 rejected; SQLite integrity OK; 1,522,387 row coordinate pairs; 4,262,613 repeated facility IDs within table members (not an error: events/history are repeated by design).
- Native handler ID: `ID_NUMBER`; NAD83 coordinate fields: `LATITUDE83`, `LONGITUDE83`. Counts by native table in `validation/rcra_20261023.json`. 1,630,839 facility-table records; do not equate total cross-table observations with physical properties. Indexed source is a **disposable Actions artifact** and has not been loaded into durable private serving.
