# Lane A: FEMA NFHL flood and USDA wildfire source evidence

**Scope:** All US facility types and industries. All records below are government geospatial *source observations*, not a census of independently verified insured properties. FEMA polygons, USDA raster pixels, ZIP/county/state summaries, and management jurisdictions are different source grains. Nothing is automatically assigned to a canonical facility.

**Coordination:** [Issue #73](https://github.com/jhennessy-pharm3r/FacilityTest/issues/73), dedicated unmerged [draft PR #75](https://github.com/jhennessy-pharm3r/FacilityTest/pull/75), branch `ingest/fema-wildfire-lane-a-20261023`. The only writes are owned Lane A scripts, tests, workflows, library modules and this document. Coordinator Lane E controls shared manifests, UI, integration, durable hosting, cross-source facility review and final merge. The GitHub Pages app cannot privately serve a 35k+ source index or run scheduled server-side ingestion.

## Current evidence ledger — 2026-10-23

Every count is **real official-source content observed and reconciled in GitHub Actions or downloaded artifacts**; fixture records are never included. "Indexed" below means **temporary source-only SQLite on an Actions runner**, not a persistent production DB.

| Source and exact grain | Real publisher rows/pixels downloaded | Normalized/accepted | Rejected in successful source replies | Ephemeral indexed | Permanently deployed |
|---|---:|---:|---:|---:|---:|
| FEMA NFHL layer 28: six bounded official query windows, distinct flood-area polygons | **34** | **34** | 0 | **34 + 34 polygon RTree bounds** | **0** |
| USDA WHP 2023 270m **continuous** ImageServer, 14 regions × 5 QA coordinates | **70 pixel replies** | **70 numeric** | 0 | **70 point observations** | **0** |
| USDA WHP 2023 270m **classified** ImageServer, same 70 QA coordinates | **70 pixel replies** | **70 valid classes/masks** | 0 | **70 point observations** | **0** |
| USDA official WHP2023 complete **geographic summary ZIP**, four publisher workbooks | **35,304 aggregate source rows** | **35,304** | 0 | **35,304** | **0** |
| Independently corroborated physical properties linked | **0** | 0 | n/a | 0 | **0** |
| Entire national NFHL polygon corpus and entire 270m national WHP raster | **NOT downloaded** | not measured | not measured | **0 full-corpus** | **0** |

**Do not sum these unlike rows as physical buildings, claims, losses or unique risk events.** No observed polygon means **UNKNOWN** until local map coverage and effective date are independently established. A failed network request has unknown source totals, not zero hazard. No property risk score is generated here.

### FEMA NFHL primary — official live service

Publisher: FEMA, National Flood Hazard Layer **S_Fld_Haz_Ar**, layer 28:
https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28

Fully paged source validation: [run 39981174363](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39981174363), archived original official source replies and temporary SQLite in artifact **12513528409**. A second independent run [39982899854](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39982899854) also completed the six bounded FEMA-window step with 34 matching source records, though its overall legacy workflow was red when another capped FEMA smoke request failed. This is a **successful data step in a partially failing multi-source workflow**, not a claim that every later government API request succeeded. A dedicated FEMA-only [Actions workflow](../.github/workflows/lane-a-fema-windows.yml) runs the strict pagination/geometry/query gate independently.

| Geographic WGS84 QA envelope (not insured sites) | Original NFHL polygon IDs reconciled to server count |
|---|---:|
| New Orleans | 18 |
| Houston | 9 |
| Miami | 2 |
| Sacramento | 2 |
| Seattle | 2 |
| New York | 1 |
| **Total** | **34** |

Actual source schema: `OBJECTID`, `DFIRM_ID`, `FLD_AR_ID`, `VERSION_ID`, `FLD_ZONE`, `ZONE_SUBTY`, `SFHA_TF`, `SOURCE_CIT`, original Esri rings and additional FEMA attributes. **6 distinct DFIRM IDs**, 0 null DFIRM IDs and 0 null source citations in the validated 34-row sample. Zone distribution: **X=23, AE=10, VE=1**. All 34 source polygons have distinct composite `dfirm:<DFIRM_ID>:fld_ar:<FLD_AR_ID>` native keys. Service `OBJECTID` is retained but not promoted to a universal property identity.

The importer explicitly queries `returnIdsOnly` and `returnCountOnly` for each envelope, compares original server row counts to every fetched batch/SQLite membership, retains original source-response SHA-256, and indexes source feature bounding boxes in SQLite RTree. Batches that hit ArcGIS HTTP 500 or payload limits are **split recursively**. Where a single polygon exceeds the response limit, the FEMA service returns a generalization request with `maxAllowableOffset=0.000005` degrees; **3 of the 34** indexed geometries were generalized and are individually flagged `GENERALIZED_REVIEW_REQUIRED`. The remaining **31** retained unsimplified API geometry. These polygons are **not suitable for definitive parcel boundaries**, and the per-map legal/effective date has **not been independently validated from the originating study**.

**Important: 34 source polygons across six small envelopes is not national FEMA completeness.** The initial New Orleans capped query returned only 10 of 18; paginator corrected this. The official API remains intermittent, including `[Errno 104] Connection reset by peer`, TLS handshake timeout, HTTP 500 and 15MB-per-reply limits. A later run may be red or return only partially staged windows; the strict source workflow does not promote partial windows to complete.

Official alternative investigated: the FEMA Map Service Center published direct download convention, product `NFHL_51013C`, https://msc.fema.gov/portal/downloadProduct?productID=NFHL_51013C. GitHub Actions attempts returned **HTTP 406 Not Acceptable** or **connection reset**; **0 county-product ZIPs** validated. Direct access was not bypassed. The state MassGIS FEMA-derived archive is tested separately and **never substitutes** for current national FEMA; a prior unrelated StoryMap ArcGIS layer returned `400 Item does not exist or is inaccessible`, and the lane switched the probe to the actual MassGIS government FeatureServer endpoint. State publisher data have a **July 18, 2025** FEMA vintage; they cannot be called current October 2026 national maps.

Source attribution/rights: FEMA's public government metadata is https://catalog.data.gov/dataset/national-flood-hazard-layer. Preserve FEMA map/status/zone and `SOURCE_CIT`, and consult effective FIRM/FIS and LOMR records for binding insurance/parcel determinations. Neither FEMA's `X` zone nor absence of polygons is interpreted as safe/no-flood exposure.

### USDA wildfire continuous and classified 270m raster — two different source products

Official USDA USFS GeoPlatform ImageServers:

- Continuous: https://imagery.geoplatform.gov/iipp/rest/services/Fire_Aviation/USFS_EDW_RMRS_WildfireHazardPotentialContinuous/ImageServer
- Classified: https://imagery.geoplatform.gov/iipp/rest/services/Fire_Aviation/USFS_EDW_RMRS_WildfireHazardPotentialClassified/ImageServer

Independent official-source [raster run 39985460693](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39985460693) **SUCCESS**, artifact **12514294355**, 16 source-specific fixture tests PASS. The actual **70 continuous and 70 classified geographic pixel replies** were downloaded and indexed separately; official server metadata plus all 140 raw pixel replies produced **142 independently rehashed response files**, and both SQLite integrity/count reconcilers passed. QA points are distributed across 14 US test regions including Alaska and Hawaii, but are **not verified insured coordinates** and **not the national raster census**. Continuous raw values range from **0 to 38,140** (not calibrated insured property scores). There were no network errors or explicit NoData replies in that verified sample.

**Classified actual observations (70):** very low 16, low 13, moderate 14, high 9, very high 3, **non-burnable 14, water 1**. The 15 masks are not falsely converted to low hazard; the source classifier reserves `UNKNOWN` for missing/not-covered raster data and distinguishes a valid zero continuous pixel. Both formats are source models, not wildfire event points, burn scars, loss claims, annual insurance probabilities or policy limits. Fire hazard is based substantially on LANDFIRE/FSim **landscape conditions as of 2020**; this is **WHP2023, revised 17 July 2024**, not an October 2026 forecast.

USDA original research archive publication/use/citation: https://doi.org/10.2737/RDS-2015-0047-4 ; USDA R&D source explanation: https://research.fs.usda.gov/firelab/products/dataandtools/wildfire-hazard-potential. USDA Research Data Archive states the government-funded research data may be used without added permissions or fees, with the requested Dillon 2023 citation; model uncertainty and intended spatial scale must be acknowledged. Confirm any *specific GeoPlatform service* redistribution terms before production.

### USDA official nationwide administrative summary ZIP — all four actual workbooks

Source: https://research.fs.usda.gov/sites/default/files/2024-07/firelab-whp2023_datasummaries.zip

[Official full source bulk/index run 39985452864](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39985452864) **SUCCESS**, artifact **12515791063**. Original ZIP **9,229,280 bytes**, **SHA-256 `1008b6d10c3635c6549dba3d1893381c2e6ed266c59b5fe8648cf5a6dea4b185`**. Source identity and landscape vintage preserved; every workbook original SHA is in the manifest.

| Source workbook and key | Real source rows read, accepted and temporarily indexed | Coverage and caveat |
|---|---:|---|
| `WHP2023_County_Summary.xlsx` / native 5-character `GEOID` | **3,143** | U.S. county-level publisher aggregate |
| `WHP2023_State_Summary.xlsx` / original `STATE_FIPS`, retaining 2 characters | **51** | 51 publisher state/D.C. codes |
| `WHP2023_ZipCode_Summary.xlsx` / original 5-character `ZIP` | **32,094** | 60 rows have no source WHP acreage; retained as `UNKNOWN_NO_AREA_VALUES` |
| `WHP2023_ManagementJurisdiction_Summary.xlsx` / original publisher category label | **16** | 15 management/ownership categories plus **one explicitly marked grand-total row**; no geographic/site IDs |
| **All original workbooks** | **35,304** | **0 rejected**, **0 duplicate source keys within their own grain** |

Original source values, names, all acreage-category fields, original worksheet row, publisher ZIP SHA, original XLSX SHA, product/version and uncertainty retained in normalized gzipped JSON lines and an indexed SQLite source-only store. The management workbook publishes areas rounded to ~1,000 acres: its acreage-category totals are checked within a **3,000-acre tolerance** rather than assuming impossible exact arithmetic. A publisher `Grand Total` is never counted as an additional physical jurisdiction in modeling.

Independent normalized **NDJSON.gz SHA-256 `efbdab10e2fb707512643fb35c3d9dacea6817eade38740561a98c8b6e6aee58`**. The `verify_lane_a_whp_index` check rehashes source ZIP + all four XLSX bytes + normalized gzip and verifies every 35,304 normalized source row, original source key and both SQLite tables; **SQL `PRAGMA quick_check=ok`**, 60 unknown-area rows, and exact source/normalized/indexed count reconciliation. Re-running unchanged input yields identical normalized gzip bytes.

This is a **complete import of the publisher's released 2023 administrative-area summary files**, **not** the national 270m GeoTIFF and **not** an all-facilities database. County/ZIP boundaries or polygon footprints are not present in these spreadsheets. State/county/ZIP aggregates must not be used as a substitute for exact facility-point raster values or insurance losses.

### Query/storage integration handoff (Lane A only)

- **Read-only index/query modules:** `facilityrisk/lane_a_source_query.py` supports exact native FEMA polygon and original USDA county/state/ZIP/management labels; no auto-matching. `facilityrisk/lane_a_geospatial.py` uses source RTree and original Esri polygon rings for reviewer-corroborated WGS84 coordinates; generalized polygons/boundary cases require extra review and sources outside fully enumerated windows are `UNKNOWN`, not no-risk.
- **Real index smoke tests:** `scripts/lane_a_source_query_smoke.py` on the complete USDA index verifies original ZIP `00029`, missing-area `10168`, county `06017`, state `06`, a management category and `Grand Total`; all are source grains, not buildings. `scripts/lane_a_fema_query_smoke.py` re-queries a real native FEMA polygon and the RTree and reconciles each enumerated window.
- **Coordinator-only handoff:** `scripts/lane_a_integration_handoff.py` emits a Lane A-scoped JSON manifest with original source grain, observed/staged and ephemeral indexed counts, national/vintage limitations, source errors, nulls and masks, and **`durable_production_rows=0`, `deployed_browser_rows=0`, `approved_site_links=0`**. Missing per-run sources are `NOT_PRESENT_IN_THIS_RUN` with unknown source totals, not zero publisher records. The coordinator must migrate these to their own private authenticated backend and source-health schema; Lane A does **not** edit shared UI or registry files.

## Reproduction

```bash
python -m unittest discover -s tests -p 'test_lane_a*.py' -v

# 2023 USDA official publisher ZIP, all four aggregate workbooks, temporary index
python -m scripts.lane_a_whp_official_summary --out-dir data/lane_a/whp_official_summary
python -m scripts.lane_a_whp_summaries_index --source data/lane_a/whp_official_summary/whp2023_official_summaries.zip --out-dir data/lane_a/whp_official_index
python -m scripts.verify_lane_a_whp_index --source data/lane_a/whp_official_summary/whp2023_official_summaries.zip --index-dir data/lane_a/whp_official_index
python -m scripts.lane_a_source_query_smoke --index data/lane_a/whp_official_index/whp2023-source-geographies.sqlite

# Official 2023 USDA continuous and classified raster geographic QA
python -m scripts.lane_a_whp_regions --out-dir data/lane_a/whp_regions
python -m scripts.lane_a_whp_classified --out-dir data/lane_a/whp_classified
python -m scripts.verify_lane_a_archive --root data/lane_a

# Authoritative FEMA polygons: exhaustive only within the six explicitly specified QA envelopes
python -m scripts.lane_a_nfhl_paged --out-dir data/lane_a/paged_windows --max-per-window 250 --batch-size 4
python -m scripts.lane_a_fema_query_smoke --directory data/lane_a/paged_windows

# Source-specific coordinator handoff, never a shared/UI deployment
python -m scripts.lane_a_integration_handoff --root data/lane_a --output data/lane_a/lane_a_integration_handoff.json
```

Separate, reproducible Actions workflows (each stores original replies, manifests and disposable SQLite in retained ZIP artifacts): [FEMA complete QA windows](../.github/workflows/lane-a-fema-windows.yml), [USDA live rasters](../.github/workflows/lane-a-wildfire-raster.yml), [USDA bulk administrative summaries](../.github/workflows/lane-a-usda-bulk.yml). The legacy combined [source QA workflow](../.github/workflows/validate-lane-a-sources.yml) retains optional access diagnostics. Note CI artifact expiration after 7 days: downloading or re-running is required before archival expiry; no current durable production deployment is implied.

## Unresolved acceptance gates — DO NOT MARK LANE A COMPLETE

1. **FEMA national completeness/availability:** Only six small envelopes exhaustively enumerated. Obtain lawful state/county/full nationwide authoritative maps or support reviewed on-demand site-coordinate queries with effective map study/LOMR dates. FEMA service periodically resets connections; the official MSC county ZIP returned HTTP 406 or reset. MassGIS is a separate older-dated optional publisher, not a replacement.
2. **USDA raster corpus completeness:** The original full-resolution national 270m GeoTIFF has **not** been downloaded/indexed. The national administrative summaries are complete at their *source aggregate* grain, and 70 original pixels per service prove official sample access, not a full raster census. Avoid false pixel-to-property translation.
3. **Insurance georeferencing:** No independently corroborated facility polygons, building/parcel footprints, campus locations or coverage assertions were supplied/approved. Coordinate evidence, accuracy, edge/overlap and changed-parcel review are required before site-specific use. All industries eligible; exclude none by FDA product status.
4. **Legal/temporal underwriting validation:** FEMA source-study effective dates and NFIP determinations, WHP spatial limitations/2020 fuels vintage, source redistribution and policy-specific loss/exposure denominators still need qualified review.
5. **Coordinator integration/deployment:** Zero Lane A records in authenticated persistent source storage, Source Health, facility pages or public GitHub Pages. Lane E alone owns crosswalk, schemas, tenant auth/monitoring, deployment, and merges; issue #39 covers durable hosting. A full end-to-end proof requires at least 25 separately reviewed real physical sites across industries with negative/missing evidence cases.

**Current conclusion:** Official USDA publisher summaries are **DOWNLOADED / NORMALIZED / INDEXED / CONTENT-VERIFIED** (source-only staging), USDA raster replies are **DOWNLOADED / STAGED / CONTENT-VERIFIED** (140 bounded point observations), and FEMA official polygons are **DOWNLOADED / NORMALIZED / INDEXED / CONTENT-VERIFIED within six tiny windows** with explicit simplification limits. **Nationwide hazard data readiness and production DEPLOYED are not satisfied. Draft PR remains unmerged.**
