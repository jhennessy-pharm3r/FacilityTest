# Private indexed EPA FRS and NOAA source service

This is an **operator-controlled, authenticated private deployment**. GitHub Pages is static and never hosts these indexes. Completing an Actions validation or PR does not provision a durable host.

## Verified source-only artifact dependencies

- **EPA FRS:** Download the successful epa-frs-indexed-registry artifact, containing full-frs-index.sqlite and the matching full-frs-index-qa.json from the same Actions run. Its last fully validated cohort contained **5,354,716 EPA reporting identities**, not all physical facilities in the United States or the world.
- **NOAA Storm Events:** Download the successful noaa-storm-events-national-2023-2026 artifact containing storm-only.sqlite, storm-events-manifest.json, private-db-qa.json and original source archives. The October 23, 2026 verified run contains **256,816 regional events**, of which **153,437** have reported reference coordinates. Year 2026 is partial.
- **Keep data separate:** source-only, replaceable immutable SQLite indexes are not writable insured-site research databases. GitHub Actions artifacts expire. Archive exact successful run IDs, source files, SHA256 manifests and QA records in controlled private storage.

## Controlled installation

1. Create a secure source-index directory on the private server. Do not commit SQLite, JSON QA manifests, private insured addresses or secrets to Git. The repository ignores source-index/.
2. Before hosting EPA, independently validate the exact staging artifacts with scripts/install_frs_source_index.py and choose a NEW versioned destination filename. Its full checks include file bytes, original counts, source-only guards, and SQLite quick_check.
3. For NOAA, separately check original source hashes, matching source-year counts and private-db-qa.json. Never substitute a manifest from a different download run.
4. Install both databases and matching manifests as a READ-ONLY mount. Do not mutate mounted SQLite while readers use immutable mode: quiesce readers, change to new versioned snapshot paths, restart the service, and preserve the prior validated version for rollback.
5. Keep the writable insured workspace at a separate path such as /app/data/facility_risk.sqlite.
6. Use TLS through an external identity-aware reverse proxy/VPN, SSO, tenant-scoped permissions, real backups and restore tests before granting external insurer/client access.

Optional local-only .env configuration (Docker paths):

~~~dotenv
FACILITY_RISK_FRS_INDEX_PATH=/app/source-index/frs-2026-10.sqlite
FACILITY_RISK_FRS_INDEX_QA=/app/source-index/frs-2026-10-qa.json
FACILITY_RISK_NOAA_INDEX_PATH=/app/source-index/noaa-2026-10.sqlite
FACILITY_RISK_NOAA_INDEX_MANIFEST=/app/source-index/noaa-2026-10-manifest.json
~~~

The Compose configuration mounts ./source-index read-only under /app/source-index and binds the server to 127.0.0.1:8765. Never expose port 8765 directly to the internet.

## Private API and UI

The **All-industry facilities** page detects a validated FRS index and defaults to searching the national EPA reporting catalog. Private workspace identities remain separately selectable; total identities should not be added or described as unique physical properties.

| Endpoint | Meaning |
| --- | --- |
| GET /api/source-indices/status | EPA/NOAA mounted readiness, source vintage, counts and scope, without exposing local filesystem paths |
| GET /api/universal-facilities/stats | Workspace totals and separately identified FRS counts |
| GET /api/universal-facilities?source=EPA_FRS&q=warehouse&limit=50 | Full indexed national EPA source search, not limited to demonstration facilities |
| GET /api/universal-facilities/{site_id} | EPA source name, registry identifier, original authority and unverified location |
| POST /api/universal-facilities/{site_id}/track | Explicit, authenticated, write-enabled import of only one selected FRS identity as an unverified private research lead |
| GET /api/noaa/storm-events/status | Exact mounted NOAA source-year counts |
| GET /api/noaa/storm-events?year=2025&state=MAINE | Regional weather report query |
| GET /api/facilities/{facility_id}/noaa-storm-events?year=2025 | Contextual nearby-event candidates only after the currently stored site point has been independently verified |

Mount states: not_configured, unavailable, ready_partial and ready_full. Missing or invalid mounted indexes do not produce misleading zero-facility or zero-hazard conclusions. Ready_full refers **only** to the US EPA FRS source identity threshold; it is not worldwide facility, hazard, loss or coverage completeness.

## Acceptance criteria

- All data-bearing API routes require authentication. Without valid credentials, return 401.
- FRS exact identifier, facility name, warehouse and hospital searches return source records with stable pagination; reported total matches the installed QA. Search uses a read-only connection and never changes the source file.
- FRS source IDs are not merged with FDA FEI or other regulatory IDs without independent review.
- A missing, mismatched or private-data-contaminated index reports unavailable; FRS query returns 503, not zero risk.
- Tracking an individual EPA record is disabled by default and, when explicitly authorized, writes only to the separate private research workspace as unverified source provenance.
- NOAA years and record counts match its manifest. Changing or withdrawing a reviewed site coordinate stops site-level proximity queries.
- Nearby NOAA coordinates are only reference points. They do **not** verify flood depth, wind speed, building damage, BI disruption, insured claim or payout.
- Backups, restore/rollback, SSO, tenancy, perimeter controls and real full-cohort hosted benchmarks remain signed-off prerequisites for production operation.

See docs/FRS_INDEX_OPERATIONS.md, docs/NOAA_STORM_EVENTS.md, docs/SECURE_DEPLOYMENT.md and issues #3, #4 and #39 for next work.
