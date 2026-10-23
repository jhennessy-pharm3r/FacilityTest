# Lane B private integration handoff — EPA environmental compliance

**Do not merge or mark deployed from this document.** Owner/coordinator for shared source service, authentication, review-only site association, production Source Health, durability and final merge: **Lane E** (Issue #73). Worker code and tests: `scripts/lane_b_epa/**`. No cross-program physical-site auto-merges, no insurance risk scores, no claims or loss attribution.

## Verified imported source cohorts (October 23, 2026)

| Source | Raw official source rows/features downloaded | Normalized/indexed staging records | Rejected/quarantined | Currently deployed |
| --- | ---: | ---: | ---: | ---: |
| ECHO exporter national ZIP | 3,229,311 | **3,208,008** | **21,303** without FRS `REGISTRY_ID` | **0** |
| RCRAInfo national ZIP, **six** source tables | 7,022,589 | **7,022,589** | 0 | **0** |
| TRI Basic U.S. 2020–2024, **five annual CSVs** | **392,878** | **392,878** | 0 | **0** |
| EPA **public** FRS RMP-program interest layer | **21,853** | **21,853** | 0 | **0** |
| Restricted full RMP and OCA plans | Not downloaded | Not authorized for unrestricted ingest | N/A | 0 |

RCRA `RCRA_FACILITIES.csv`: **1,630,839** rows and unique native handler identities; across six tables 7,022,589 are *not* seven million facilities. Exactly **1,522,387** facilities have usable official RCRA NAD83 point pairs; no independent parcel verification. Public RMP **21,853 program-interest identities** represent **21,567 distinct FRS registry IDs**, not independently verified properties.

ECHO **3,146,109** source-keyed coordinate pairs among 3,208,008 indexed records. The complete file contains 3,167,409 coordinate pairs, but **21,300** of these occur in 21,303 unkeyed rows. New schema v2 preserves the 21,303 rows and SHA-256 fingerprints in its quarantined raw-payload table. Do not assign a name/address-derived synthetic FRS key or represent these as clean/negative findings.

TRI 2024: **77,295** chemical-report records from **21,482** native TRIFDs; **68,567 Form R**, **8,728 Form A**, **76,574 pounds-unit reports**, **721 grams-unit reports**; 232 rows have EPA's PFAS source flag `YES`. These are reporting classifications, **not PFAS property-risk labels**. Across 2020–2024, there are **392,878** chemical-report rows, of which **388,944** use pounds and **3,934** use grams. Never add tons/grams/pounds or events/chemical reports to physical-site counts without normalized units and semantic checks.

## Authoritative joins and orphan handling

- **ECHO:** native FRS `REGISTRY_ID` is an identity within the federal regulatory catalog, not proof of a single property. Counts/penalty summaries within the wide ECHO Exporter are **summaries**, not independently verified individual violation event rows. Source uses `FAC_LAT`, `FAC_LONG` when reported.
- **RCRAInfo:** official documented link keys are **`ID_NUMBER` + `ACTIVITY_LOCATION`** (both required); report tables, evaluation/enforcement/violation/SNC history are separate. The complete official profile found **11,212 source rows** without an exact two-key match in `RCRA_FACILITIES.csv`: 1,677 enforcements, 5,501 evaluations, 1,519 NAICS, 2,515 violations, 0 SNC-history records. Those remain individually indexed/unlinked, **never force linked** using names or handler ID alone. Even an exact same-regulator match does not independently confirm a physical insured property.
- **TRI:** exact native `2. TRIFD` is the reporting facility identity; `36. DOC_CTRL_NUM` and the chemical/reporting year distinguish reports; `3. FRS ID` is a **candidate** external crosswalk, not automatic site mapping. Full five-year source provenance by year at `validation/tri_2020_2024.md`.
- **RMP:** public FRS programme association records support exact native `PGM_SYS_ID`, `REGISTRY_ID`, `OBJECTID` lookup. They do **not** include sensitive RMP/OCA plans, chemicals, release scenarios or losses. EPA access restrictions must be respected; authorized non-OCA releases would require a separate reviewed source.

## Immutable private bundle installation (coordinator only)

1. Retrieve each *matching* Actions run's original official ZIP/CSV (or RMP JSONL), compressed SQLite and manifest/QA artifact **before artifact expiration**. Verify original EPA archive SHA256 and source-index SHA256 match the same run. Do not mix cohorts/run manifests; `tri.sqlite` filenames must be separated by **year**.
2. Extract SQLite into a versioned, read-only private mount; preserve original EPA export in private immutable raw storage; prevent SQLite WAL. Do not include public index in GitHub Pages assets. Mount to the existing authenticated backend, **not** the writable insured workspace.
3. Validate with `scripts.lane_b_epa.read_index.source_status(db, manifest, source)` or `scripts.lane_b_epa.rmp_lookup.status(directory)`. These fail closed on missing/altered manifest/data, mismatched counts, unexpected private tables and nonintegral SQLite.
4. Query source-specific identities using `lookup(...source_id..., activity_location=...)`. Only users/tenants authenticated by the coordinator's existing server may access it. RCRA same-regulator handler coordinates are explicitly unverified source points; include raw authority/date/key and identity confidence in outputs.
5. **Until all production acceptance tests pass:** publish public Source Health as *staging only*, with distinct downloaded / normalized / indexed / verified / deployed counts. Use **0 DEPLOYED** for Lane B. Absence of an EPA event/report remains **UNASSESSED**, never low risk.
6. Exercise all-industry non-life-science samples, cross-program candidate matches/false positives, original source report dates, 10+ exact native program ID lookups, read-only validation and backup/rollback/restore on a controlled private host. Coordinator must attest count parity in live authenticated API and browser before promoting.

## Source-release gates, real tests, audit links

- ECHO full source/rejection/geo [run 39973733592](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39973733592), original archive SHA256 `116f6e53117b52f7891c6d2466d662f4ee5e29946b065fdb7b97eaf095615899`.
- RCRA v2 full read-only query/index/hash checks [run 39979755246](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39979755246), original SHA256 `babf48b1e2388b7f27cfc186cb1e9eb0ecfa26f53476fc81908712e41dfe09f3`. 3.16GB uncompressed indexed data / 740MB compressed temporary handoff artifact.
- TRI **all five** 2020–2024 official national years [run 39980692415](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39980692415), annual input and index hashes at `validation/tri_2020_2024.md`. Available only as short-lived **staging** artifacts.
- Public FRS RMP source with separate distinct-program/FRS identity counts, raw JSONL and indexed blob [run 39980425241](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39980425241); deterministic GeoPlatform ordering correction in a subsequent source-only rerun.
- Complete observed official field schemas, selected date years, jurisdictions, geobounds and nonmatching RCRA handler keys [full audit 39980093306](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39980093306). Official ECHO/RCRA ZIP response Last-Modified was **October 18, 2026**; HTTP retrieval time is not an event date.
- Source data guidance: [ECHO official downloads](https://echo.epa.gov/tools/data-downloads), [RCRAInfo data dictionary](https://echo.epa.gov/tools/data-downloads/rcrainfo-download-summary), [TRI Basic reporting/units/revisions](https://www.epa.gov/toxics-release-inventory-tri-program/tri-basic-data-files-calendar-years-1987-present), [restricted RMP access](https://www.epa.gov/rmp/accessing-rmp-data).

## Unresolved independent obligations

- Obtain/retain a durable authenticated source host (Lane E); temporary CI artifacts expire and are **not** persistent deployed indexes.
- Comprehensive public RMP plans/OCA cannot be treated as unrestricted bulk. Follow authorized, non-OCA disclosure and access review.
- Full historic TRI 1987–2019 not yet staged by the five-year workflow; source coverage is explicit.
- RCRA orphan two-key source identities and ECHO blank-registry rows require **manual source-data policy** for eventual review, never automatic physical-site assignment.
- Benchmark actual production search/pagination and geographic coverage on authenticated host, inspect dataset vintages and date sentinel values, implement refresh, backup, provenance reconciliations, real source-status publication and physical-property approval.
