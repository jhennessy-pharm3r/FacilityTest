# Public EPA FRS–RMP program-interest registry — matching current source bundle

**Scope:** public FRS programme interests only, **not** RMP plans, chemicals, release scenarios, accidents or offsite-consequence analysis (restricted source handling required). Official public EPA GeoPlatform [FRS_INTERESTS_RMP feature layer](https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/FRS_INTERESTS_RMP/FeatureServer/0/query).

**Latest complete official source run:** [39981171808](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39981171808), Oct 23, 2026 UTC `2026-10-23T15:49:08.852308+00:00`.

| Actual source-level measure | Verified value |
| --- | ---: |
| Official public layer feature/object IDs reported and completely downloaded | 21,853 |
| Original public records normalized | 21,853 |
| Separate source-only SQLite indexed | 21,853 |
| Rejected records | 0 |
| Duplicate or missing `OBJECTID` in full paging | 0 |
| Missing `REGISTRY_ID` | 0 |
| Missing `PGM_SYS_ID` | 0 |
| Distinct native programme `PGM_SYS_ID` | 21,853 |
| Distinct FRS registry `REGISTRY_ID` | 21,567 |
| Source-records with valid reported coordinate pairs | 21,853 |
| Publisher `ACTIVE_STATUS=ACTIVE` | 21,834 |
| Missing source active status | 19 |
| Latitude min/max | -14.270809 / 70.490861 |
| Longitude min/max | -170.686791 / 145.741235 |
| SQLite integrity / exact program-ID lookup | PASS |
| **Production deployed records** | **0** |

Current **matching run** raw JSONL SHA-256: `c86acb52b94cac31b0e3c725591e345743c0193261b7f22ac03a18339c162d76`.  
Current matching SQLite index SHA-256: `93ad2b930424758780a5603f059019b1b1325808a4241bbaf415fc2280d91198`, SQLite bytes **30,846,976**.

The initial public FRS source run [39971992625](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39971992625) produced a different canonical JSONL SHA (`a2ae6195b1e20096b8b21faed57e4ed840fcc753f6775624aadb292e0d3a4272`) before stable object-ID response ordering was enforced; **do not mix old/new SHA-provenanced bundles**. The complete source count is equal in both checked snapshots but byte-level snapshots are independent. All original source JSONL, matching SQLite and QA manifests must be installed together.

[Separate fresh-run public RMP real source-only private installation and native program lookup 39999641452](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39999641452) **PASSED**. It independently downloaded the matching publisher records/index/manifest, verified all hashes and programme counts and then removed temporary raw source/index bytes. Read-only public lookup `python -m scripts.lane_b_epa.rmp_lookup --directory /app/source-index/epa-rmp-public-20261023 --program-id <exact-official-PGM_SYS_ID>`; full install `python -m scripts.lane_b_epa.install_auxiliary rmp-public ...` documented in [integration handoff](../INTEGRATION_RELEASE.md).

These records are source programme interests, **not verified insured properties, loss claims, verified actual release risk, or complete RMP plans**. Property matching remains unapproved; no API or production service deployed.
