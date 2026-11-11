# Pharm3r Facility Risk Intelligence — Insurance Workbench / v0.8

An evidence-first **all-industry facility discovery and risk research** application for insurance use. Every facility type is eligible for investigation; the initial FDA, Canada NPRI and Ireland EPA source populations are not the coverage universe. The 12 analyst facilities are case studies, not a limit on facility discovery. The all-industry backend registry is a separate source identity layer and is not yet a complete global inventory. The app deliberately **does not calculate a facility risk score**: the current inputs are public-source research, not a calibrated sample of insured losses.

## v0.8: all-industry insurance underwriting workflow

The public preview opens on an **interactive insurance exposure workbench** for any facility or industry (not limited to FDA). Analysts can select research scenarios—flood, hurricane, wind, earthquake, fire, industrial hazards, and power/water/telecom/supplier/access/cold-chain dependencies—then inspect property, BI, utility-interruption, contingent BI and parametric products that *may* be relevant. Policy review statuses are **user-reported and unverified**; a product's commercial availability does not prove an insured has coverage. A gross downtime contribution-margin illustration does not constitute an insured loss calculation or payout. Users can export a versioned research worksheet to JSON directly from the browser; no user input is sent to the app service by this module.

A facility source identity from the public regulatory catalog or authenticated universal registry can prefill the workbench without carrying over previous sites' hazard/coverage assumptions. The research case and private API/SQLite backend are separate from the public Pages preview. Read [current authoritative backlog](docs/NEXT_STEPS.md) for production and hazard-verification gates.

## FEMA flood and USFS wildfire: installed-source private API

The official-source Lane A ingestion code is merged (PR #75). An optional **authenticated, read-only source index** can now expose the original FEMA NFHL and USDA WHP2023 source records from an operator-installed immutable release. It does **not** generate a facility risk score, legal FEMA map determination, or insured loss.

The verified frozen Lane A source release contains **34 FEMA flood polygons (six small QA windows only)**, **70 continuous + 70 classified USFS 2023 raster QA pixels**, and **35,304 nationally published county/state/ZIP/management aggregate rows**. In the ZIP cohort, **60** records have unknown hazard acreage. The complete WHP2023 original publisher raster archive has now been **acquired, SHA-validated and independently pixel-audited in GitHub Actions**, but neither those TIFFs nor the 5.8M-record national FEMA polygon corpus are installed on a verified permanent private server. Only the 34-record FEMA QA cohort has been installed temporarily. These counts describe government-source grain, not insured buildings.

For a controlled private host, install the verified source bundle under `./source-index/lane-a` using `python -m scripts.lane_a_install`, set `FACILITY_RISK_LANE_A_INDEX_ROOT=/app/source-index/lane-a` in the untracked Compose `.env`, and validate `GET /api/lane-a/status` with authentication. The private Source Health view lists all four cohorts and the hazards panel permits a **read-only** FEMA polygon check only for sites whose **current coordinates are independently reviewed in the private workspace**. Missing/failed source data remain UNKNOWN. All static GitHub Pages counts remain staging-only; **not publicly hosted as a private source database**.

Complete commands, authenticated endpoints, refresh/rollback, source SHA receipts and the remaining host/security gates: [Lane A private API integration](docs/LANE_A_PRIVATE_API_INTEGRATION.md), [source handoff](docs/LANE_A_INSTALLATION_HANDOFF.md), and [secure deployment requirements](docs/SECURE_DEPLOYMENT.md).

### Complete original USDA wildfire rasters — separate private source product

**PR #88 merged:** Downloaded original USFS WHP2023 publication (368,424,961-byte archive; original SHA256 `7f10f1f8dd97551b8be1458fe0ec924df60b2cea7ece2d1af4c3c1166d1895ab`). Six original native 270m GeoTIFFs are verified across **CONUS, Alaska and Hawaii**, with **133,505,015 non-masked modeled pixels per continuous/classified product** and **168,553,707 masked/no-data cells per product**. These are modeled landscape cells, not facility records, fire events, probabilities, insurer loss outcomes, or sites. The model largely reflects 2020 fuels.

`python -m scripts.lane_a_whp_full_raster --root ./source-index/whp2023-full --expected-sha256 7f10f1f8dd97551b8be1458fe0ec924df60b2cea7ece2d1af4c3c1166d1895ab --full-audit` downloads and locally installs an immutable, source-replayable, SHA-derived release. The optional private Compose env `FACILITY_RISK_WHP2023_RASTER_ROOT=/app/source-index/whp2023-full` exposes its **read-only** and **authenticated** `GET /api/lane-a/whp2023/full-status` source status and `GET /api/facilities/{facility_id}/usfs-whp2023` reviewed-site raster evidence. Site-specific queries require a **currently independently reviewed private workspace coordinate**; missing or masked original source pixels return UNKNOWN, class 6/7 remain distinct land-cover masks, and no effective insurance coverage/loss is inferred. The public Pages site does **not** host the original rasters. See [full national raster handoff](docs/LANE_A_WHP2023_NATIONAL_RASTERS.md), [private index deployment requirements](docs/LANE_A_PRIVATE_API_INTEGRATION.md), and [Issue #39 persistent secure hosting](https://github.com/jhennessy-pharm3r/FacilityTest/issues/39).

## GitHub Pages public preview

The repository root `index.html` hosts a **read-only public preview** at
`https://jhennessy-pharm3r.github.io/FacilityTest/`. Pages cannot execute the Python/FastAPI/SQLite service or connectors.
The preview shows a separate, small, attributed public case-study dataset. It does **not** publish the private analyst workbook or 990-row evidence database. Site markers in the public preview are **city-level reference points only**.

To explore the full local research within the hosted UI without uploading data to GitHub:

```powershell
python -m facilityrisk export-browser data\my-private-facility-snapshot.json
```

Open the Pages site, select **Load private snapshot**, and choose the local JSON file.
The snapshot is read into browser memory only; there is no upload endpoint, storage persistence, or sharing link. The file itself contains the complete research corpus and must remain private. It is excluded by `.gitignore` under `data/`.

See [hosting and security notes](docs/GITHUB_PAGES.md).

## Private industrial incident source API (Lane C + Lane E)

The authenticated backend can browse 17 USCG NRC annual reporting cohorts
(2010–2026, 2026 provisional), the latest CSB release, and a **separate**
PHMSA Work Management System enforcement-case index through approved,
checksummed, versioned read-only SQLite releases. No source observation
automatically becomes a verified physical facility, unique confirmed accident,
insurance claim, or paid loss. The primary PHMSA pipeline/hazmat incident
census has not been ingested because official agency exports remain access-blocked.

The private **Source health** screen offers a source-vintage incident explorer
and PHMSA operator-ID case lookup when a verified private index is mounted.
These controls **do not operate on GitHub Pages**. They require the existing
authenticated FastAPI backend and strictly separate private source storage.
All REST endpoints deny missing credentials; cross-agency review candidates
require an individually authenticated reviewer/admin account.

For production preparation, verified source counts, original source
provenance, complete install/refresh/rollback commands, container read-only
mounts, security prerequisites and an operator-run real-host API acceptance
tool, read [Lane E Private Industrial Deployment](docs/LANE_E_PRIVATE_INDUSTRIAL_DEPLOYMENT.md)
and the [Lane C Integration Handoff](docs/lane-c-integration-handoff.md).
GitHub Actions staging and API smoke checks do not constitute a durable,
tenant-secure deployed source service. No real insured physical-site
validation or actuarial loss assessment is implied.

## Public regulatory identities versus universal private facility registry

The public app now includes **All registered facilities** as a separate discovery tab. It searches a periodically refreshed compact catalog of FDA medical-device registrations and, where successfully parsed, FDA drug-establishment records. Foreign U.S.-market registrants are included. The catalog is generated by the scheduled GitHub Actions workflow, not from private analyst workbooks.

**Important:** The FDA listing population is not the entire worldwide manufacturing universe. An FDA registration is not evidence of regulatory approval, a physical property coordinate, an environmental incident, or an insurance loss. Sites not present may be opened as **unverified research requests**; evidence is linked only after manual identity verification.

Run `python -m facilityrisk import-registry web/registry/catalog.json` to make the public catalog searchable in the authenticated local backend. The original 12 facilities remain **Research cases**. See [coverage and limitations](docs/COVERAGE.md).

## What's included

- Facility explorer with analyst-recorded identifiers, site coordinates, research summaries and verification flags.
- Source-linked cross-facility evidence search, with facility/source/domain filters.
- SEC manufacturing impact and recovery findings, with unlinked cases kept unassigned.
- Data-source inventory and raw field catalog.
- Evidence-dated facility profiles, filterable detail drawer and downloadable CSV (with spreadsheet-formula injection protection).
- Data-quality dashboard (missing FEI/coordinates, unmatched SEC, availability dates, date semantics, re-import history).
- Local SQLite, read-only FastAPI endpoints and offline tests.
- Opt-in source adapters: USGS ComCat (regional earthquakes), WRI Aqueduct 4.0 (modeled baseline water stress), EPA ECHO DFR (raw response only) and NOAA Storm Events Details CSV (point-proximity, not property impact).

### Build 2: underwriting and verified-evidence workflow

- **Five new browser sections:** Incident timelines (12 dated milestones across Baxter North Cove, Pfizer Rocky Mount and Amgen Juncos); interactive geographic map with OpenStreetMap and explicit point precision; identity-crosswalk review status; five-category underwriting exposure profiles; source connectivity and provenance status.
- **Verified identity gates:** EPA FRS records become *candidates*, never accepted automatically; accept/reject demands corroborating HTTPS evidence, reviewer and rationale. FEIs imported from the workbook are marked observed, not independently validated.
- **Flood gate:** FEMA NFHL zone query is allowed only after manual site-coordinate review. No returned NFHL geometry means *unmapped*, not low risk; historic storm loss is separate from current flood zone.
- **Real-source adapters:** USGS earthquakes, NOAA storm CSV, WRI Aqueduct, EPA ECHO raw responses, FEMA zone, EPA FRS candidates and FDA inspections CSV. Parsers are fixture tested; the service reports connectivity without inventing ingested records.
- **Private-case data:** 3 public primary-source incidents and 12 milestones are also seeded in the private database, alongside the original 990 evidence rows.
- **Private hosting blueprint:** Container/Compose local-only listener, fail-closed single-tenant bearer/basic token guard, optional controlled writes, and CI plus weekly public endpoint connectivity checks. **Not production insurer SSO/RBAC.** See [secure deployment](docs/SECURE_DEPLOYMENT.md).

```powershell
python -m facilityrisk seed-cases
python -m facilityrisk qa
python -m facilityrisk probe-sources
python -m facilityrisk discover-frs --facility site-baxter-north-cove --name "Baxter Healthcare" --state NC
# Review each candidate before acceptance; the app will not automatically assert a link.
```

### Quick start — Windows PowerShell

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m facilityrisk ingest-workbook "C:\path\Facility Risk Data Exploration.xlsx"
python -m facilityrisk serve --port 8765
```

Open http://127.0.0.1:8765 in your browser. On macOS/Linux, use `python3 -m venv .venv` and `source .venv/bin/activate` instead. The local data lives in `data/facility_risk.sqlite`.

**If you received the privately packaged build with the preloaded SQLite file**, you can skip workbook ingestion and run `python -m facilityrisk serve` after installation.

### Refresh real public-source data — requires outbound internet

Inspect the site's coordinates and verify physical-site identity before ingestion. The following commands are **opt-in**; they do not run automatically.

```powershell
python -m facilityrisk refresh-usgs --facility site-baxter-north-cove --start 2023-01-01 --end 2024-12-31 --radius-km 150 --min-magnitude 4
python -m facilityrisk refresh-aqueduct --facility site-baxter-north-cove
python -m facilityrisk refresh-verified-echo --facility site-baxter-north-cove
python -m facilityrisk ingest-noaa-csv "C:\path\StormEvents_details_2024.csv.gz" --radius-km 40
```

**EPA FRS matches must be reviewed and accepted before ECHO refresh.** The original FEI is not an EPA FRS `REGISTRY_ID`; do not substitute it. ECHO responses are archived raw without compliance normalization until their live schema has been validated.

USGS detects earthquakes with epicenters inside the chosen radius; it does not estimate shaking intensity, insured damage or business interruption. Aqueduct is modeled basin-level exposure. NOAA storm points are approximate and do not imply a specific facility was affected.

### Tests

```powershell
pip install -r requirements-dev.txt
pytest -q
python -m facilityrisk qa
```

Offline tests use synthetic fixtures for the public-source adapters. If the original analyst workbook exists at `/mnt/data/Facility Risk Data Exploration.xlsx` or `FACILITY_RISK_WORKBOOK`, an additional integration test ingests and validates all of its sheets. Live API connectivity still requires verification from an internet-enabled environment.

### API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/overview` | Research volumes, site footprint, domain breakdown |
| `GET /api/facilities?search=...` | Search/paginate sites |
| `GET /api/facilities/{id}` | Site summary and associated disclosures |
| `GET /api/facilities/{id}/evidence` | Source-linked evidence, filtering, pagination |
| `GET /api/evidence` | Search all evidence across sites |
| `GET /api/financial` | SEC findings, not deduplicated financial losses |
| `GET /api/public-evidence` | Supplemental source references |
| `GET /api/sources` | Source research inventory |
| `GET /api/source-fields` | Analyst field catalog |
| `GET /api/quality` | Data quality and source ingestions |
| `GET /api/match-preview` | Match candidates; only verified exact FEI permits auto-linking |

### Data governance and safety

- **Public GitHub repository:** Code, tests and documentation only. `.gitignore` excludes research workbook, downloaded source files, live snapshots and database. Do not publish source exports or client data without authorization.
- **Local-only:** The prototype has no login, permissions, rate limiting, or production security. The server defaults to `127.0.0.1`. Do not expose it publicly or bind to `0.0.0.0` without authentication and authorization.
- **Evidence quality:** A link existing in an analyst workbook is not live API verification. Publication/availability date is unverified on imported evidence rows. Historical backtesting needs the *information availability date* to be earlier than any target outcome.
- **Facility matching:** Name similarity produces review candidates only; never silently merge facilities, or treat EPA FRS IDs as FDA FEIs.
- **No unwarranted conclusions:** Nearby weather/earthquakes, environmental compliance, and regulatory citations are not proof of insured loss, negligence or a site shutdown.

See [next development steps](docs/NEXT_STEPS.md) and [data model](docs/DATA_MODEL.md).

### Optional FDA FEI verification reference (private only)

The FDA OII FEI API requires an FDA-issued **Authorization-User** and **Authorization-Key**. Apply through [FDA FEI API Usage Documentation](https://www.accessdata.fda.gov/scripts/feiportal/apidocs/) (contact listed there). Do not commit these secrets or expose them in the browser. Configure them only in a secured backend environment:

```powershell
$env:FACILITY_RISK_FEI_AUTH_USER = '<FDA-issued username>'
$env:FACILITY_RISK_FEI_AUTH_KEY = '<FDA-issued secret>'
python -m facilityrisk lookup-fda-fei --facility site-baxter-north-cove
```

The lookup submits **only the facility's observed FEI** to the official authenticated FDA endpoint, archives a minimal firm-name/physical-address observation and an audit event, and leaves the FEI **unverified**. This is a user-initiated observation, not a bulk DECRS substitute, a manufacturing licence, or a facility risk score. To enable the HTTP equivalent `POST /api/facilities/{id}/fei-lookup`, the private server must also set `FACILITY_RISK_ENABLE_WRITES=1` and authenticate the user. Review physical-site correspondence separately before accepting any crosswalk.


### Facility assessment and on-demand research (v0.6 development)

The **private** FastAPI instance (not GitHub Pages) supports source-grounded report generation and site-specific research planning. Do not publish the generated report if it contains analyst/client data.

```powershell
python -m facilityrisk plan-research --facility site-baxter-north-cove
python -m facilityrisk research-status --facility site-baxter-north-cove
python -m facilityrisk export-assessment --facility site-baxter-north-cove --output data/baxter-assessment.html
python -m facilityrisk build-pilot --output data/pilot-research-candidates.csv
```

The site report includes reviewed identifiers, regulatory observations held for identity review, hazard checks, company disclosure references, confirmed retrospective cases, pending nearby-event candidates and per-domain missingness. It remains **unranked** and contains no actuarial loss probability, underwriting acceptance or premium calculation.

The optional `run-research-source` command executes **one request now**, never a background or continuous monitor. Set `FACILITY_RISK_ENABLE_SOURCE_REQUESTS=1` only on a controlled environment after verifying the operator's approval and source terms; then explicitly request e.g. `run-research-source --facility ID --source fema_flood`. It blocks if site coordinates or jurisdiction are not eligible; ECHO also requires a verified EPA FRS identity. Private API endpoints: `GET/POST /api/facilities/{id}/research`, `POST /api/facilities/{id}/research/run-source`, `GET /api/facilities/{id}/assessment`, and `GET /api/facilities/{id}/assessment.html`. Browser POSTs also require `FACILITY_RISK_ENABLE_WRITES=1` and authentication.

**Pilot caveat:** `build-pilot` creates three retrospective example rows and twenty-two independently sourced **unverified research candidates**, not a validated 25-plant cohort or no-loss controls. See [pilot protocol](docs/PILOT_PROTOCOL.md).



### FDA pharmaceutical registry coverage — verified import (October 21, 2026)

The authenticated-independent public FDA ZIP was successfully parsed as official Windows-1252 DECRS data on GitHub Actions. It yielded **10,422** drug registration source rows and **10,068** distinct drug source identities, alongside **25,890** device source identities. See [live workflow](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39681018525). These numbers measure **source identities**, not verified physical pharmaceutical manufacturing facilities. Drug-specific `field_coverage_by_sector` now reports observed FEI, reported address, and structured country/city completeness. The source registration file may include an address but no separate structured country/city; the app does **not** guess these fields from free text. The number of countries observed in the public catalog therefore cannot be interpreted as geographic coverage of all drug establishments.

Private facility reports show at most 250 evidence records and now disclose when evidence is not fully displayed. Use the full evidence explorer/CSV export for all linked findings. Risk scores and incident-based loss probabilities remain unranked until verified physical-site and claims evidence are available.


### Second-person source identity approval (private server only)

Optional `FACILITY_RISK_DUAL_REVIEW=1` with per-user PBKDF2 credential mapping stages location, FEI and regulatory crosswalk reviews as pending. A **different authenticated approver** is required before any protected source identity is promoted. Site moves or source candidate revisions invalidate outstanding proposals; a rejected crosswalk also revokes a previously verified identity. This is not SSO, client tenancy or actuarial approval. Consult [secure deployment notes](docs/SECURE_DEPLOYMENT.md). Shared service tokens remain read/integration credentials and are not human approvers.


### Complete authenticated evidence export

Private facility reports show a deliberate 250-row preview limit so large records do not overwhelm printable assessments. The private HTML report now offers `GET /api/facilities/{id}/evidence.csv`, which streams **all linked source evidence** for the selected facility, including evidence source, raw date, original text, match confidence, source URL, limitations, ingestion and independently verified availability timestamps. Excel-formula-like strings are prefixed for spreadsheet safety without changing the stored database values. Exports remain authenticated and uncached, and are not published to GitHub Pages or workflow artifacts. A file opened from a local `.html` export has no backend API; export full evidence from the authenticated running service when needed.


## Universal facility expansion

The private v0.7 registry provides indexed cross-industry source searches, audited manual identity linkage, authorized CSV/GeoJSONSeq imports, and a separate insurance coverage reference taxonomy (including property, business interruption, utility disruption and parametric options). The public Pages preview does not execute this backend and must not imply all commercial or industrial facilities are already loaded. See [universal facility documentation](docs/UNIVERSAL_FACILITIES.md).

An official **EPA FRS National** staging pipeline now downloads the published national ZIP and, only after schema/row checks, creates a temporary GitHub Actions artifact with the normalized, source-only data and checksum manifest. It does not automatically publish millions of facility records to Pages or a production service. Use the artifact with the private importer and verify the resulting registry counts and source vintage. See [EPA import workflow](.github/workflows/build-epa-frs.yml).

## EPA source-index integration (private service)

EPA ECHO, RCRAInfo, all 38 official TRI Basic reporting years (1987–2024), and the **public** FRS-RMP interests are included as **regulator-source-only** importer/index artifacts. [Lane B PR #76](https://github.com/jhennessy-pharm3r/FacilityTest/pull/76) was merged after full official-source checksum, replay and read-only installation QA; [coordinator integration](https://github.com/jhennessy-pharm3r/FacilityTest/pull/82) wires optional authenticated source-native-ID routes and an **EPA regulatory evidence** page into the private app. GitHub Pages is static and does not deploy those multi-GB source indexes. No regulator observation is automatically a verified insured property, pollution damage, claim or paid loss.

See [private EPA installation + complete retrieval/recovery instructions](docs/EPA_LANE_B_DEPLOYMENT.md), [original publisher and data QA](scripts/lane_b_epa/INTEGRATION_RELEASE.md), and [durable hosting prerequisite #39](https://github.com/jhennessy-pharm3r/FacilityTest/issues/39). Production-deployed and independently approved insured-property-match counts remain **zero** until real private-host service, security and site QA are verified.

## Lane D private utility/outage source API

Private authenticating code can query original EIA-861, PNNL historical county evidence, DOE OE-417 and rights-gated ORNL source snapshots only after validated, immutable indexes are installed. Installation and API availability do not prove a facility's serving utility, outage, insured BI or paid claims. See `docs/LANE_D_PRIVATE_DEPLOYMENT.md`. No source records are publicly hosted by GitHub Pages.
