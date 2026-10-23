# Official EPA ECHO–TRI 2024 exact regulator-ID candidate audit

**2026-10-23, full national publisher archives, not fixture data.** Independent [Actions run 39987583584](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39987583584) **SUCCESS** with original official ECHO and 2024 TRI files downloaded from earlier validated source producer artifacts (no external/undocumented mirrors). Exact original regulator archive SHA256:
- ECHO: `116f6e53117b52f7891c6d2466d662f4ee5e29946b065fdb7b97eaf095615899`
- TRI 2024: `06dfa3a67bb4c5bd38d9e9f0f7b8bff10b95254a63169423632d7f6f251e1506`

| Official source-identity measure | Observed count |
| --- | ---: |
| ECHO complete exporter raw rows | 3,229,311 |
| ECHO accepted unique `REGISTRY_ID` keys | 3,208,008 |
| ECHO records missing `REGISTRY_ID` | 21,303 |
| ECHO repeated keyed FRS registry IDs | 0 |
| TRI 2024 per-chemical source forms | 77,295 |
| TRI native distinct `TRIFD` reporting facility IDs | 21,482 |
| TRI chemical forms whose original `3. FRS ID` exactly appears in ECHO | **75,336** |
| TRI chemical forms whose reported FRS ID absent from ECHO exporter | **979** |
| TRI chemical forms with **no** reported FRS ID | **980** |
| Distinct FRS IDs reported among TRI forms | 20,916 |
| Distinct TRI FRS IDs found in ECHO | 20,782 |
| Distinct TRI FRS IDs absent from ECHO | 134 |
| Distinct TRI native TRIFDs with at least one exact FRS-key candidate | 20,817 |
| Distinct TRI native TRIFDs with at least one missing FRS field | 529 |
| **Independently verified physical properties, sites or insured claims** | **0** |
| **Production deployed records in authenticated source index** | **0** |

**Reconciliation:** 75,336 + 979 + 980 = **77,295** full chemical-report records. Exactly matching native registry identifiers show a **review-only candidate program association**, not an independently confirmed plant/building/parcel; no names, coordinates, operators or historical date coincidences were used to manufacture joins. An FRS key absent from current ECHO could be due to coverage, source timing or differing program identity, **not proof of nonexistence or low environmental risk**.

Reproduce with `python -m scripts.lane_b_epa.crosswalk_audit --echo-zip /private/official-echo.zip --tri-csv /private/tri_2024_US.csv --year 2024 --output /private/tri_echo_candidates.json`. Official source SHA256 must be independently verified and no private insured records included. The coordinator alone may review cross-source candidates, physical property correspondence and Source Health.
