# Universal Facility Discovery and Insurance Coverage (v0.7)

**Scope: any industry, any jurisdiction.** The app must not restrict facility eligibility to FDA, pharmaceutical/device manufacturers, environmental reporters, or the initial research cases.

## Implemented in this build

- Backend source-identity candidate registry `universal_sites` and `universal_source_records`; import sources without inferring that same-name records represent one physical facility.
- SQLite FTS5 indexed search, pagination, source, industry and country filters.
- Import official CSV (mapped schema) and GeoJSONSeq points, including externally authorized Overture Places exports. Requires downloading through publisher's allowed distribution method first; *no Overture or EPA national dataset has been imported merely by adding the importer*.
- Import existing public FDA / Canada / Ireland catalogs into the private universal registry.
- All newly discovered records remain site candidates with unknown property identity, insurance protection and risk; coordinates are source-reported, not parcel-verified.
- Manual independent two-person link routine with original source evidence URL, rationale and audit history; do not automatically combine records from disparate sources.
- Optional promotion to the existing authenticated private research workspace.
- Structured, public-reference property, environmental, operational-interruption, utility, contingent-BI, and parametric coverage taxonomy. Every coverage remains **unknown** without reviewing an actual contract.

## Private API

- `GET /api/universal-facilities/stats`
- `GET /api/universal-facilities?q=&country=&industry=&source=&limit=50&offset=0`
- `GET /api/universal-facilities/{site_id}`
- `POST /api/universal-facilities/{site_id}/track` (private writes and authentication required)
- `GET /api/insurance/coverage-types`
- `GET /api/insurance/screen?hazard=flood,wildfire&utility_dependent=true`

No automated approval endpoint is exposed for cross-source merges. The two-person linkage routine must be invoked only within controlled, separately authorized private reviewer workflows. Do not bypass the existing user/auth gates with a public route.

## Ingestion

The existing public catalogs can be added to the private registry:

```sh
python scripts/import_universal.py web/registry/catalog.json --format published-catalog
python scripts/import_universal.py web/registry/ireland-leap.json --format published-catalog
python scripts/import_universal.py web/registry/canada-npri.json --format published-catalog
```

For an authorized EPA FRS CSV download inspect the actual file header before mapping. Example placeholders:

```sh
python scripts/import_universal.py /private/frs.csv --format csv --source EPA_FRS \
 --source-url https://www.epa.gov/frs/frs-data-download-options --vintage 2026 \
 --field source_identifier=REGISTRY_ID --field name=PRIMARY_NAME \
 --field address=LOCATION_ADDRESS --field city=CITY_NAME --field country=COUNTRY_NAME
```

Column names above are *examples*: confirm the actual source export schema and country-code normalization rather than assuming this exact set works. Country filtering expects ISO country codes; raw labels may need conversion during pre-processing.

For an authorized GeoJSONSeq point export of Overture Maps Places:

```sh
python scripts/import_universal.py /private/places.geojsonseq --format geojsonseq \
 --source OVERTURE --source-url https://docs.overturemaps.org/ --vintage 2026-10
```

**Important operational limit:** SQLite will handle many records better than browser-loaded JSON, but this implementation has not yet been benchmarked on a million real facilities. Split extremely large sources into batches/partitions, monitor import time, and consider PostgreSQL/PostGIS for production.

## Evidence and risk boundaries

- A registry record is a *source identity*, not independently verified physical insurance property, current operation, incident, regulatory violation or claim.
- An Overture place can be a shop, branch, campus or non-building point; do not promote it to verified physical site without supporting evidence.
- An EPA/OSHA registration is not proof of loss or heightened risk.
- Hazard proximity, a contract-product definition and an actual insured contract are distinct concepts.
- No actuarially calibrated claims frequency or price is available. Never interpret unknown records as low-risk.
- Never publish the private registry, proprietary insurance policies, or client exposures on GitHub Pages.

## Next validation gates

1. Download and reconcile the official EPA FRS bulk export with source totals and schema checks.
2. Download geographically partitioned Overture Places exports under applicable terms; measure duplicates, category value and match precision.
3. Add an independently reviewed facility-to-building and ownership model and cross-agency mapping QA.
4. Move the public preview discovery tab to a hosted scalable service with access control; GitHub Pages remains static and does not execute Python.
5. Batch-screen verified location candidates against catastrophe layers, and validate utility dependencies and event outcomes.
6. Add client-specific policy documents and supervised coverage reviews only after tenant-scoped permissions and production security.
