# Build backlog — recommended order

**Gate 1 (done): local evidence prototype.** Ingest analyst workbook; preserve URLs and caveats; create searchable facility profile, source inventory, SEC page, data quality; run offline adapter and API tests.

**Gate 2 (implementation built; verification pending): verified identity crosswalk.** Add audited FEI ↔ EPA FRS ↔ RCRA / NPDES / TRI / OSHA IDs and source-specific address normalization. Keep candidates and rejected matches, reviewers and original matching evidence. Add campus/building distinction and geocoding source/precision. Do not equate company ownership with a physical site.

**Gate 3 (connectors built; live matching pending): operational ingestion.** Test official EPA ECHO DFR responses for selected, *verified* FRS registry IDs; normalize inspection, enforcement, compliance and permit history only when API field meanings are confirmed. Schedule update/version capture and source-license review. Add tested NOAA, USGS, WRI, FEMA and industrial-hazard ingestion by geography with hazard-specific units.

**Gate 4 (3 public case studies seeded; cohort pending): temporal validation.** For at least 25 facilities, capture evidence publication dates, confirmed event dates, claims / BI outcomes, public recovery milestones and no-event controls. Prevent future information leakage. Record sampling bias and the absence of insurance losses in public filings.

**Gate 5 (evidence categories built; insured values pending): real underwriting data.** Add construction, protection, replacement values, business-interruption values, property engineering, process hazards, backup power/water and supplier redundancy. Keep per-coverage loss pathways separate (property, BI, environmental, product and political risk).

**Gate 6: evidence-based screening, then calibrated risk.** Test indicators against a validated cohort and exposure denominator before any weighted risk score or loss propensity model. Track model version, exceptions and human approval. Score insufficient evidence as unranked, not low risk.

## Specific data anomalies in the analyst workbook

- 12 facility profiles, 11 with documented site points, 11 with FEIs.
- 990 evidence records and all source URLs populated, but *none* has a separately verified public-availability date.
- 19 SEC findings, 11 unlinked to a specific imported site. Many findings describe overlapping fiscal/event periods.
- The raw dates include **two post-2026 dates** in EPA program crosswalk records. These may be permit expiration/effective dates, not future incidents; verify semantics.
- Curated source labels do not exactly correspond to the 10 source-family names in the inventory.

## Proposed new-source tests

1. National Response Center — official incident reports; confirm whether investigation or corrective action verifies site attribution.
2. U.S. Chemical Safety Board — investigate major fires/explosions and documented causes and recovery.
3. EPA RMP — check data access and disclosure limitations before implementation.
4. EIA 861 — utility-level reliability context rather than exact factory outages.
5. Irish EPA LEAP — confirm actual facility IDs for Galway and Clonmel.
6. EU Industrial Emissions and Canada's NPRI — non-U.S. facility compliance and emissions context.
7. FEMA flood risk, historical NOAA storm footprint, USFS wildfire, WRI flood and water stress — quantitative *hazard exposure*, not site loss.

Status: source adapters tested with offline fixtures; **no live external API queries were completed within the development sandbox** due restricted outbound DNS/network.

## Build 2 completion and remaining operational blockers

- Built an interactive actual tile-based map, but none of the imported analyst coordinates is yet independently reviewed as an exact physical property point. No valid parcel-scale flood screen may be asserted.
- Built auditable FRS match review and secure-gated FEMA and ECHO source adapters. No live source registry matches have been independently corroborated.
- Added incident timelines and five evidence-based exposure sections. The three cases are retrospective; do not use them as pre-event predictive validation.
- Container/Compose and CI are reproducible prototypes, not a deployed production backend; enterprise RBAC/SSO and encryption/backup governance remain prerequisites.
- Scheduled public-source connectivity checks do not transmit client facility information or ingest the private database. Actual live ingest must run on a restricted environment and follow source/schema checks.


## FDA pharmaceutical/source identity blocker, verified October 21, 2026

The FDA DECRS home page advertises an annual-registration ZIP, but the published `https://www.accessdata.fda.gov/cder/drls_reg.zip` returned **HTTP 404** during multiple GitHub-hosted refreshes. The catalog correctly marks `fda_drug: unavailable`, does not mislabel FDA NDC labelers as manufacturing sites, and preserves a prior good drug snapshot if one becomes available. The `--drug-zip` offline import is supported if an official ZIP can be lawfully downloaded manually. FDA OII's separate FEI API requires issued credentials and supports **per-FEI** firm verification, not global facility enumeration; the new opt-in connector archives observations as unverified. Obtaining a current permitted DECRS download or another official complete register remains a hard dependency to complete the pharmaceutical universe.
