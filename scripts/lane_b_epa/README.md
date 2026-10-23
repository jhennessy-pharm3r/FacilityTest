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
| RCRAInfo | Official archive downloaded in GitHub Actions; initial schema runs rejected zero-row ingest; corrected ID_NUMBER mapping run pending | Unknown | No |
| TRI | Official year-specific file not acquired in this runtime | Unknown | No |
| RMP | Bulk download deliberately blocked by access constraints | 0 | No |

Next gates: network-enabled complete official run; verify real member schemas and table semantics, original archives and checksum retention, unit semantics, rejected rows, geographic bounds, indexed query examples, application-specific API and durable deployment. Never mark VERIFIED based on passing fixtures or HTTP probes.
