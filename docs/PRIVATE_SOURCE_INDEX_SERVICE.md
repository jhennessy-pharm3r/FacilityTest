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

## EPA environmental compliance source-only integration (all industries)

The merged Lane B importer now has a coordinator-approved optional read-only source API for **ECHO, RCRAInfo, TRI Basic 1987–2024 and public FRS-RMP**. It does not replace FRS universal identity search; it is a separate regulator-native observation index, **not** a canonical insured-site or regulatory violation attribution.

- Versioned, original SHA-256-validated bundles mount beneath `/app/source-index`, with original ZIP/CSV/JSONL and quarantined records preserved.
- `/api/epa/lane-b/status` enumerates `not_configured`, `unavailable` or `mounted_source_only` independently per source. `/api/source-indices/status` includes the same private `lane_b_epa` readiness object; never equate “mounted” with verified insured-property match or production release approval.
- `GET /api/epa/lane-b/{source}/identity?native_id=...` requires the regulator’s **exact original ID**, with two-character `activity_location` for RCRA and explicit year for TRI. Program interest RMP is public metadata only. Raw attributes need researcher/reviewer/admin credentials.
- The private research UI exposes **EPA regulatory evidence** only from a genuinely mounted private API. GitHub Pages cannot serve the index and may not claim these observations are deployed.
- `FACILITY_RISK_LANE_B_ROUTES_ENABLED=0` by default, `FACILITY_RISK_ENABLE_WRITES=0`; private Docker image includes the source adapter and drops privileges to UID 10001. Production requires operator-controlled source archive retention, TLS/SSO, multi-tenant security, and reviewed site links.

**Exact artifact IDs, restore, installation, environment variables, UID permissions, expected source counts, live smoke tests, and rollback:** [EPA Lane B operator runbook](EPA_LANE_B_DEPLOYMENT.md). Source-level original URL/hash audit: [Lane B integration release ledger](../scripts/lane_b_epa/INTEGRATION_RELEASE.md). The real non-root Docker and authenticated HTTP acceptance used official public RMP observations [Actions run 40004791507](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/40004791507). **Actual live production source rows remain 0 until independently hosted and measured.**
