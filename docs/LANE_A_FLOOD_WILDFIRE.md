# Lane A — FEMA NFHL flood and official USDA wildfire hazard evidence

**Coordination:** [Issue #73](https://github.com/jhennessy-pharm3r/FacilityTest/issues/73); isolated branch \`ingest/fema-wildfire-lane-a-20261023\`; draft [PR #75](https://github.com/jhennessy-pharm3r/FacilityTest/pull/75). **No changes to other lanes, shared UI, canonical source-health or main.** All US facility and industry types are eligible for independently corroborated spatial review; neither source provides a global registry of insured sites.

## Official sources, identities, rights and limitations

1. **FEMA National Flood Hazard Layer (NFHL)** official MapServer flood hazard polygon layer 28, \`S_Fld_Haz_Ar\`: https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28. It returns native \`DFIRM_ID\`, \`VERSION_ID\`, \`FLD_AR_ID\`, \`FLD_ZONE\`, \`ZONE_SUBTY\`, \`SFHA_TF\`, \`SOURCE_CIT\` and service-scoped \`OBJECTID\`; original ArcGIS polygon geometry is retained. The composite \`DFIRM_ID + FLD_AR_ID\` is a source record key when supplied, **not** a physical property ID. Dates/vintage are local to underlying flood maps, not a single national epoch. Check source records and FEMA distribution/terms before publishing redistributed data.
2. **USDA Forest Service / Rocky Mountain Research Station Wildfire Hazard Potential (WHP) 2023**, official USFS raster distributed via federal [GeoPlatform ImageServer](https://imagery.geoplatform.gov/iipp/rest/services/Fire_Aviation/USFS_EDW_RMRS_WildfireHazardPotentialContinuous/ImageServer). A modeled continuous **270-meter raster**, not a record of a fire, policy loss, building ignition probability, wildfire perimeter, or insurance pricing. Per-coordinate query is an ArcGIS \`ImageServer/identify\` pixel lookup, not \`MapServer/query\`. There is no native individual pixel event ID; a coordinate-based observation key is generated **only** for local reproducibility. [USFS publisher documentation](https://research.fs.usda.gov/firelab/products/dataandtools/wildfire-hazard-potential). Record vintage **2023**.
3. **Optional MassGIS FEMA-derived 2025 SFHA subset:** [MassGIS documentation](https://www.mass.gov/info-details/massgis-data-fema-national-flood-hazard-layer). The attempted ArcGIS republication is geographically narrower, may omit non-SFHA flood areas, and returned \`400 Item does not exist or is inaccessible\`. It is explicitly **not a replacement** for current national NFHL and has **zero validated records** in this workflow.

Original responses are staged separately from normalized source observations. SHA-256 refers to the **actual received response bytes**, not a published national archive hash. Before downstream publication, the coordinator must independently verify FEMA and USFS attribution, licensing, replication and refresh conditions.

## Observed live run — 2026-10-23

**Content-level evidence:** [GitHub Actions run 39974657234](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39974657234), artifact \`lane-a-fema-usfs-massgis-source-qa\`, ID **12509934075**. Unit fixtures passed (**21 tests** on that revision), and [repository CI 39974668226](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39974668226) passed. The official-source workflow **correctly failed its full-completion gate** because FEMA access was intermittent and the separate MassGIS source was inaccessible. Subsequent commits add additional archive/manifest regression verification; inspect their own CI before accepting the current branch.

| Stage / observed count | FEMA NFHL polygon QA | USDA WHP 2023 raster QA |
| --- | ---: | ---: |
| Geographic probes attempted | 3 bounding boxes | 3 points |
| Successful geographic probes | 2 | 3 |
| Original source records returned in successful probes | **12** | **3 pixels** |
| Accepted and staged records | **12** | **3** |
| Rejected source records | **0 in successful responses** | **0** |
| Distinct source keys / point observations indexed in source-only SQLite | **12** | **3** |
| Nationwide dataset downloaded | **NO** | **NO** |
| Corroborated physical facility matches | **0** | **0** |
| Durable backend / live app deployment | **0** | **0** |

**FEMA bounding boxes:** New Orleans **10** accepted polygons (query response explicitly flagged \`exceededTransferLimit=true\`, so incomplete, not exhaustive; raw SHA-256 \`0e4bad104fec007642d48087920280183686081766bd02497658d5dcf7a4e67f\`); Houston **network connection reset** (no count inferred); Sacramento **2** polygons (raw SHA-256 \`dd8a056f68e9495a65e989ab22817ce9981e60f6caca512ebaf8fe97d29eccb3\`). The retrieved polygons include both \`AE\` and \`X\` flood zones. A returned polygon is not intrinsically high risk. Real source native identifier examples: \`22071C / 22071C_6650\` and \`06067C / 06067C_1223\`.

**USFS point probes:** Tahoe WHP value **0** (raw SHA-256 \`754d67da1e156b14a1a9de4945dcbec4e0461f05c1b617a9f3e2357771b9be9c\`), Boise **231** (\`ebb84747dd1948cfc1c7b383d30004d320d04da9a29505bde6924839cb5370df\`), Denver **4155** (\`0d765f5b8827e60484b28e4f3a4d5da7a2cd20c3fe511c6493e0593b47a852da\`). These are raw continuous WHP raster values, **not normalized scores**, and no claim of insured property proximity is made.

**Separate FEMA attribute-only diagnostic:** Same run successfully returned **2 response observations (1 per GET/POST transport)** to the *same* FEMA source key (\`22071C / 22071C_40561\`), 0 rejected, 2 indexed query receipts but **1 distinct source ID**. No geometry is returned by that diagnostic. **Do not add its 2 receipts to the 12 geometric polygons and call that 14 unique flood zones or 14 facilities**. This also proves the service was intermittently reachable and that a failed method is not proof of an empty official dataset.

**Earlier metadata confirmation:** [run 39974018063](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39974018063) fetched true FEMA flood polygon layer metadata including \`geometryType=esriGeometryPolygon\`, native ID field descriptions, original SHA-256 \`6605b8063afefa8f44f604b44a920b2c5645ded739ec9558b24188e3bdedb358\`. The same request failed intermittently in subsequent runs; success does not guarantee query availability.

All reported accepted/rejected/indexed figures are **per successfully downloaded *samples***, not national counts; blocked queries have **unknown** source row totals, not zero. Source-only SQLite in GitHub Actions is disposable staging; the ZIP artifact has a retention period, not a production serving guarantee.

## Reproducible workflows

**Run unit tests:**

\`\`\`bash
python -m unittest discover -s tests -p 'test_lane_a*.py' -v
\`\`\`

**Live geospatial source QA** (non-exhaustive government geographic points and bounds; no verified facilities):

\`\`\`bash
python scripts/validate_lane_a_sources.py --output-dir data/lane_a/live_validation
python -m scripts.diagnose_lane_a_fema_access --output-dir data/lane_a/fema_transport
python -m scripts.validate_lane_a_massgis --output-dir data/lane_a/massgis_2025
python -m scripts.verify_lane_a_archive --root data/lane_a
\`\`\`

The separate diagnostics deliberately return nonzero if official service cannot provide the required source content. Capture/verify the manifests and retained original JSON, not just HTTP response code. The **branch-scoped GitHub Actions workflow** \`.github/workflows/validate-lane-a-sources.yml\` provides the repeatable cloud-hosted run, strict regression suite, original responses and SQLite artifacts. Its source access job can be red while archive verification and repository unit-test steps pass; do not promote incomplete source status to VERIFIED.

**Per-site sampling requires actual georeference evidence:**

\`\`\`json
[
  {
    "site_reference": "reviewed_property_1",
    "longitude": -119.2,
    "latitude": 38.1,
    "coordinates_corroborated": true,
    "coordinate_evidence": "surveyor-confirmed parcel centroid, reviewed YYYY-MM-DD"
  }
]
\`\`\`

\`\`\`bash
python -m facilityrisk.lane_a_hazards --points points.json --output data/lane_a/site_samples.json
\`\`\`

The example is a **schema illustration only**, not a corroborated facility or a verified point; do not run it as real-site validation without the stated evidence. Treat parcel, building and campus/tenant boundaries separately. Preserve exact location source/datum and map effective date. Do not commit private property coordinates, insured identities, or site-level observations to the public branch.

## Gates before coordinator merge or production

- Prove repeatable FEMA geometry retrieval, **untruncated** paging or official full snapshot, authoritative \`SOURCE_CIT\`/effective dates, geometry validity/topology, CRS and boundaries. Current bbox windows are capped and one query was interrupted; no nationwide count exists.
- Validate geographic and risk classification coverage (no-data, edges, overlapping flood zones, WHP pixel no-data/mask and geography), not only response schemas. Restrict site point use to independently corroborated coordinates.
- Record actual accepted/rejected counts and original checksums for each completed download. Preserve native FEMA IDs and raw WHP pixel responses without inventing site IDs, property-loss outcomes or policy coverage.
- Verify original source attribution/redistribution terms; coordinate with Lane E for durable private indexing, shared manifest/Source Health/UI, rollback and refresh monitoring. Only coordinator may merge; GitHub Pages cannot serve a national private geospatial database.
- Carry an **unknown/unassessed** state where either source is absent, inaccessible, outdated or not geographically applicable. Do not call missing evidence “no risk.”

**Current honest state:** real federal samples have been **DOWNLOADED and STAGED in ephemeral source-only CI indexes**, and isolated regression QA is passing. **Nationwide VERIFIED, durable INDEXED and DEPLOYED remain unmet.** The draft PR remains unmerged.
