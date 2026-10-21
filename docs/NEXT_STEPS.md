# Build backlog — recommended order

**Gate 1 (done): local evidence prototype.** Ingest analyst workbook; preserve URLs and caveats; create searchable facility profile, source inventory, SEC page, data quality; run offline adapter and API tests.

**Gate 2: verified identity crosswalk.** Add audited FEI ↔ EPA FRS ↔ RCRA / NPDES / TRI / OSHA IDs and source-specific address normalization. Keep candidates and rejected matches, reviewers and original matching evidence. Add campus/building distinction and geocoding source/precision. Do not equate company ownership with a physical site.

**Gate 3: operational ingestion.** Test official EPA ECHO DFR responses for selected, *verified* FRS registry IDs; normalize inspection, enforcement, compliance and permit history only when API field meanings are confirmed. Schedule update/version capture and source-license review. Add tested NOAA, USGS, WRI, FEMA and industrial-hazard ingestion by geography with hazard-specific units.

**Gate 4: temporal validation.** For at least 25 facilities, capture evidence publication dates, confirmed event dates, claims / BI outcomes, public recovery milestones and no-event controls. Prevent future information leakage. Record sampling bias and the absence of insurance losses in public filings.

**Gate 5: real underwriting data.** Add construction, protection, replacement values, business-interruption values, property engineering, process hazards, backup power/water and supplier redundancy. Keep per-coverage loss pathways separate (property, BI, environmental, product and political risk).

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
