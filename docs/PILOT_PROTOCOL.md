# Facility Risk v0.6 pilot protocol

## Status

**Candidate cohort only. Not 25 verified plants, not 22 confirmed non-event controls, and not a calibrated insurance loss dataset.**

The `build-pilot` command selects 25 research rows from versioned official-source catalogs:

- 3 curated retrospective disruption cases (Baxter North Cove, Pfizer Rocky Mount, Amgen Juncos)
- 12 FDA device registration identities (not necessarily verified manufacturing plants)
- 5 Ireland EPA licence profiles (licence records can represent non-manufacturing activities)
- 5 Canada NPRI reporting identities (an NPRI reporter is not automatically a manufacturer)

Selection of source-only records uses SHA-256 sorted keys to avoid always choosing alphabetically first names. The 3 historical cases are *illustrations*, not examples to include in an unguarded predictive training cohort. All other outcome states remain `unknown_not_a_confirmed_no_event_control`. No row asserts an insurer claim outcome, an exact property point, risk magnitude or registration validity as of analysis date.

Command:

```powershell
python -m facilityrisk build-pilot --output data/pilot-research-candidates.csv
```

Keep this file within a private workspace, not GitHub Pages or a publicly linked folder.

## Analyst qualification process

For each candidate:

1. Verify official source identity, original business function, physical property, owner/operator, parent entity, and current/historical address; remove duplicate or nonmanufacturing sources from life-sciences underwriting cohorts.
2. Source independently reviewed building coordinates and record the actual reviewer, corroboration URL and coordinate vintage.
3. Collect regulatory compliance, environmental permits/incidents, facility protection and natural hazard exposure **with source-specific scope and publication dates**. Avoid interpreting no hit as low risk.
4. Resolve dated operational events and actual downtime against company SEC filings, regulatory investigations, contemporary news, and verified facility/customer disclosures.
5. For *potential* non-event controls, verify that the selected source and observation window are comparable, and document why the outcome is treated as no known event. **No public-source absence alone establishes a loss-free control.**
6. Separate gross production interruption, revenue timing, direct property costs, environmental remediation, capital replacement and insurance recoveries. Do not sum repeated 10-K/10-Q estimates.
7. Store original event timestamp, first publicly available evidence timestamp and site match record. Exclude any feature not available before the event for pre-event model tests.

## Exit criteria

- At least 25 **independently reviewed physical** sites, with a justified mix of documented events and independently researched comparison controls (the candidate manifest alone does not pass).
- Explicit company, operator, parent and physical-property identities for each retained site.
- At least 3 pertinent source groups checked per site; eligibility, missingness and observation vintage recorded per group.
- Five completed, independently reviewed facility evidence assessments with original sources.
- Historical event labels and evidence-publication dates validated in time order, with source coverage and selection bias documented.
- An exposure denominator and loss-severity/claims definitions before fitting any numeric model. Until then risk scores remain **unranked**.

## Current technical capabilities

- `plan-research --facility ID` writes a source-by-source checklist and audit event without launching a background job.
- `research-status --facility ID` displays all plans and explicit attempts.
- `run-research-source --facility ID --source fema_flood|wri_water|epa_echo|usgs_earthquake` executes exactly one permitted operation after opt-in and verified identity/point guards.
- `export-assessment --facility ID --output data/site-assessment.html` writes a printable private source-based report. The report contains no loss prediction, probability or premium.
- The private API exposes matching report/research routes. GitHub Pages remains a read-only preview and does not persist private research.

Live source queries require `FACILITY_RISK_ENABLE_SOURCE_REQUESTS=1` on the authenticated private server, in addition to route write authorization for browser access. FDA FEI firm lookup separately requires FDA-issued credentials. No source test or public registry listing constitutes a verified physical facility, a confirmed incident or underwriting approval.
