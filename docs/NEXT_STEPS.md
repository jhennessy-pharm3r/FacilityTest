# Facility Risk Intelligence — verified status and current roadmap

**As of:** October 22, 2026.
**Universal scope:** All facility types and industries; life sciences are one optional vertical. Sources cover only the places each publisher reports. Regulatory identities, place observations and insured physical properties are not interchangeable.

## Verified implementation

| Component | Verified result | Deployment gap |
| --- | --- | --- |
| Public GitHub Pages | Static preview, 3 sourced retrospective research cases and 50,368 FDA/Canadian/Irish source identities; browser smoke passing | Not universal live search or an insured-client portal |
| National EPA FRS | Complete official export: 5,354,716 valid records, 7,158 rejected; source provenance SHA256 | National registry excludes many commercial premises |
| National indexed backend | 5,354,716 identities loaded and indexed; 11,174 search matches for warehouse; SQLite quick_check OK; 4.56 GB database; Actions run 39813812469 | An expiring Actions artifact, not running in a durable authenticated production host |
| Overture pilot | 101,979 place observations across Halifax, Cleveland, Dublin, Singapore; 99,251 categorized in 1,364 categories; database integrity passed | Small sample areas, unverified property identity, no global census |
| Facility identity and research | Separate cross-source observations, review gates and evidence-linked case reports | Building/campus and company parent reconciliation pending |
| Natural hazards / incidents | FEMA, NOAA, USGS, WRI and EPA connectors / review flows | Not screened for all discovered sites; no claim or property-impact validation |
| Insurance coverage reference | Property, flood, windstorm, earthquake, wildfire, standard/contingent BI, utility, extra expense, spoilage, non-damage BI and parametric types | Reference only, no insured policy terms |
| Insurance workbench | User-selected cross-industry exposure scenarios, utility/supplier dependencies, review topics, illustrative downtime cost, JSON export | No live geohazard crosswalk; user-entered policy statuses are not verified |
| Model scoring | No published overall actuarial risk score | Claims outcomes and insured denominators have not been validated |

**Primary distinction:** A source-identity count is not a physical property count. A nearby storm or chemical report is not an insured loss. A policy product being offered is not proof of insured coverage. Unassessed does not mean low risk.

## Intended underwriting workflow

**Discover facility → resolve property/parent/operator → assess verified location and perils → map operations and dependencies → inspect insured policies and parametric alternatives → distinguish verified gaps from unknowns → document financial loss scenarios → export sourced assessment.**

The public Pages workbench supports only scenario and policy-review preparation. It never measures actual property hazard, validates a contract, computes an insured claim or prices risk.

## P0 — universal backend for all industries

1. Move the 4.56 GB validated EPA indexed database out of time-limited Actions artifacts into durable secured storage with reliable backup, refresh, published vintage, source and checksum metadata. Do not commit it to Pages.
2. Deploy the indexed facility search as an authenticated private endpoint, test names/source IDs/NAICS/industry/country/pagination against >=5 million identities, and report actual p50/p95 response times. Optimize FTS and prefix lookups; evaluate Postgres/PostGIS if necessary.
3. Ingest and reconcile all source families: EPA FRS, FDA drug/device, Ireland EPA, Canada NPRI, and permitted Overture subsets. Keep independent source records and review all possible cross-regulator equivalences before merging.
4. Add physical site vs building vs campus/parcel; operator and ultimate parent; country-code normalization; geocoder and coordinate provenance; historical relocations and operator changes; duplicate evidence and false-positive QA.
5. Expand Overture geographic coverage legally and gradually. Overture Places includes retail, restaurants and other points that cannot automatically be counted as verified insurable structures.
6. Implement tenant isolation, permissions, backup, access logs and rate limits before client data and policy documents can be hosted.

**Gate:** Every identified facility appears as searchable, even without adverse events, losses, inspections or FDA registration. All unscreened properties display unknown/unassessed.

## P1 — measured hazards, operations, BI and policy verification

1. For independently reviewed property geometries, integrate FEMA NFHL flood, NOAA wind/storm tracks, USGS seismic hazard, wildfire potential, heat/water stress, and jurisdiction-appropriate Canadian/European datasets. Store units, source URL, model vintage, resolution, location-review revision and uncertainty. Stale points invalidate old overlays.
2. Ingest reviewed environmental/industrial incident evidence from EPA ECHO, RCRA, TRI, USCG NRC, CSB, PHMSA, OSHA and other regulators without confusing geographic proximity with an actual property loss.
3. Build operational dependency tables: serving utility (if known), outage exposure, backup power and water, temperature control, suppliers, transport access, restoration time and alternative production capacity. EIA-861 measures utility-level reliability, not a verified specific-facility outage.
4. Add authenticated policy records and location schedules, property/BI limits, catastrophe sublimits, attachments, deductibles, waiting periods, utility/CBI endorsements, coverage territories, exclusions and effective/expiry dates.
5. Parametric contract details: index provider, point/polygon/measurement, threshold, payout ladder, local insurable interest/loss tests when applicable and explicit basis risk.
6. Set policy status to reported, unknown, conditional, document-reviewed covered or document-reviewed excluded. Only independently reviewed, cited policy terms may support verified status.
7. Keep physical hazard, operational vulnerability, coverage quality and residual financial exposure as separate dimensions; do not conflate hazard intensity with insured loss or payout.

**Gate:** At least 25 real mixed-sector facilities independently geocoded and evaluated with data vintage, source and reviewer. Verified exclusions are distinguishable from unanswered questions.

## P2 — insurer-ready reporting and historical validation

1. Company and parent portfolio view spanning all facilities; industry and geography filters; maps and concentration exposures; property vs insured location distinctions.
2. Multi-property risk profiles and client-ready PDFs/CSV with linked evidence, insurance review status, caveats, source dates and analyst approvals.
3. A properly designed longitudinal event/non-event cohort with verified pre-event publication dates and economic/insurance outcomes, including adverse selection and denominator controls. Avoid double-counting SEC disclosures.
4. Only introduce a calibrated numerical rating when independently verified exposures, losses and denominators justify it; otherwise remain unranked.

## Product quality and public Pages

- Pages source list is a limited public registry. The 5.35-million EPA database and Overture pilot are indexed Actions artifacts and are **not** available through the static Pages search bar.
- Do not type sensitive client policy documents or proprietary data into a public site; the private authenticated backend is the correct location.
- The interactive workbench shows analyst-selected possibilities, not parcel-specific verified hazards. Policy fields in browser memory remain user-entered and explicitly unverified.
- CI and local Playwright browser tests should be complemented with post-deployment checks against the actual public Pages URL, including desktop/mobile, risk input, coverage matrix, export and console errors.

## Primary tracked work

- Issue #3: universal facility identity and production-grade registry.
- Issue #4: verified catastrophe/incident and outcome evidence.

**This file is the authoritative current backlog. Earlier development-stage notes are historical and must not overrule live source-validation results.**

## Policy-review implementation gate

The private insurance policy metadata and coverage-term review module now supports independently authenticated reviewer/approver decisions, document SHA-256 references and versioned invalidation of earlier approval after coverage edits. The facility-level crosswalk connects **current, independently reviewed** hazard screenings to relevant **document-reviewed** terms only. It does not certify policy authenticity, coverage applicability, or claim payment. The public Pages version has no policy-storage access. Production deployment, multi-tenant security, client-provided contracts, real coverage review, national index hosting, geospatial production QA, and 25 independent facility case studies are still outstanding; do not claim otherwise.

Private viewer navigation now includes a **Verified policy review** workspace for reviewing per-facility policy metadata, terms, verified point screening crosswalks, and independent reviewer approval decisions. This is not available in public Pages and does not eliminate the need for SSO, tenant isolation or authentic policy-document evidence.
