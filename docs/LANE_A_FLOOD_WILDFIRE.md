# Lane A — official flood and wildfire hazard acquisition

Ownership: issue #73, branch `ingest/fema-wildfire-lane-a-20261023`. No shared registry, app UI, or other source lane changes. All US site/industry types are eligible; only **corroborated** WGS84 coordinates are accepted. Coordinates alone do not establish the legal insured property boundary.

## Authoritative inputs

- **FEMA National Flood Hazard Layer**, official ArcGIS REST NFHL MapServer polygon layer **28**, `S_Fld_Haz_Ar`: https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28 . Requested source fields include `OBJECTID`, `DFIRM_ID`, `FLD_ZONE`, `ZONE_SUBTY`, `SFHA_TF`, `SOURCE_CIT`; original source attributes retained. Source vintage varies by map community / revision; do not assign a single uniform nationwide date. Point-in-polygon server-side query with explicit EPSG:4326.
- **USDA Forest Service, Rocky Mountain Research Station, Wildfire Hazard Potential 2023**, official ArcGIS REST service: https://apps.fs.usda.gov/arcx/rest/services/RDW_Wildfire/RMRS_WildfireHazardPotential_2023/MapServer . Uses ArcGIS **identify**, not feature `query`, because WHP is a modeled raster. Published WHP 2023 is based on wildfire simulations/fuels and is *not* the likelihood of a specific insured loss, insurance premium or active wildfire perimeter. Research overview: https://research.fs.usda.gov/firelab/products/dataandtools/wildfire-hazard-potential .

Both sources require their actual attribution, status and source vintage in downstream displays. Check FEMA and USDA access/redistribution policies before distributing any bulk derivative. Do not claim a nationwide download based on sampling points.

## Reproduction

Create `points.json` locally, using e.g. `[{"site_reference":"reviewed_property_1","longitude":-119.2,"latitude":38.1,"coordinates_corroborated":true}]`. The value must refer to independently checked site coordinates, not a generated street centroid.

```bash
python -m unittest discover -s tests -p 'test_lane_a_hazards.py' -v
python -m facilityrisk.lane_a_hazards --points points.json --output lane_a_manifest.json
```

A nonzero exit code means at least one source retrieval failed. The manifest retains service URL, SHA256 of **actual received JSON**, raw and accepted counts, coordinate, original source attributes, source observation and explicit coverage unknown state. Keep private site identifiers/coordinates out of public git history.

## Validation ledger at PR creation

| Stage | FEMA | USFS |
| --- | --- | --- |
| Metadata/source discovery | official endpoints identified | official WHP 2023 documentation and endpoint identified |
| Remote HTTP access from current execution environment | **blocked**: FEMA URL inaccessible from web tool | **blocked**: map service returned HTTP 403 from web tool |
| Actual downloaded source data | **0 verified rows** | **0 verified rows** |
| Normalized rows | **0 verified rows** | **0 verified rows** |
| Indexed durable records | **0** | **0** |
| Deployed live source evidence | **NOT VERIFIED** | **NOT VERIFIED** |

These zeros are **not national counts** and **not absence of hazard**; they mean no validated ingest occurred. Unit tests exercise deterministic mocked fixtures, not real source observations. Confirm live endpoint schemas/fields, genuine download and checksum, nonempty geographically varied test cases, no-data scenarios, per-source terms, record IDs, effective dates, and service paging/limits in a network-enabled CI run before raising state beyond `PROBED`. For public app integration, the coordinator owns persistent storage, health ledger, and Source Health UI.

## QA and limitations

- One FEMA intersected polygon or USFS raster cell does not equal one physical property, nor an insurance claim.
- Empty intersection or missing raster coverage => **unknown**, never automatically safe/minimal risk.
- FEMA polygon `OBJECTID` is service-scoped and may change across service reloads; preserve `DFIRM_ID` and original attributes for provenance, never use it as a global canonical facility ID.
- WHP `layerId` + service vintage identifies raster product at queried coordinates; it is **not** a unique physical wildfire occurrence ID.
- CRS, no-data, overlapping flood map boundaries and classification resolution all need independent QA against authoritative map services.
- Never infer building footprint, contents valuation, flood depth, flood policy status or actual event from either source.
