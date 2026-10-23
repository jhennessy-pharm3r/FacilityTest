# Lane A — production integration and coordinator installation handoff

**Review scope:** [Issue #73](https://github.com/jhennessy-pharm3r/FacilityTest/issues/73), [PR #75](https://github.com/jhennessy-pharm3r/FacilityTest/pull/75). This is a source-ingestion release for **all US industries and facility types**. It is **not** a property-risk prediction, insured claim, nationwide raster/polygon deployment or an independently verified physical-site registry.

**Status:** Source download, normalization, archive verification, local read-only source-index installation, atomic release and query integration have been tested with real official artifacts in Actions. **Authenticated backend deployment and independently reviewed site matching are 0 / not carried out.** Coordinator Lane E must own application integration, durable operation, service authorization, shared Source Health/UI updates and any eventual PR merge. Keep unavailable hazard evidence **UNKNOWN**, never low risk.

## Exact official source evidence / artifact (October 23, 2026)

| Source-grain / identity | Original observed | Normalized accepted | Rejected | Disposable source-only index | Durable service installed | App deployed |
|---|---:|---:|---:|---:|---:|---:|
| FEMA official NFHL layer 28 \`S_Fld_Haz_Ar\`, **6 small QA windows**, \`DFIRM_ID+FLD_AR_ID\` | **34 polygons** | 34 | 0 | **34 features + 34 RTree entries** | **0** | **0** |
| USDA WHP2023 continuous 270m ImageServer — independent geographic QA coordinates | **70** pixels | 70 numeric | 0 | 70 | 0 | 0 |
| USDA WHP2023 classified 270m ImageServer — same coordinates | **70** pixels | 70 class/mask | 0 | 70 | 0 | 0 |
| USDA full official 2023 publisher **administrative summaries** (\`GEOID\`, \`STATE_FIPS\`, \`ZIP\`, management label) | **35,304** publisher rows | 35,304 | 0 | **35,304** | 0 | 0 |
| Authorized/independently verified physical insured sites | 0 | 0 | — | 0 | **0** | **0** |
| **National original WHP2023 raster — separate PR #88 six-TIFF source release** | **6 original GeoTIFF files acquired; 368,424,961 original ZIP bytes; 133,505,015 valid modeled cells per continuous/classified source product** | 6 original TIFF files checksum-verified, 0 rejected | 0 original source files rejected | **6 TIFFs fully cell/mask audited in disposable CI** | **0 permanent production host** | **0** |
| **National original FEMA NFHL polygon corpus (separate flood blocker)** | NOT ACQUIRED (publisher count-only 5,813,220 source polygons) | NOT MEASURED | NOT MEASURED | **0 entire-national polygon corpus** | 0 | 0 |

These cohorts **must never be summed as physical properties or interpreted as insurance losses**. The original USDA 2023 administrative summary is complete at its published geographic grain. It is *not* a raster or a list of facilities.

**Proven end-to-end:** [official complete-source run 39987050225](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39987050225) **SUCCESS**, artifact **12515934383**, original official source files, SQL, per-reply hashes, 34 FEMA polygons and the 35,304/140 USDA records. [Separate USDA bulk 39987666908](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39987666908) and [wildfire 39987666766](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39987666766) **SUCCESS**. [Real preinstall → install → read-only query → identical second installation 39999861590](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39999861590) **SUCCESS**, artifacts include actual installed release ID **\`0fe99942dd2d58919130de5b\`**. The release installed four separate indexes from 181 source files; native-key query examples all returned source evidence and preserved unknown/source grain. **Expanded real-artifact integration proof:** [run 40001064674](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/40001064674) **SUCCESS**, confirming the direct original Actions ZIP and extracted-source staging produce **identical installed release IDs and source counts**. The workflow intentionally modified the real official USDA provenance manifest; its integrity check rejected the altered source with `Original official USDA source ZIP SHA256 mismatch`, proved the previous `current.json` was unchanged, and re-queried the preserved valid index. A follow-up tightened installer symlink rejection. **4 of these 34 FEMA geometries were recorded as generalized in the selected 39987050225 source archive**; other successful live runs varied (e.g. three generalizations), so read geometry tolerance per *artifact*, not a fixed national constant. Same-original-input installation yields identical release file SHA/release ID; a new live extraction is a new source snapshot, not expected to have identical generalized rings or response timestamps.

### Source URLs, licensing, native keys, data vintage and limitations

- **FEMA NFHL official ArcGIS layer 28:** https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28 . \`DFIRM_ID+FLD_AR_ID\` composes \`dfirm:<DFIRM>:fld_ar:<FLD_AR>\`; retain \`OBJECTID\` only as a service-local ID. Original schema includes \`FLD_ZONE\`, \`SFHA_TF\`, \`ZONE_SUBTY\`, \`SOURCE_CIT\`, \`VERSION_ID\`, Esri original polygon rings/CRS. Tested envelope sizes: New Orleans 18, Houston 9, Miami 2, Sacramento 2, Seattle 2, New York 1; flood zones X 23 / AE 10 / VE 1. **Six windows are not nationwide hazard coverage**. 3–4 of the sample geometries may require explicitly flagged source-side simplification due to official oversized API responses, making parcel-boundary decisions inappropriate. Per-\`DFIRM_ID\` effective map/FIRM/LOMR date is NOT independently verified. Federal map and coverage/legal disclaimers apply; review individual effective maps, zoning, local erosion and LOMR updates before underwriting decisions. Official nationwide count-only REST response **5,813,220 original source features** ([run 39987270144](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39987270144)): *publisher count metadata only, zero full national polygon downloads*. ArcGIS official WFS \`GetCapabilities\` and MSC county package \`NFHL_51013C\` failed with connection resets/HTTP 406; no unauthorized workaround attempted.
- **USDA Forest Service WHP2023 continuous raster ImageServer:** https://imagery.geoplatform.gov/iipp/rest/services/Fire_Aviation/USFS_EDW_RMRS_WildfireHazardPotentialContinuous/ImageServer . Source observation key is derived \`usfs_whp_2023_geographic_probe:<region>:<grid_index>\`, with lat/lon and source URL; **no source-native pixel/insured-site ID**. 14 region × 5 public QA coordinates; original continuous model values 0..38140. Do not convert into calibrated insurance probabilities or zero-safe values. Product vintage 2023, revised **July 17, 2024**, landscape inputs substantially **2020**.
- **USDA Forest Service WHP2023 classified raster ImageServer:** https://imagery.geoplatform.gov/iipp/rest/services/Fire_Aviation/USFS_EDW_RMRS_WildfireHazardPotentialClassified/ImageServer . Same 70 QA points, derived region/grid identities; original classes **1=Very low (16), 2=Low (13), 3=Moderate (14), 4=High (9), 5=Very high (3), 6=Non-burnable (14), 7=Water (1)**. The 15 special non-burnable/water classes remain masks, not low risk, and missing sampled raster data must remain UNKNOWN. **Not current fire occurrence, imminent seasonal risk, verified site damage or actual insured losses**.
- **USDA official full 2023 source geography summary ZIP:** https://research.fs.usda.gov/sites/default/files/2024-07/firelab-whp2023_datasummaries.zip . Original **9,229,280 bytes**, SHA-256 **\`1008b6d10c3635c6549dba3d1893381c2e6ed266c59b5fe8648cf5a6dea4b185\`**. County original \`GEOID\` **3,143**, state original \`STATE_FIPS\` **51**, ZIP original \`ZIP\` **32,094** (60 no-acreage \`UNKNOWN_NO_AREA_VALUES\`), and management original source label **16**, including **1 clearly marked grand total**. **35,304 accepted/0 rejected/0 duplicate native source keys**, all four XLSX source SHA records in \`whp_official_index/manifest.json\`. Normalized GZIP source SHA-256 **\`efbdab10e2fb707512643fb35c3d9dacea6817eade38740561a98c8b6e6aee58\`**. Management acreages source-rounded; 3,000-acre explicit tolerance. Preserve geographic IDs as strings, including \`00029\` and state \`06\`. No implied site geocodes from region/ZIP labels or insurance losses.
- **Publisher methodology/rights:** https://doi.org/10.2737/RDS-2015-0047-4 and https://research.fs.usda.gov/firelab/products/dataandtools/wildfire-hazard-potential . USDA Research Data Archive public research license permits reuse without extra authorization/fees with requested attribution; check redistribution/licensing for *specific GeoPlatform services* before exposing pixels to customers. Public FEMA mapping requires appropriate NFIP/effective-study interpretation. **No proprietary insured-property data stored in these public-source artifacts.**

## Reproducible installation — exact Actions official data, no new network ingestion

**Prerequisites:** Python **3.12+**, GitHub CLI authenticated for the private/publisher source artifact if required, Linux persistent disk directory with enough free space (source artifact ≈29MB compressed; source-only indexed/uncompressed SQLite/artifacts ≈100MB, with backup/working room). This importer uses standard Python/SQLite without extra dependencies. Run under a dedicated low-privilege data-ingestion OS identity. Neither the server nor CI should contain insured-site coordinates in the source-only raw artifact.

From a checked-out PR #75 branch (or coordinator-merged commit), download the **known successful** official content artifact (read-only token needs GitHub Actions permission):

\`\`\`bash
mkdir -p /srv/facility-risk/staging/lane-a-source-39987050225
gh run download 39987050225 \
  -R jhennessy-pharm3r/FacilityTest \
  -n lane-a-fema-usfs-massgis-source-qa \
  -D /srv/facility-risk/staging/lane-a-source-39987050225

# Install ONLY Lane A-owned FEMA/WHP source identity indexes, with full raw-SHA,
# stage/index/ID/CRS/SQLite validation before pointer activation.
python -m scripts.lane_a_install \
  --source-root /srv/facility-risk/staging/lane-a-source-39987050225 \
  --destination /srv/facility-risk/private/lane-a \
  --require fema_nfhl \
  --require usda_continuous \
  --require usda_classified \
  --require usda_summary

python -m scripts.lane_a_installed_smoke \
  --destination /srv/facility-risk/private/lane-a \
  --receipt /srv/facility-risk/private/lane-a/coordinator-query-check.json
\`\`\`

**Direct ZIP option:** \`python -m scripts.lane_a_install --archive /path/to/lane-a-official-Actions-artifact.zip --destination /srv/facility-risk/private/lane-a --require fema_nfhl --require usda_continuous --require usda_classified --require usda_summary\`. The installer rejects path traversal/unsafe symlinks, unknown foreign source paths, conflicting duplicate payloads, partial indexes, stale/incomplete FEMA QA window manifests, forged raw checksums, tampered row counts and invalid SQLite. It only skips explicitly enumerated older Lane A diagnostic folders; it **never** imports another lane. Failed validation does **not** advance \`current.json\`.

**Installed directory contract:**

\`\`\`text
/srv/facility-risk/private/lane-a/
  current.json
  releases/<24-character SHA-derived release_id>/
    release-verification.json
    data/lane_a/
      paged_windows/manifest.json
      paged_windows/fema-window-index.sqlite
      paged_windows/raw/...
      whp_regions/manifest.json
      whp_regions/whp-regional-source-only.sqlite
      whp_classified/manifest.json
      whp_classified/whp-classified-source-only.sqlite
      whp_official_summary/whp2023_official_summaries.zip
      whp_official_index/manifest.json
      whp_official_index/whp2023-source-geographies.ndjson.gz
      whp_official_index/whp2023-source-geographies.sqlite
\`\`\`

Installer writes read-only files (0444), uses cryptographic content-addressed release IDs, validates native source/index counts, original raw response checksums and real read-only query outputs before swapping \`current.json\` atomically. A second install of the identical source contents returns the *same* release ID without a second release; every source component retains its distinct raw provenance. **The installer does not run an HTTP server, change shared app Source Health, store insurer records, or claim production deployment.** Additional OS access controls/backup/encrypted disk/tenant authorization are Lane E responsibilities. \`current.json\` is a *local index activation*, not proof of public UI deployment.

### Public-source query contract (must be wrapped by authenticated Lane E API)

\`\`\`python
from facilityrisk.lane_a_installed import (
    query_publisher_id, query_raster_probe, query_reviewed_coordinate,
    installed_release,
)
root = "/srv/facility-risk/private/lane-a"

# Exact original USDA 2023 source IDs: all source aggregates, not insured buildings.
zip_record = query_publisher_id(root, "usda_summary",
    geography_type="zip", original_id="00029")
unassessed_zip = query_publisher_id(root, "usda_summary",
    geography_type="zip", original_id="10168")
assert unassessed_zip["source_coverage"] == "UNKNOWN_NO_AREA_VALUES"
county = query_publisher_id(root, "usda_summary",
    geography_type="county", original_id="06017")

# Exact original FEMA source polygon, not a canonical building ID:
fema = query_publisher_id(root, "fema_nfhl",
    original_id="dfirm:06067C:fld_ar:06067C_1223")

# USDA original QA raster point, NOT a physical property:
continuous = query_raster_probe(root, "usda_continuous",
    region="alaska", grid_index=0)
classified = query_raster_probe(root, "usda_classified",
    region="alaska", grid_index=0)

# Only after Lane E provides independently corroborated WGS84 property/site
# coordinate evidence and reviewer workflow. Outside completed QA windows
# is UNKNOWN; generalized/boundary geometries require review.
# query_reviewed_coordinate(root, longitude=<lon>, latitude=<lat>,
#     site_reference=<reviewed_site_ref>, coordinate_evidence=<citation>,
#     coordinates_corroborated=True)
\`\`\`

**Proposed private API ownership for coordinator:** \`GET /api/sources/lane-a/usda-whp2023/{geography_type}/{original_id}\` returns original publisher aggregate and source provenance; \`GET /api/sources/lane-a/fema-nfhl/{dfirm_id}/{flood_area_id}\` returns source geometry metadata with precision flags; \`GET /api/sources/lane-a/usda-whp2023/qa-pixel/{source}/{region}/{index}\` is explicitly *internal QA*, not production site assessment; a separate *review-authenticated* POST for \`site_reference+WGS84+coordinate_evidence\` may access \`query_reviewed_coordinate\` but never auto-save a canonical site match. Authenticate and authorize the caller, constrain result size/rate limits/tenant boundary, log original source key+release SHA, return clear \`NOT_IN_STAGED_SOURCE_INDEX\` / \`UNKNOWN_INCOMPLETE_SOURCE_COVERAGE\` and no fake zero risk for missing source evidence.

## Refresh, retention, rollback, operating failure gates

1. **Sources/versions:** Poll FEMA current effective map studies and official NFHL service for material changes, but do not treat a changed global metadata count as downloaded new polygons. NFHL API can reset TLS connections/return HTTP 500; importer alternates supported GET/POST, retries, recursively splits oversized queries, flags generalization and reconciles original IDs/counts. Do not activate partially retrieved windows; keep prior verified release, record exact upstream failure, and retry through authorized endpoints. July 2025 optional MassGIS archive is older than current national maps and is not a fallback for underwriting determinations.
2. **USDA:** WHP2023 is a fixed 2023 modeled product revised 2024; refresh to a newly published official WHP version, **never silently relabel old WHP2023 pixels as the current year**. When a successor version exists, separately download and verify new ZIP/raster metadata and preserve product-version+original source SHA. Calendar polling alone does not make data fresher. New age/masks/source vintage require explicit Source Health review.
3. **Validation:** Per source do download → retain original response/XLSX ZIP/hash → normalize at original source grain → rejects/nulls/duplicate native ID audit → local SQLite and RTree \`PRAGMA quick_check\` → independent original-row/normalization SHA → \`scripts/lane_a_install\` pre-activation verification → \`scripts/lane_a_installed_smoke\` actual read-only SQL queries. Reject negative/missing acreage, missing native keys, malformed ring/CRS, ambiguous source joins and mismatched pixel coordinates. Reconcile numeric accepted/rejected/indexed separately. Never substitute test fixtures for real source counts.
4. **Release operation:** Run incoming builds on staging, install as a distinct content-addressed release, inspect \`release-verification.json\` + read-only query receipt, then connect authenticated app to the reviewed release via Lane E. Installer activates a *local* release pointer after its own gates; coordinator must separately approve user-visible source availability. For rollback, atomically restore \`current.json\` to the previous known-good release ID/relative path after rehash validation of its \`release-verification.json\` and source content. Retain last known-good artifacts/backups and log both releases in the change record. Do not overwrite prior source data or merge incompatible vintages.
5. **CI/GitHub:** Actions QA artifacts are retained **7 days** and are **not persistent hosting**. The pinned official-source artifact run 39987050225 must be exported to durable authorized object storage before expiry (or fully re-ingested and revalidated). Production backup/restoration, private disk capacity, TLS, auth, logging, schedule, source health UI, tenant boundaries and actual application verification belong to Lane E (#39).

## Remaining explicit blockers

- **FEMA national current polygon coverage not acquired/served:** only 34 polygons from six minuscule QA envelopes. Publisher reports 5,813,220 *source records* in a count-only request, NOT downloaded. Official full county ZIP via MSC returned HTTP 406/reset; WFS returned reset; valid alternative/full bulk and per-DFIRM effective date review still required. Baseline retained six-window artifact can be installed as bounded QA only.
- **USDA full original national WHP2023 raster acquired and entirely audited, but not privately deployed:** Original USDA Research Data Archive full ZIP 368,424,961 bytes, SHA256 `7f10f1f8dd97551b8be1458fe0ec924df60b2cea7ece2d1af4c3c1166d1895ab`; six original CONUS/Alaska/Hawaii continuous/classified 270m TIFFs verified; 133,505,015 valid and 168,553,707 masked modeled cells **per source product**. Real original model pixels queried through authenticated source API and private browser in transient CI, [run 40010151712](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/40010151712). **0 permanent source-host installations and 0 verified insured-property links**. See [national raster runbook](LANE_A_WHP2023_NATIONAL_RASTERS.md) and [current private API integration](LANE_A_PRIVATE_API_INTEGRATION.md). Source pixels and aggregates must never be represented as insured facilities, fire incidents, calibrated loss risks or covered damages.
- **Site geocoding and claims outcomes:** 0 independent confirmed physical insured sites, 0 claims/losses or insurance-policy coverages; preserve uncertain map precision and source identities separately. Issue #4 calls for ≥25 cross-industry physical-property case audits/negative controls.
- **Application production deployment:** 0 Lane A records installed in a verified authenticated Facility Risk App backend, 0 user-visible production hazard responses. Lane E must provision durable storage, integrate and secure queries, publish truthful Source Health status, run live app tests, and merge the dedicated PR when approved.

### Merge-ready source package, NOT complete risk-product deployment

Pass/retained artifacts: **official-source ingestion** (FEMA [39987050225](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39987050225), USDA [39987666908](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39987666908)/[39987666766](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39987666766)), **repository CI**, **read-only source release and original data integration [39999861590](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39999861590)**. Dedicated PR remains unmerged; coordinator review can merge **only** the isolated/source-owned package after final green head-run CI and conflict checks. Integration-ready does **not** satisfy the overarching Issue #73 deployment definition of done.
