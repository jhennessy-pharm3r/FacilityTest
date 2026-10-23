# NOAA IncidentNews: selected oil and chemical response events

Official publisher: NOAA Office of Response and Restoration (OR&R).
Official CSV: https://incidentnews.noaa.gov/raw/incidents.csv
Documentation: https://incidentnews.noaa.gov/raw/index

## What this source can and cannot tell insurers

The CSV contains a selected set of oil, chemical and other incidents for which NOAA provided scientific response support. It is not an exhaustive USCG National Response Center spill notification registry or an inventory of all properties. Case data includes the incident ID, response notification date, case name, textual location, approximate point coordinates (when reported), Oil/Chemical/Other type, spill-related tags, commodity, maximum POTENTIAL release in gallons, response countermeasure flags and a narrative.

**Maximum potential release volume is NOT actual measured released volume or insured property damage.** Point proximity is not a hazard footprint, a loss, a confirmed facility operator or a policy payout. Missing records mean unknown, not low risk. Some pre-1985 dates are dates from third-party sources.

## Source ingestion and verification

A weekly GitHub Actions workflow downloads the official CSV from the publisher host, bounds source bytes, validates the full schema, source IDs and data types, calculates original and normalized SHA256 hashes, records retrieval UTC and row counts, and archives raw and normalized snapshots plus a JSON manifest. The workflow builds an independently indexed source-only SQLite and validates indexed row counts by threat, source SHA256 and SQLite integrity. Incomplete/invalid sources fail closed. GitHub Actions artifacts are short lived and are not production databases.

Only sanitized aggregate counts and provenance are allowed on public GitHub Pages. The separate Source Health ledger reports whether source records have actually been staged. HTTP reachability alone never establishes ingestion. Individual NOAA incident descriptions and source coordinates are not uploaded into Pages.

## Private service

Copy matching successful source-only SQLite and manifest to a controlled private source-index mount; never overwrite an insured research database. Optional server settings:

    FACILITY_RISK_INCIDENTNEWS_INDEX_PATH=/app/source-index/incidentnews-source-only.sqlite
    FACILITY_RISK_INCIDENTNEWS_INDEX_MANIFEST=/app/source-index/incidentnews-manifest.json

On an independent private source-only database, explicit import:

    python -m facilityrisk import-noaa-incidentnews data/incidentnews/incidents.csv.gz --manifest data/incidentnews/manifest.json

Private API routes: GET /api/source-indices/status; GET /api/noaa/incidentnews/status; GET /api/noaa/incidentnews with q, threat, from_date, to_date and pagination; GET /api/facilities/{facility_id}/noaa-incidentnews with a bounded proximity radius, available only after current independent property-point review.

The private source catalog is read-only, independently validated and not merged with insured property, EPA FRS, FDA FEI, NPRI or company owner identities. Cross-source links require a separate auditable decision, and no claims, financial outcomes or risk scores are inferred.

## Unfinished all-industry source coverage

Broader USCG NRC reported releases, CSB investigation findings, PHMSA hazmat transport, EPA ECHO/RCRA/TRI, NFIRS/NERIS fire reports, site-level FEMA flood, wildfire, USGS seismic, wind, utility outage, supplier and interruption datasets need separately validated ingestion. Source-specific limits and geographic/period coverage must remain visible in the app.
