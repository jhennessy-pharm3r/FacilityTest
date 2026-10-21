# Pharm3r Facility Risk Intelligence — Build 1

An evidence-first facility risk research app for insurance underwriting. The app deliberately **does not calculate a facility risk score**: the current inputs are public-source research, not a calibrated sample of insured losses.

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

## What's included

- Facility explorer with verified identifiers, site coordinates, research summaries and matching cautions.
- Source-linked cross-facility evidence search, with facility/source/domain filters.
- SEC manufacturing impact and recovery findings, with unlinked cases kept unassigned.
- Data-source inventory and raw field catalog.
- Evidence-dated facility profiles, filterable detail drawer and downloadable CSV (with spreadsheet-formula injection protection).
- Data-quality dashboard (missing FEI/coordinates, unmatched SEC, availability dates, date semantics, re-import history).
- Local SQLite, read-only FastAPI endpoints and offline tests.
- Opt-in source adapters: USGS ComCat (regional earthquakes), WRI Aqueduct 4.0 (modeled baseline water stress), EPA ECHO DFR (raw response only) and NOAA Storm Events Details CSV (point-proximity, not property impact).

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
python -m facilityrisk refresh-echo --facility site-baxter-north-cove --registry-id VERIFIED_EPA_FRS_REGISTRY_ID
python -m facilityrisk ingest-noaa-csv "C:\path\StormEvents_details_2024.csv.gz" --radius-km 40
```

**EPA registry ID shown above is an illustrative placeholder, not a verified match.** Obtain the correct EPA FRS `REGISTRY_ID` from facility/address research. Do not substitute an FDA FEI. ECHO responses are archived raw without compliance normalization until their live schema has been validated.

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