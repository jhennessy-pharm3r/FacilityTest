# Lane E — Private industrial source API / self-hosted deployment guide

**Scope:** all facility types/industries, subject to each regulator's reporting universe. **Do not interpret regulator source rows as a census of physical insured sites, unique confirmed accidents, insured losses or insurance policy coverage.** This guide is for a private, authenticated FastAPI deployment. The existing [public GitHub Pages app](https://jhennessy-pharm3r.github.io/FacilityTest/) is static and **cannot** host SQLite, live Python APIs, ingestion or scheduled refresh.

**Actual verified upstream data (October 23, 2026):** Lane C [PR #79](https://github.com/jhennessy-pharm3r/FacilityTest/pull/79) validated 17 NRC annual reporting cohorts (2010–2026, open provisional 2026) with **429,122 accepted native notifications**, plus **674** current CSB release rows after **1 rejected** undated original = **429,796** normalized source observations across 18 namespaces. Separately **5,089** PHMSA WMS *enforcement cases* are normalized and indexed; these are not PHMSA pipeline/hazmat accident report census observations. Original PHMSA accident releases remain **HTTP 403/inaccessible**. CI installs are temporary and **are not a verified durable production deployment**. Original source SHA-256 and row counts: [Lane C source ledger](lane-c-industrial-incidents.md); [Lane C ingestion/install commands](lane-c-integration-handoff.md).

## Verified end-to-end official publisher data through authenticated private API

**[Actions real-source API run #40006495901](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/40006495901) PASSED** on October 23, 2026. The [aggregate-only, seven-manifest QA artifact #12524956764](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/40006495901/artifacts/12524956764) was downloaded, extracted and independently examined. No original NRC/CSB/PHMSA row-level source workbooks, normalized rows, SQLite, sensitive text or API credentials were uploaded.

The actual workflow downloaded official first-party NRC CY2010–CY2026 and CSB Sep 2026, normalized and SHA-revalidated all 18 source namespaces, installed versioned read-only source indexes on a temporary protected runner path, independently fetched PHMSA's 5,089 enforcement-case source, installed its **separate** read-only SQLite, and used a strongly authenticated FastAPI TestClient to query **every source namespace** and role-restricted cross-agency candidates. Results (verified by both the initial run and a **fresh process restart**):

| Acceptance check | Actual result |
| --- | --- |
| NRC + CSB source observations indexed and accessible | **429,796**, 18 source namespaces, PASS |
| PHMSA separate enforcement cases indexed and accessible | **5,089**, PASS — not incident census |
| Exact cross-regulator reported-attribute candidate pairs | **135**, REVIEW-ONLY |
| All-source bounded authenticated queries | **18/18 PASS** |
| Worst observed per-cohort read-only query latency | **7.9 milliseconds** in the restart test on GitHub-hosted runner (not a production SLA) |
| Unknown source names, bad dates, unauthenticated access | **FAIL-CLOSED PASS** |
| Individually authenticated reviewer gate | **PASS** |
| Indexed SQLite SHA-256 | NRC/CSB `c72526a738d9687978617ca2dc2d19e54b458a47d83caf2ab3b3057f74885d17`; PHMSA case index `022307edfd6707b11fa421faf6835a16d3e74c936ded0a81d190916994ef281f` |
| Unredacted temporary original/normalized/index cleanup | **PASS** |
| Confirmed physical insured sites, insurer losses | **0 independently verified** |
| Durable production host / OIDC tenancy / live customer deployment | **NOT PROVISIONED OR VERIFIED** |
| PHMSA national primary pipeline/hazmat incident exports | **NOT TESTED — OFFICIAL 403 / LOGIN** |

The real-source end-to-end test uses installed original source files but a **disposable GitHub Actions runtime**, not a durable insurer environment; it demonstrates a working backend implementation, not completion of external production infrastructure or site-level insurance validation.

**[Private Source Health browser UI smoke #40006934553](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/40006934553) PASSED**, testing actual Source Health navigation, 25 **synthetic** cross-industry unreviewed source rows, reported-state filtering, native PHMSA operator search and no auto site linking. [Standard CI #40007016363](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/40007016363): **205 passed, 1 skipped**, JavaScript syntax PASS; [public GitHub Pages preview browser #40007016250](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/40007016250) PASS. All three tests are distinct: only the first uses actual official source data; only the second shows a synthetic private browser UI; neither is an external production insured-site acceptance test.

## Branch/merge dependency

Lane E integration [PR #84](https://github.com/jhennessy-pharm3r/FacilityTest/pull/84) is **stacked on Lane C #79**, so it can test the actual source installers without copying or silently changing the lane's ingestion code. Coordinator sequence:

1. Independently review and merge approved Lane C source package #79, retaining its disclosed PHMSA access limitations.
2. Retarget Lane E #84 from the Lane C branch to `main`, resolve any source-status UI conflicts while preserving the latest public coordination filter/page behavior, and rerun all CI.
3. After another reviewer signs off and CI is green, merge Lane E integration and deploy on the explicitly provisioned private backend. Do **not** self-merge worker PRs.
4. Record actual deployed counts **only after live backend/app verification**, not after Actions completes.

## Protected host layout and permissions

Use an authorized, encrypted, backed-up private server or VM. The repository connector alone does not provision such a host, cloud tenancy, persistent disks, DNS, TLS proxy or organization SSO. Allocate disk for original NRC workbooks, normalized copies, read-only SQLite and previous immutable releases. **Do not store private source files or client workspace in a public Git repository.**

Example private layout (paths may differ):
```
/srv/facility-risk/
  source-index/             # HOST PATH, outside git checkout, mounted read-only into Compose
    lane-c/
      active-release.json
      releases/<approved-id>/indexes/lane-c-source.sqlite
    phmsa-wms/
      active-release.json
      releases/<approved-id>/indexes/phmsa-wms-enforcement.sqlite
  incoming/                 # original official files and provenance (protected operator only)
  ingestion-qa/             # aggregate QA manifests; keep detailed original records private
  backups/                  # encrypted off-host backups, tested restores
```

The Lane C installer enforces installation **outside** the repository. Hence the default legacy Compose `./source-index` directory is unsuitable for *new Lane C installation*; explicitly set `FACILITY_RISK_PRIVATE_SOURCE_HOST_DIR=/srv/facility-risk/source-index`. Compose mounts that host directory at `/app/source-index:ro`, separate from the writable analyst workspace `/app/data/facility_risk.sqlite`.

The Docker image runs UID/GID `10001`. Apply **least-privilege ACLs**: the serving identity requires traversal of the two versioned release trees and read access to their active pointers, bundle manifests and **SQLite files only**. It does **not** need read access to the raw original publisher workbooks, normalized gzip exports or sensitive per-source raw extracts. Keep those source originals at operator-only `0400` behind nontraversable subfolders, grant the service GID `10001` read/traverse only on the needed pointers/manifests/indexes, and explicitly deny `other` users. A reviewable setup approach is `setfacl -m u:10001:rx` on only the directory ancestors needed, `setfacl -m u:10001:r` on `active-release.json`, `private-bundle-manifest.json` (or WMS equivalent), and their indexed SQLite files, while leaving `originals/` and `normalized/` operator-only. ACLs must be re-applied to **each new immutable release** during promotion by the privileged operator. Audit with a UID 10001 read test against the SQLite, then separately assert the same UID **cannot** read raw original XLSX/TXT files or write any file. The Compose mount remains `read-only` and the container has no added Linux capabilities. If index/manifest permission is inadequate, fail closed as `unavailable`; never make sources world-readable.

Production data confidentiality additionally requires a **separate volume or host-level permissions boundary for archived originals**. The versioned Lane C bundle retains original bytes for provenance verification during privileged install, but the application only needs the pinned live release metadata and SQLite. Do not grant a generic API service user blanket access to archived publisher content.

## Actual official source installation

From **the coordinator-reviewed revision** of the repository and a Python virtual environment with dependencies installed:
```bash
python -m pip install -r requirements-dev.txt
mkdir -p -m 700 /srv/facility-risk/incoming /srv/facility-risk/ingestion-qa
mkdir -p -m 700 /srv/facility-risk/source-index/lane-c
mkdir -p -m 700 /srv/facility-risk/source-index/phmsa-wms

# 17 NRC official workbooks + CSB current release, real validation and
# deterministic original/normalized SHA-256 + review-only SQL index.
python scripts/run_lane_c_verified.py \
  --output /srv/facility-risk/ingestion-qa/nrc-csb \
  --private-bundle-dir /srv/facility-risk/incoming/nrc-csb-20261023

python scripts/lane_c_install.py install \
  --bundle /srv/facility-risk/incoming/nrc-csb-20261023 \
  --root /srv/facility-risk/source-index/lane-c \
  --release-id nrc-csb-20261023-verified
python scripts/lane_c_install.py status \
  --root /srv/facility-risk/source-index/lane-c
python scripts/lane_c_install.py health \
  --root /srv/facility-risk/source-index/lane-c
python scripts/lane_c_install.py query \
  --root /srv/facility-risk/source-index/lane-c \
  --source nrc_2025 --state TX --since 2025-01-01 --page 1 --page-size 10

# PHMSA case source remains separate; NEVER add its cases to accident totals.
python scripts/probe_lane_c_phmsa_enforcement.py \
  --output /srv/facility-risk/ingestion-qa/phmsa \
  --private-bundle-dir /srv/facility-risk/incoming/phmsa-cases-20261023
python scripts/lane_c_enforcement_install.py install \
  --bundle /srv/facility-risk/incoming/phmsa-cases-20261023 \
  --root /srv/facility-risk/source-index/phmsa-wms \
  --release-id phmsa-wms-20261023-verified
python scripts/lane_c_enforcement_install.py query \
  --root /srv/facility-risk/source-index/phmsa-wms \
  --page 1 --page-size 10
```

File SHA/count/SQLite validation must pass **before** activating a new release. Installation into a versioned directory is immutable; `active-release.json` changes atomically only after successful checks. Serialize all install/rollback commands through a **single writer**. Preserve prior releases and test `lane_c_install.py rollback` / `lane_c_enforcement_install.py rollback`. If source schemas or hashes change, stop publication and record publisher source URL, HTTP status, validation failure and last good release. Do not overwrite verified releases or treat a blocked publisher as zero incidents.

## Bring up the authenticated backend

Use a private `.env` (ignored by Git, readable by authorized operator only) with independently generated strong credentials and **container-visible** roots:
```dotenv
FACILITY_RISK_AUTH_TOKEN=<generate unique unpredictable 32+ character secret>
FACILITY_RISK_REQUIRE_AUTH=1
FACILITY_RISK_PRIVATE_SOURCE_HOST_DIR=/srv/facility-risk/source-index
FACILITY_RISK_LANE_C_ROOT=/app/source-index/lane-c
FACILITY_RISK_PHMSA_WMS_ROOT=/app/source-index/phmsa-wms
FACILITY_RISK_ENABLE_WRITES=0
```
```bash
docker compose config >/dev/null    # verify external mount resolves correctly
docker compose up -d --build
# Service is intentionally bound to loopback 127.0.0.1:8765.
curl -fsS -H "Authorization: Bearer <secret>" \
  http://127.0.0.1:8765/api/source-indices/status
curl -fsS -H "Authorization: Bearer <secret>" \
  http://127.0.0.1:8765/api/industrial/status
curl -fsS -H "Authorization: Bearer <secret>" \
  'http://127.0.0.1:8765/api/industrial/observations?source=nrc_2025&state=TX&limit=10'
curl -fsS -H "Authorization: Bearer <secret>" \
  'http://127.0.0.1:8765/api/industrial/phmsa-enforcement?limit=10'
```

To independently inspect a **running** authorized backend without printing source rows, export the secret through an approved shell or secret manager and run:

```bash
# FACILITY_RISK_AUTH_TOKEN must be in the protected process environment;
# do not include it in command history or CI/public artifact URLs.
python scripts/verify_private_host_industrial.py \
  --base http://127.0.0.1:8765 \
  --expected-observations 429796 --expected-wms-cases 5089 \
  --output /srv/facility-risk/ingestion-qa/private-api-runtime-acceptance.json
```

This command confirms **actual mounted host** counts, separately classified WMS cases, unauthenticated 401, bearer service reviewer 403 and bounded native source queries. It refuses remote non-TLS URLs and produces aggregate-only output. Run again **after stopping/restarting** the service and restoring from an encrypted backup. A passing command is host-level API functionality, not insurer SSO/tenant-security approval or real physical-site corroboration.

API routes require the existing security middleware; uncredentialed requests return **401**. The cross-regulator **review-only** endpoint `/api/industrial/review-candidates` additionally requires an **individually authenticated reviewer/admin Basic account**, not a shared service token. No role or endpoint automatically promotes one report into a corroborated site/event/claim. Only selected source columns are returned; unrestricted original report JSON/free text stays private. Filters are parameterized, paginated, bounded, with source/index validation and SQL query timeout. Unconfigured/status-invalid indexes return `not_configured` / `unavailable`; data queries return **503**, not an empty fake incident census.

The **private app Source health** page shows a separate interactive NRC/CSB reporting-vintage browser and PHMSA case search when sources are really mounted. The **public GitHub Pages** page shows metadata/provenance only, never queries a secret or private index. This private UI cannot be tested by visiting GitHub Pages.

## Refresh and real deployment acceptance

- **Ingestion:** use scheduled external scheduler or operator on the approved VM, not GitHub Pages. Poll official NRC annual/current partial, CSB quarterly and WMS source, preserve original URL/bytes/hash/vintage, run source schema/identifier/join/coordinate/duplicate tests. Treat 2026 reporting vintage as partial; CSB June vs September `Number` is *not* immutable.
- **Storage:** keep `source-index` encrypted, authenticated service-only, read-only. Log every refresh/release pointer/audit failure. Back up and test restoration of source originals, release manifests and active pointers. Recheck source index after service restart; no active work should silently change past data or an approved site crosswalk.
- **Authentication:** Docker bearer/basic is **not enterprise SSO, claims-system tenancy or a public internet perimeter**. For insurer users, provision TLS, identity-aware reverse proxy, OIDC tenant-specific authorization, session/audit logging, rate limiting, and security review before exposing any public service. The code's `private_api_mounted=true` means authenticated software can read the index **on that host**, not that production customer deployment has been independently verified.
- **25-site acceptance:** select **25 real, authorized, independently reviewable physical insured premises across multiple industries**, with official industry/site identifiers and verified coordinates as applicable. For each, independently corroborate regulator/company/address/physical site identity, note whether source reporting covers that country/program, and have separate reviewer approval. A missing report is not low risk. Existing 25-sector **synthetic** negative tests prove no automatic site linking, *not* 25 real reviewed sites.
- **Outcome evidence:** NRC notifications, CSB release records and PHMSA enforcement actions are not insurance claim/loss records. Confirm real cause, damage, downtime/BI and applicable policy terms from independent records before computing underwriting indicators.
- **Production sign-off required:** record actual private host name (not in public repo), authenticated read-only GET test results, count/hash reconciliation, tenant/role restrictions, backup/restore test, service restart, live UI verification, expected update frequency and responsible owner. **Only then** report durable production records as deployed. Actions runner installations remain ephemeral. Original PHMSA accident/hazmat exports still need approved publisher access.

## Current verified boundary

Lane C successfully completed official-source, deterministic normalization and temporary read-only install SQL QA. Lane E regression tests and CI smoke validate API/UI code. **No private durable production host or external client deployment has been provisioned through GitHub, no real 25 insured-site review has occurred here, and primary PHMSA accident/hazmat incident coverage remains blocked by official HTTP 403/access restrictions.** Keep production-deployed records at **0** until actual independent deployment verification.
