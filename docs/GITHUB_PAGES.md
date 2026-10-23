# GitHub Pages — public research preview

## Architecture

- `index.html` at repository root is a static Pages entry point.
- `web/app.js` is the same UI shared with the local FastAPI app.
- `web/public-api.js` is a browser-only read adapter that implements API-like filtering and pagination.
- `web/public-demo.json` holds a **separately researched, public, three-facility set** linked to primary issuer and SEC documents.
- `web/case-studies.json` adds 3 retrospective incidents with 12 dated milestones; `web/intelligence-ui.js` adds historical timelines, interactive map, crosswalk review, underwriting summaries and source health views.
- Map tiles and Leaflet load from public third-party networks; only use the public preview or appropriately anonymized coordinates for this feature.
- The original `web/index.html` + `/api/` endpoints continue to run locally using the SQLite database.

The hosted preview **is not a live government data feed**. It cannot run SQLite, server-side Python ingestion, monitoring jobs, or private authentication on GitHub Pages.

## Shareable URLs and browser history

Pages use same-document **query-string URLs**, which work from the GitHub Pages
project path without a server rewrite. Sidebar items are actual links, so they
can be opened in a new tab. The **Copy link** action copies the current view URL.
Browser Back and Forward restore the selected page, public-source registry search
and source record, and (for available source-backed research cases) the facility
details drawer and selected risk/evidence tab. A refresh or newly opened tab can
load the same public state.

Examples:

- Source health: `https://jhennessy-pharm3r.github.io/FacilityTest/?page=feeds`
- Public registry search: `?page=registry&q=Pfizer`
- Facility case detail: `?page=facilities&facility=public-baxter-north-cove&tab=risk`

The public registry can also restore a selected `record` ID, source and
country/sector filters, and pagination. The private universal search can restore
source identity IDs and search filters **only for recipients already authorized
to access that private backend**. The application will not assert a physical site
match or a risk score merely from a shareable link.

**Data safety:** Links do not include workbench-entered insured values,
insurance policy terms, downloaded private datasets, or locally imported
research findings. A browser-imported private snapshot is not available to
another recipient and cannot be shared merely by copying its page URL.
Sharing a source reference does not grant access to private server data.

## Load private analyst data without publishing it

1. In the project root after ingesting the workbook, run
   `python -m facilityrisk export-browser data/my-private-facility-snapshot.json`.
2. Visit the static GitHub Pages URL, and click **Load private snapshot**.
3. Choose the JSON file. The browser reads it using the File API, keeps it in memory, and rerenders the explorer. It does **not** send data to GitHub Pages or any remote API.
4. Click **Reset** to return to the public example set. Refreshing the page also discards the private data.

**Important:** The generated file includes complete facility research, source URLs, disclosure notes, and unvalidated metadata. It must not be committed into the public repository, shared with unauthorized users, or used for an insurance rating. A browser extension may have access to page content; private work should use a managed environment for sensitive data.

## Deployment

GitHub Pages can publish from `main` root (Settings → Pages → Build and deployment → Deploy from a branch → main → /(root)). The root `index.html` and `.nojekyll` are included for this mode. The static site uses relative paths (`./web/...`) compatible with the `/FacilityTest/` project path.

There is no requirement to deploy Python, SQLite, `.env`, `data/`, or test artifacts.

If the current Pages source is not `main /(root)`, select it under repository Settings → Pages. Check Actions → Pages build and deployment for errors. The site is public even if the workbook is local.

## Checks

- Public browser mode loads all seven navigation tabs without `/api/` calls.
- Source linked evidence and SEC reference URLs lead to the original publisher.
- Private JSON importer validates schema 1.0, duplicate facility IDs, orphan evidence and size limits (20 MB).
- Public-demo city-level markers are **not** site geocodes and must not be used in property hazard overlays.
- Imported data is kept in memory, not localStorage, cookies, URL query strings, or network requests.

## Private hosting

See [Secure deployment blueprint](SECURE_DEPLOYMENT.md) for a locally bound, token-gated server and the safeguards still required before handling insurer client data. Github Actions runs Python tests and a weekly public endpoint health check, **not** private facility ingestion.

## Next gate

Deploy an authenticated backend in a separate environment with server-side ingestion, audited facility identifiers, and insurer-level access control. Configure Pages as a frontend only if CORS, authentication and client data governance are properly addressed.


## Independent Ireland EPA public lookup

`web/registry/ireland-leap.json` is a minimal catalogue of Ireland EPA LEAP
licence profile identities, updated by the registry workflow and shown alongside
FDA registrations without automatic deduplication or facility matching. Its
presence does not establish manufacturing activity, a site coordinate,
environmental violation or insured property loss. Contact fields are excluded.


## Canadian NPRI source catalogue

`web/registry/canada-npri.json` is populated exclusively from Canada's official NPRI ArcGIS reporting-facility layer, currently described as 2024. It is published by a separate automated workflow so a transient Canadian source outage does not block updates of the FDA or Irish-source catalogs. The browser adds the source identities without cross-source deduplication or assigned underwriting scores. Geographic coordinates and private analyst matching are not in the public file. Records are labeled *Environmental reporting*; reporting is not an enforcement finding or known insurance loss.
