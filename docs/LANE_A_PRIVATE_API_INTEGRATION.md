# Lane A — authenticated Facility Risk App integration

**Code state:** FEMA NFHL / USDA WHP2023 government-source ingestion PR [#75](https://github.com/jhennessy-pharm3r/FacilityTest/pull/75) is merged. This integration adds a private FastAPI adapter to the existing source-only immutable release. All facility types and industries are eligible; a publisher source ID is **not** a verified physical property, damage claim, insured loss or policy coverage.

**Proof:** [Real official-source FastAPI CI run 40004684317](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/40004684317) passed authentication, archive SHA-256 validation, SQLite read-only queries, missing-coverage semantics and unreviewed-site gate against the original fully installed [source release 0fe99942dd2d58919130de5b](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/40001237902). The test runner is **not a persistent production host**.

## Install on a persistent operator-controlled private server

Use the repo's configured *private* FastAPI/Compose deployment. Do not put the artifact into `web/`, Pages, `data/` in Git, or any shared publicly reachable bucket. Provision a real host with encrypted persistent disk, credentials, identity-aware TLS proxy, private network access, backups and monitored storage; those services have **not** been provisioned by this GitHub code change.

From the repository checkout on that host, obtain the actual original government source artifact (GitHub Actions artifacts expire after seven days):

```bash
# Download and retain the original validated government source files outside git.
mkdir -p ./source-index/staging-lane-a
gh run download 39987050225 \
  -R jhennessy-pharm3r/FacilityTest \
  -n lane-a-fema-usfs-massgis-source-qa \
  -D ./source-index/staging-lane-a

# Recheck every original official source-response SHA and original publisher
# XLSX/ZIP; prove native IDs/accepted/rejected/SQLite and read-only queries
# before atomically activating a content-addressed immutable release.
python -m scripts.lane_a_install \
  --source-root ./source-index/staging-lane-a \
  --destination ./source-index/lane-a \
  --require fema_nfhl \
  --require usda_continuous \
  --require usda_classified \
  --require usda_summary

python -m scripts.lane_a_installed_smoke \
  --destination ./source-index/lane-a

# Configure the path visible INSIDE the container in an untracked .env:
# FACILITY_RISK_LANE_A_INDEX_ROOT=/app/source-index/lane-a
# And supply a unique long FACILITY_RISK_AUTH_TOKEN from a secret manager.
docker compose up --build -d
```

The Compose source index mount is `./source-index:/app/source-index:ro`. It is separate from the independently writable insured workspace `./data:/app/data`. The server listens only on `127.0.0.1:8765` and rejects missing/invalid API credentials. The demonstrated Basic/Bearer token is single-tenant research authentication, **not** production-grade OIDC, tenant separation or independent insurance client authorization. Do not expose the port or client data before completing `docs/SECURE_DEPLOYMENT.md` / Issue #39.

The service scans/re-hashes the installed publisher files for an unchanged immutable release, verifies the saved source-file SHA map, row counts, source identities, SQLite `PRAGMA quick_check`, absence of private workspace tables, FEMA RTree count, 60 original USDA no-acreage ZIP rows, 70 aligned USDA original QA raster points, and absence of a nonempty SQLite WAL. It caches validation for the unchanged snapshot and revalidates on a version/pointer/database file change. If the mount is absent or fails validation, source status becomes `not_configured` or `unavailable`, all data queries return HTTP **503**; *not* zero hazard.

## Authenticated read-only API

All these routes are protected by the existing FastAPI authentication middleware. Status is included in the existing consolidated private `GET /api/source-indices/status` as `lane_a`; the browser **private Source Health** page shows real mounted counts if available. The static GitHub Pages preview shows only publisher QA ledger and **never** reports a private install unless queried through an actual authenticated backend.

| Method/path | Meaning |
|---|---|
| `GET /api/lane-a/status` | Mount state `not_configured` / `unavailable` / `ready_partial`, original source counts, vintage, scope, release ID, no verified insured-site links |
| `GET /api/lane-a/usda-whp2023/geography/zip/00029` | Original five-character ZIP publisher aggregate (not a property) |
| `GET /api/lane-a/usda-whp2023/geography/zip/10168` | Preserves 2023 original `UNKNOWN_NO_AREA_VALUES`, never low wildfire hazard |
| `GET /api/lane-a/usda-whp2023/geography/county/06017` | Original county GEOID, preserving leading zero |
| `GET /api/lane-a/usda-whp2023/geography/state/06` | Original state FIPS |
| `GET /api/lane-a/usda-whp2023/geography/management_jurisdiction/Grand%20Total` | Publisher management grand total *row*, not new geographic area |
| `GET /api/lane-a/fema-nfhl/06067C/06067C_1223` | Original `DFIRM_ID+FLD_AR_ID` source polygon metadata with original response SHA and geometry precision (not parcel boundary) |
| `GET /api/lane-a/usda-whp2023/qa-pixel/usda_continuous/alaska/0` | An original **fixed QA pixel**, not property raster lookup |
| `GET /api/lane-a/usda-whp2023/qa-pixel/usda_classified/alaska/0` | Original **fixed QA classified pixel**, including masks as distinct values |
| `GET /api/facilities/{facility_id}/fema-nfhl` | Read-only FEMA RTree/polygon evidence at server-stored **currently reviewed** site coordinate only; unreviewed/moved coordinates return `UNKNOWN_UNVERIFIED_SITE_COORDINATE` |

The last endpoint **does not accept** client-supplied lat/lon or a caller-provided `reviewed=true` flag. It reads `facilities` and `location_reviews` from the authenticated private workspace, verifies equality to the independently recorded currently reviewed coordinate (precision `site_verified` or `property_polygon`), and uses the original cited source URL. It does not auto-link any FEMA source identity to an insured facility, save a risk conclusion, or infer covered property damage. Geometry simplified at source, legal NFIP effective FIRM/LOMR changes and source boundaries still require qualified review. Outside fully enumerated **six tiny FEMA QA windows** the correct state is **UNKNOWN**.

**Internal QA note:** The older Lane A four-source release has only the fixed USDA **70+70 ImageServer QA pixels**; do not use those as nationwide raster lookups. A **separate, newly verified full six-GeoTIFF WHP2023 source release** now exists ([PR #88](https://github.com/jhennessy-pharm3r/FacilityTest/pull/88), [full real-source validation](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/40008808882)). Its 133,505,015 valid modeled cells **per continuous/classified product** across CONUS, Alaska, Hawaii are available through the *separately mounted* `FACILITY_RISK_WHP2023_RASTER_ROOT`; only stored independently reviewed private facility points are eligible for contextual sampled source readings. This is not a current-season fire forecast, insurer loss estimate, or verified property risk score.

## Separate complete USDA national WHP2023 GeoTIFF release and authenticated facility-context queries

The prior FEMA/WHP query archive is **four small source-only SQLite indexes**; its 70+70 model source samples remain immutable. [Source PR #88](https://github.com/jhennessy-pharm3r/FacilityTest/pull/88) separately acquired the official Forest Service original **368,424,961-byte** 2023 national six-GeoTIFF archive, with pinned original ZIP SHA-256 `7f10f1f8dd97551b8be1458fe0ec924df60b2cea7ece2d1af4c3c1166d1895ab`, six independent TIFF original hashes and **100% native raster cell/mask audits**: CONUS, Alaska, Hawaii; 133,505,015 modeled valid cells per continuous/classified product and 168,553,707 masked/nodata cells per product. Original source resolution is 270 metres. Original class 6 non-burnable and 7 water are **distinct masks, not lower risk or loss probabilities**; original continuous value `0` can be a valid modeled cell. This is a 2023 model based on predominantly 2020 fuels, not current wildfire occurrence.

For a *separately provisioned* private server running the current repository, with NumPy/rasterio installed as defined in `requirements.txt`, run:

```bash
python -m scripts.lane_a_whp_full_raster \
  --root ./source-index/whp2023-full \
  --expected-sha256 7f10f1f8dd97551b8be1458fe0ec924df60b2cea7ece2d1af4c3c1166d1895ab \
  --full-audit
```

In the private, untracked `.env`, add `FACILITY_RISK_WHP2023_RASTER_ROOT=/app/source-index/whp2023-full`. The existing Compose source-index volume is mounted read-only. The private app exposes these **authenticated** endpoints:

- `GET /api/lane-a/whp2023/full-status` — `not_configured` / `unavailable` / `ready_publisher_rasters`; original source SHA, six TIFF count, 133.5M valid and 168.55M masked cells per product, all three original geographic domains. `ready_publisher_rasters` means a validated source snapshot mounted **on that responding private server**, NOT an insurer-wide deployed risk product.
- `GET /api/facilities/{facility_id}/usfs-whp2023` — original 270m classified/continuous source native pixel observations for the **server-stored currently independently reviewed** coordinate only. Unsupported/unreviewed coordinates return UNKNOWN; 6/7 are special masks; not a building identifier, claim, rating, current fires or an insured loss. No caller-supplied arbitrary lat/lon is accepted.

The combined private `/api/source-indices/status` and private Source Health view show the distinct complete original raster source state alongside earlier four-source Lane A indexes without summing pixel and source-record counts. The private natural-hazard panel has a separate original wildfire raster query that is **disabled** when the six real source TIFFs are not actually mounted. GitHub Pages remains a static viewer with source metadata only. End-to-end original **full 368MB source download → six georeferenced pixel QA → authenticated FastAPI native pixel lookups → Chromium browser** passed in [CI run 40010151712](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/40010151712) with 0 verified insured-site links and 0 external host deployment. See full [raster provenance, refresh, rollback and limitations](LANE_A_WHP2023_NATIONAL_RASTERS.md).

## Real-data acceptance test on the operator's host

```bash
# Run only in a controlled private test service environment, not against
# client-identifiable production workspaces. The fixture creates one research
# intake with no reviewed location, to prove no fabricated site match.
FACILITY_RISK_REQUIRE_AUTH=1 \
FACILITY_RISK_AUTH_TOKEN='<secret-manager-test-token-at-least-24-chars>' \
FACILITY_RISK_DB=/srv/facility-risk/test-workspace.sqlite \
FACILITY_RISK_LANE_A_INDEX_ROOT=/srv/facility-risk/source-index/lane-a \
python -m scripts.smoke_lane_a_private_api
```

The known successful CI test [40004684317](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/40004684317) used **original real government-source records**, not simulated source rows: **34** FEMA polygons (+34 RTree entries, 4 marked generalized in the selected archive), **70** continuous pixels, **70** classified pixels, **35,304** USFS published regional administrative source rows (3,143 counties, 51 states, 32,094 ZIPs and 16 management records). Source ZIP SHA-256 `1008b6d10c3635c6549dba3d1893381c2e6ed266c59b5fe8648cf5a6dea4b185`. The source release is **intentionally bounded** for FEMA and raster point samples; it is *not* the current U.S.-wide 5,813,220-source-feature FEMA corpus, not the full 270m raster, and not 35,478 independently verified insurance properties.

## Readiness meanings and remaining deployment conditions

- **MERGED:** Lane A original ingestion package is in source control; does not confer facility association or database availability.
- **VERIFIED IN CI:** Original downloads, accepted/rejected counts, native keys, original SHA-256, row integrity and end-to-end authenticated source-only queries passed on a transient GitHub Actions runner. This is the current validated status.
- **PRIVATE INDEX MOUNTED:** Only after a controlled persistent server installs the release, source path/env is configured, and live authenticated API status reports `ready_partial` (never national completeness). Runtime verification must be done on the *actual host*, not substituted with a CI test.
- **PRODUCTION/CLIENT DEPLOYED:** Requires an actual TLS/SSO/tenant-scoped reverse proxy, backup/restore, monitoring, legal/data-use approval, release and source-history management, independent cross-industry site-coordinate QA and audited claims/engineering limitations. Currently **NOT VERIFIED / NOT DEPLOYED**.

**Hard external/operational blockers:** FEMA MSC county archive via authorized documented endpoint returned HTTP 406 or TCP reset; official WFS caps had resets. Only 34 original flood polygons in six bounded windows are verified; complete nationally current FEMA polygon geometry and independent FEMA FIRM/LOMR effective map date reconciliation remain unavailable. The original national WHP2023 270m USDA raster **has now been acquired, entirely pixel-audited, and authenticated-query validated in temporary GitHub Actions** but has **not been installed on a permanent server**. No independently verified insurer-site facility matches, protected production tenant/OIDC infrastructure, claims/loss outcomes, or authenticated durable backend host were supplied. The 2023 USDA publisher geography summaries and modeled cells do not establish insured losses. See [full national raster handoff](LANE_A_WHP2023_NATIONAL_RASTERS.md).

See [Lane A source-provenance handoff](LANE_A_INSTALLATION_HANDOFF.md), [security blueprint](SECURE_DEPLOYMENT.md), [durable hosting blocker #39](https://github.com/jhennessy-pharm3r/FacilityTest/issues/39), and [coordination Issue #73](https://github.com/jhennessy-pharm3r/FacilityTest/issues/73).
