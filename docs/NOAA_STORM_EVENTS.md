# NOAA Storm Events bulk source ingestion — all industries

This source is **not a list of insurable properties** and must never be used to declare that a particular industrial, office, retail, medical, municipal, energy, warehouse or residential property was affected by a reported regional event.

## Source and refresh

- Publisher: NOAA National Centers for Environmental Information, Storm Events Details.
- Official index: https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/
- Source format: StormEvents_details-ftp_v1.0_dYYYY_cYYYYMMDD.csv.gz.
- The builder selects the newest published creation date (c) for every requested data year (d) and fails if a year is missing.
- Workflow: [NOAA Storm Events national bulk ingestion](../.github/workflows/build-noaa-storm-events.yml), weekly or manually dispatched; main-branch changes to the builder also trigger it.
- Initial staged years: **2023–2026**. The most recent year can be incomplete and is amended by the publisher. Earlier historical years remain outside this initial staging window, not zero-event years.
- Output: short-lived workflow artifact containing the unmodified official gzip archives, a normalized source-only storm-events.csv.gz and an independent JSON manifest.
- Provenance: original archive SHA256 for every annual partition, normalized SHA256, year, official URL, observed source row count, count of events with reported geographic coordinates, and ingestion timestamp.
- Public Pages receives **only aggregate** web/ingestion/noaa-storm-events.json with record counts, years, hashes and a link to the workflow. It does not receive storm-level records or any insured facility data.

The updater fails closed on invalid publisher host, missing/duplicate annual file, unexpected annual or event IDs, missing required columns, corrupted archives, missing annual cohorts or a normalized checksum/count mismatch. A successful HTTP request is not a substitute for these validations.

## Install in the authenticated private backend

Download the complete artifact from the workflow before expiration and extract it to a controlled, private data directory. Do **not** commit its data files.

~~~powershell
python -m facilityrisk import-noaa-storm-events data/noaa/storm-events.csv.gz --manifest data/noaa/storm-events-manifest.json
python -m facilityrisk serve --port 8765
~~~

The import is **explicit**, atomic per complete source-year partition, and idempotently replaces that partition only after checksum and row count checks. One missing year cannot silently be presented as successfully loaded.

Private API endpoints:

- GET /api/noaa/storm-events/status — years loaded, counts, source hashes and vintages.
- GET /api/noaa/storm-events?year=2025&state=MAINE&limit=50 — regional records, not property matches.
- GET /api/facilities/{facility_id}/noaa-storm-events?year=2025&radius_km=50 — contextual candidates only after current reviewed site coordinates. A changed point invalidates the earlier review and blocks this request. A missing point returns unassessed_location, not zero risk.

Even with a reviewed site coordinate, event reference points **are not reliable hazard footprints or claims**. Events lacking point positions remain searchable by state/date/type but never participate in the point-proximity query. A nearby point does not verify property damage, roof loss, flood-water elevation, operational interruption, coverage, an incurred claim, a payout, or severity at a particular site. Reported regional property damage is unverified with respect to an insured facility.

## Open production gates

1. Host validated normalized source archives and imported SQLite/Postgres records durably. GitHub Actions artifacts expire after 14 days and are not a long-term facility-risk database.
2. Backfill requested historical years with a versioned policy and guard against files whose coverage/categorical definitions change across decades.
3. Reconcile storm type/date/area with more appropriate physical hazard geometries—tracks, warning polygons, gauge readings, flood footprints and station-derived intensities—before interpreting site exposure.
4. Add provenance and change detection for publisher revisions and late reports.
5. Validate industry-neutral physical building/parcel/utility geocodes and source-event chronology. Review site-specific operational and financial losses separately, and preserve unknown rather than assigning zero.
6. Keep the public source-health panel split into connectivity, staged source artifact, private backend import, verified site association, and insurance outcome. Only later stages support evidence-rated underwriting; this pipeline does not establish them.

## Manual repro

~~~powershell
python scripts/build_noaa_storm_events.py --years 2023-2026
python -m pytest -q tests/test_noaa_storm_events.py tests/test_public_source_status.py
~~~

The core normalized dataset is event-scoped. NOAA event IDs remain independent of regulator source IDs (EPA FRS, FDA FEI, NPRI), asset IDs, or operator/parent IDs. No automatic facility merge or loss-derived insurance score is introduced.
