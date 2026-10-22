# Source validation matrix — October 21, 2026

The project separates **data download verified**, **official source identity linked**, **property location verified**, **regulatory/physical hazard contextualization**, and **historical event/outcome verified**. An accessible documentation URL or an HTTP 200 is never a substitute for those gates.

| Source | Confirmed implementation | Not yet established |
| --- | --- | --- |
| FDA device registration and listing (openFDA bulk) | 25,890 reported device source identities in last successfully inspected publication; 108 countries | Deduplicated physical sites, regulated role accuracy, inactive/historical site status, parent-company reconciliation |
| FDA Drug Establishments Current Registration Site | October 22, 2026 GitHub-hosted official DECRS ZIP successfully ingested: 10,422 source rows into 10,068 unique drug source identities; credentialed per-FEI API optional | Physical site deduplication, source free-text geographic completeness, current activity and site match review |
| Ireland EPA LEAP | 6,694 published official licence-profile identities, source GUID collisions guarded | Manufacturing classification for each record, verified physical property correspondence, emissions/enforcement detail |
| Canada NPRI | 7,715 source records from 2024 official ArcGIS reporting layer | Facility-specific releases as validated exposures; nonreporter meaning, active 2026 manufacturing confirmation, physical coordinates |
| EPA FRS and ECHO | Source candidate and verified-identifier gate; authenticated private ECHO DFR JSON archiving, official endpoint connectivity probes | Production-validated normalized violations, penalty/enforcement severity, facility-source crosswalk for full population |
| USGS and WRI Aqueduct | Live adapter code plus offline fixture tests; current point review gate | Actual point-level coverage for the universe, modeled loss or downtime |
| FEMA NFHL | Official polygon query after current point approval | Complete U.S. parcel coverage and historical-date flood interpretation |
| NOAA, PHMSA, NRC, CSB, fire | Explicit review-only incident candidate staging | Attribution of any nearby event to a specific insured plant or verified loss |
| SEC | 19 earlier analyst-identified filing findings, with 11 lacking verified site attribution | 25-site complete outcome cohort, verified pre-event public availability, insured exposure/loss denominator |

## Automated live probes

**Update (October 22, 2026):** The official FDA archive data-client HTTP 404 was resolved; the browser-compatible request to the same official host downloaded a valid ZIP, parsed the Windows-1252 tab-separated text and passed schema/source-row validation. See the GitHub `FDA facility registry update` workflow. The older failure description below is historical and must not be interpreted as current source status.


`FDA DECRS official download diagnostic` runs limited HEAD and four-byte GET checks against the FDA-published URL and saves a JSON diagnostic artifact. Passing the probe **does not** mean the archive was fully downloaded or the pharmacy population loaded. Review the `state`, HTTP codes, content type, final URL, and ZIP magic. If blocked, contact eDRLS@fda.hhs.gov for current supported download access. See the [official FDA DECRS page](https://www.fda.gov/drugs/drug-approvals-and-databases/drug-establishments-current-registration-site-decrs).

`Candidate cohort research artifact` builds a 25-row source-based research list from existing published catalogs, verifies it has 3 retrospective events and 22 *unverified identity candidates*, and uploads a short-lived CSV artifact. It does not write names or unverified control labels into a public site assessment, and does not generate any risk ranking.

## Research acceptance

Before using any item in insurance evidence, capture:

- Official publisher and record URL or immutable ID, content checksum, dataset vintage, retrieval time and first public availability time where independently confirmed
- Facility physical site/parcel and operator/parent, independently corroborated match and reviewed coordinates
- Source semantics (report vs incident, incident vs regulatory allegation, emissions reported vs permit violation, hazard vs insured loss)
- Observation window and independently confirmed outcome, including event date, operational disruption and separately identified property, BI, remediation and insurance recovery impacts
- Explicit missingness and quality-review status; no-hit is **unassessed**, not a clean facility
