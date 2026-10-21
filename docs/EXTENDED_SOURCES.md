# Additional source testing and integration (October 21, 2026)

## Implemented

- 14 source-family records representing 12 requested groups (NERIS/NFIRS and Europe/Canada split).
- `GET /api/source-extensions` returns priorities, official links, scope, test objectives, ingestion capability, last probe and candidate counts.
- The read-only GitHub Pages **Source health** page displays the extended source inventory; it cannot run backend probes or expose any private database.
- `python -m facilityrisk probe-extended-sources` checks official documentation HTTP status and LEAP OpenAPI shape without submitting any insured-facility identifiers. Outcomes **docs_reachable**, **schema_reachable**, **failed** or **not_tested** do **not** indicate usable normalized records, production credentials, licensing clearance or matched sites.
- `stage-incident-csv` imports *candidate proximity records* from an official, locally downloaded CSV when column mapping is explicitly supplied. Source keys supported: `nrc`, `csb`, `neris`, `nfirs`, `ucdp`, `phmsa`. Imports are idempotent and SHA-256 attributed; only **independently reviewed site coordinates** are eligible. Distances are not an assertion of facility involvement. Candidates never enter the evidence table automatically.
- Offline fixture regression tests exercise endpoint state distinctions, staging, deduplication, coordinate safeguards and mandatory reviewer rationale.
- The scheduled GitHub Actions source-probe workflow now includes extended source diagnostics, which **do not refresh private facility evidence**.

## Commands

```powershell
python -m facilityrisk probe-extended-sources
python -m facilityrisk stage-incident-csv "C:\\source-data\\incidents.csv" --source phmsa --id-column INCIDENT_ID --lat-column LATITUDE --lon-column LONGITUDE --date-column INCIDENT_DATE --title-column SUMMARY --url-column SOURCE_URL --precision-column GEO_PRECISION --radius-km 25
pytest -q
```

**Column names in the staging example are placeholders**: inspect the official file header and map its actual fields before execution. Official source files vary by year, jurisdiction and vintage. An event with no valid coordinates, no reviewed facility location or an unsuitable positional-accuracy field must not be treated as exact site exposure. The tool currently retains the positional-accuracy field *for analyst review* rather than enforcing a universal precision threshold. Choose radius consistent with that precision. For high-precision underwriting results, reject coarse event points and require investigation-level evidence.

## Verified vs unverified boundaries

This is a **source-evaluation and controlled-ingestion extension**, not a completed backtest or a fully automated integration of every source. Live records were not retrieved by the isolated development runtime. Source pages reviewed include UCDP (the API requires a token; CSV availability separately documented) and NERIS (public incident data is released on a lag). Modelled flood/wildfire raster overlays, serving-utility service-territory crosswalks, RSEI↔TRI joins, EU/NPRI/Irish facility crosswalks and incident-level attribution remain gated.

**No client database, workbook, API token, private facility address or personal information is committed to GitHub.**

## Next validation gates

1. Run the official source probe workflow on GitHub-hosted compute and inspect the `extended-source-report.json` artifact; document failures and endpoint drift, not just HTTP 200.
2. Download source-authorized files into a secured private workspace, confirm schema, terms, geography and date vintage.
3. Confirm site coordinates and identifiers with physical-site evidence before any link.
4. Stage proximity records; manually review occurrence, source geocoding precision and operator/site match with corroboration.
5. Assemble event-time and publication-time snapshots and a denominator of non-event sites; only then evaluate predictive lift against insurance-relevant outcomes.


## Incident staging scale and geography (October 2026)

The CSV staging adapter now uses a global one-degree spatial grid to prefilter candidate reviewed sites before calculating exact haversine distance. Unlike naive `events × all verified sites` scanning, the number of distance calculations is bounded by regional proximity; the output reports `geographic_distance_checks` and `verified_sites_tested`. Longitude wraps across the ±180-degree date line and near-polar neighborhoods expand the conservative window. The bounding grid does **not** perform attribution: all candidate records remain `pending` until an analyst documents operator/site identity, positional precision and independent event corroboration. Only a site coordinate explicitly approved for its **current latitude/longitude** participates; editing a site's coordinate invalidates a prior site-level review and blocks FEMA or incident screening until another reviewed record is saved.
