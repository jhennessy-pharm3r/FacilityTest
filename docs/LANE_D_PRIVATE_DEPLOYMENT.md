# Lane D private production integration: operator runbook

Updated 2026-10-23. Source PR #77 and stacked coordinator integration PR #83 are not merged. Running a GitHub Actions test does not provision a persistent server. This document defines the exact private-host installation and validation steps. All industries and facility types are in scope; source records are never automatically insured premises, paid claims or insured outages.

## Validated source packages and known counts

| Publisher/version | Original source SHA-256 | Accepted | Rejected | CI read-only source index |
| --- | --- | ---: | ---: | --- |
| EIA-861 final 2025 | f59f6c732bf685fe0a1591b32227f5ce572dc0dfd26bb5caaeed128ac4e3a396 | 12,923 | 3 | ff0b25fac8f0fb2508b598ec4aea5697481a854509e4d77ba24b5685611de39b |
| DOE/PNNL historical 2014-2023 | 44557bae7a5c8e02c611a14f75fe9e123d81d286f700b9fd88ac538edd910fe7 | 2,124,183 | 0 | 353b0ce39a0232341054c5cf7fc55228c1d069924bb15e58b597cb5aa0e140af |
| DOE OE-417 annual 2023 discovery, public domain | 5329d272544e9164692f08b34a5079d3f89a2095f1a77a8fa8dfca8923b06d18 | 341 | 0 | f7d13108d3ed9f0ee7bebfc7d152c20d2209b704ac395b68721257456f753957 |

PNNL original source contains 277,360 repeated complete source rows, preserved with original source-line lineage. Correlated rows, lag sensitivity and state-month aggregates are not additive county outages; 2,124,183 is not a count of unique outages. DOE annual and EIA EPM disturbance data may overlap. Thirty-two DOE OE-417 rows have unknown event start dates. ORNL current /odi changes between snapshots and is disabled from private serving pending applicable commercial-use rights.

Actual source/transfer/index QA:
- EIA-861: https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39999761323
- PNNL: https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39999800430
- DOE OE417: https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/40001818924
- Original source/schema/vintage details: docs/lane_d_integration_handoff.md

## 1. Provision real private and backed-up storage

A controlled Linux server/VM, managed persistent storage and encrypted off-host backup must exist before declaring production deployment. Minimum suggested free disk headroom for source rebuild/transfer/installation: 15 GiB, with additional space and growth allowance for originals, backup snapshots and client data. Make separate restricted paths such as:

    /srv/facilityrisk/source-index/lane-d/
    /srv/facilityrisk/source-archives/lane-d/
    /srv/facilityrisk/private-workspace/
    /secure/transfers/

Do not store original source rows, insured/client research, credentials or SQLite indexes in the public repository or GitHub Pages. Persist original published EIA/PNNL ZIPs and DOE OE417 original JSON plus publisher metadata with SHA-256 manifests and exact source vintage. All serving indexes use immutable, versioned SQLite and read-only mounts, distinct from the client's mutable research database.

## 2. Acquire the exact original validated source-index handoffs

Use an authorized GitHub CLI on the private server (artifacts expire in about three days). When expired, rerun the SOURCE importer from the approved pinned original government URLs, reconcile against the original checksum and create a new validated handoff. A new publisher SHA requires a fresh review, never a silent replacement.

    gh run download 39999761323 --repo jhennessy-pharm3r/FacilityTest -n lane-d-eia861-2025-readonly-staging-index -D /secure/transfers/eia
    gh run download 39999800430 --repo jhennessy-pharm3r/FacilityTest -n lane-d-pnnl-2014-2023-readonly-staging-index -D /secure/transfers/pnnl
    gh run download 40001818924 --repo jhennessy-pharm3r/FacilityTest -n lane-d-oe417-2023-public-domain-readonly-staging-index -D /secure/transfers/oe417

Each transferred bundle must contain the native source-only SQLite, its manifest.json and coordinator_handoff.json. If missing or differing from an independently expected SHA, do not install.

## 3. Install, verify and test the source-only indexes

From the reviewed Python 3.12 repository checkout and on the protected host:

    umask 077
    python -m facilityrisk.lane_d.install_source_index install --bundle /secure/transfers/eia --dest /srv/facilityrisk/source-index/lane-d --dataset eia861_2025 --source-sha256 f59f6c732bf685fe0a1591b32227f5ce572dc0dfd26bb5caaeed128ac4e3a396 --index-sha256 ff0b25fac8f0fb2508b598ec4aea5697481a854509e4d77ba24b5685611de39b --role private-backend-candidate
    python -m facilityrisk.lane_d.install_source_index install --bundle /secure/transfers/pnnl --dest /srv/facilityrisk/source-index/lane-d --dataset pnnl_2014_2023 --source-sha256 44557bae7a5c8e02c611a14f75fe9e123d81d286f700b9fd88ac538edd910fe7 --index-sha256 353b0ce39a0232341054c5cf7fc55228c1d069924bb15e58b597cb5aa0e140af --role private-backend-candidate
    python -m facilityrisk.lane_d.install_source_index install --bundle /secure/transfers/oe417 --dest /srv/facilityrisk/source-index/lane-d --dataset oe417_annual_public --source-sha256 5329d272544e9164692f08b34a5079d3f89a2095f1a77a8fa8dfca8923b06d18 --index-sha256 f7d13108d3ed9f0ee7bebfc7d152c20d2209b704ac395b68721257456f753957 --role private-backend-candidate
    python -m facilityrisk.lane_d.install_source_index verify --dest /srv/facilityrisk/source-index/lane-d --dataset eia861_2025
    python -m facilityrisk.lane_d.install_source_index verify --dest /srv/facilityrisk/source-index/lane-d --dataset pnnl_2014_2023
    python -m facilityrisk.lane_d.install_source_index verify --dest /srv/facilityrisk/source-index/lane-d --dataset oe417_annual_public

The installer checks trusted original-source SHA, manifest/receipt, original acceptance/rejections and source kinds, required source ID columns, duplicate flags, SQLite size and complete integrity. It copies into dataset/versions and atomically moves current.json only after validation. Invalid source, active writer, changed digest or bad schema fails closed. An identical version re-install is idempotent. To roll back, re-install the original independently accepted version with its pinned original source SHA; do not overwrite SQLite by hand.

## Extra review-only first-party issuer business-interruption evidence

The private API can independently serve original first-party disclosures from Crane Company and Pebblebrook Hotel Trust as two separate reviewed case-study indexes. **These are not national insurer claims, insured premises or meter outages.** First-party Crane original 2024 annual and 2025 Q2 quarterly PDFs have 7 typed accounting observations (2 documents), with the issuer reporting USD 4,000,000 received for lost profits in Q2 2025. Other financial figures are property-damage expenses/recoveries/receivables under different reporting periods. First-party Pebblebrook 2024/2025 year-end investor publications have 5 typed accounting observations (2 documents), including FY2024 Hurricane Ian USD 23,800,000 recognized BI insurance income and FY2025 Helene/Milton USD 12,700,000 recognized BI income. Quarterly amounts are **already included in annual**, and recognized income alone does not establish a carrier-confirmed paid claim.

The financial source installer validates exact original first-party document URLs/SHA-256 signatures, issuer CIK, every typed accounting figure, annual/quarter/cumulative source period, SQL row identity and absence of independent insured-site/claim verification. It fails closed on any new/changed unreviewed document.

After reviewing data use terms and installing the separate pypdf PDF parser on an authorized private host:

    python -m facilityrisk.lane_d.ingest_crane_bi_pdf --output /secure/transfers/crane --min-sources 2
    python -m facilityrisk.lane_d.ingest_pebblebrook_bi --output /secure/transfers/pebblebrook --min-sources 2
    python -m facilityrisk.lane_d.install_issuer_financial install --bundle /secure/transfers/crane --dest /srv/facilityrisk/source-index/lane-d/issuer_financial --case crane
    python -m facilityrisk.lane_d.install_issuer_financial install --bundle /secure/transfers/pebblebrook --dest /srv/facilityrisk/source-index/lane-d/issuer_financial --case pebblebrook
    python -m facilityrisk.lane_d.install_issuer_financial verify --dest /srv/facilityrisk/source-index/lane-d/issuer_financial --case crane
    python -m facilityrisk.lane_d.install_issuer_financial verify --dest /srv/facilityrisk/source-index/lane-d/issuer_financial --case pebblebrook

An issuer page digest or amount drift blocks the install, pending another official-source audit. Query the authenticated GET /api/source-context/issuer-bi?issuer=Crane%20Company or Pebblebrook%20Hotel%20Trust. The response preserves issuer-reported facts without insurer/policy verification. Its installed-source status appears separately in issuer_bi_financial_context; do not use it as a verified insured claim or underwriting rating.

## 4. Run the authenticated private backend using persistent mounts

In an UNTRACKED .env or managed secrets, configure:

    FACILITY_RISK_AUTH_TOKEN=<operator-created-random-secret-32plus>
    FACILITY_RISK_REQUIRE_AUTH=1
    FACILITY_RISK_ENABLE_WRITES=0
    FACILITY_RISK_SOURCE_INDEX_HOST=/srv/facilityrisk/source-index
    FACILITY_RISK_LANE_D_INDEX_ROOT=/app/source-index/lane-d
    FACILITY_RISK_LANE_D_ODIN_USE_APPROVED=0

The existing Compose server listens on host 127.0.0.1:8765 and mounts the source index read-only under /app/source-index. UID 10001 runs the private container.

**Actual Docker permission gate:** the versioned source installer creates owner-only directories (0700); SQL files are read-only (0444). After verified source installation on an approved Linux host, grant the unprivileged container UID 10001 ownership/traversal before Docker startup:

    sudo chown -R 10001:10001 /srv/facilityrisk/source-index/lane-d
    sudo chown -R 10001:10001 ./data

Keep source-index directory restricted to authorized operators and backed up, with the application bind mount explicitly read-only (:ro). The mutable insured workspace stays separate. An earlier Docker smoke exposed missing container rights to owner-only source-index directories; granting UID10001 ownership fixes access without granting mutable source storage inside the container. Do not use global-write permissions.
 Remote customers require separate HTTPS/VPN, tenant-scoped identity-aware proxy and role authorization; a shared bearer token by itself is **not enterprise client-grade SSO**.

    docker compose up --build -d
    docker compose ps
    python scripts/verify_lane_d_live_service.py --base-url http://127.0.0.1:8765 --output /secure/qa/lane-d-live-api.json

The verifier reads FACILITY_RISK_AUTH_TOKEN from environment and does not log it. It checks HTTP 401 for unauthenticated access, the three pinned government source row counts, EIA WA/Pierce 15 provider candidates, a real PNNL FIPS query, DOE 2023 309 dated reports, and ORNL rights gating. It intentionally does not attest site connection, insurer payment, public Pages deployment, persistent disk or backup recovery.

## 5. Private API endpoints and honest Source Health

- GET /api/source-context/lane-d/status: original publisher SHA and verified *private mounted index* counts, not publicly deployed physical facilities.
- GET /api/source-context/utility-candidates?state=WA&county=Pierce: 2025 reported EIA utility presence candidates (not a particular property's electric account).
- GET /api/source-context/historical-outages?county_fips=48201: 2014-2023 county episodes only; no insured building downtime imputed.
- GET /api/source-context/annual-electric-disturbances?year=2023: source DOE annual reporting records; EIA EPM overlaps.
- GET /api/source-context/current-outages?county_fips=48201: returns 503 until rights-approved first-party ORNL snapshot is installed and explicit source-use review gate enabled.
- GET /api/source-indices/status: includes authenticated Lane D source-index status; no false public GitHub Pages deployed values.
- GET /api/source-context/issuer-bi?issuer=Crane%20Company: reviewed issuer-published financial accounting observations with period and original SHA. Not insurer-confirmed paid claims.

A configured but invalid/corrupt index must return 503 or unavailable; never treat missing evidence as zero risk. Every response preserves source-vintage identity and explicitly negates claims of verified insured meter, paid claim and actual insured loss.

## 6. Backup, restore and operational approval

Use encrypted **off-host** backup with an independently held secret, e.g. restic configured through the host secret manager (never check in actual backup credentials):

    restic backup /srv/facilityrisk/source-index/lane-d /srv/facilityrisk/source-archives/lane-d
    restic snapshots
    restic restore latest --target /secure/isolated-restore-test

Then verify all three restored installed-index version roots from the restored tree using the same SHA/integrity read-only verify and source queries; record date, restore location and outcome. Do not claim backup success based only on a backup command or GitHub Actions artifact. The authorized host operator must demonstrate restore and configure scheduled monitoring for stale/missing sources, protected storage, TLS, OIDC, storage alerting and backup retention.

PNNL OEDI declares CC BY 4.0; credit Buxin She, Veronica Adetola and Ji Young Yun (2024), link license, mark changes. DOE OE417 metadata declares Public Domain. ORNL ODIN current /odi may be publicly queryable, but **commercial serving/redistribution requires publisher-specific rights confirmation** and remains disabled by default.

Before a claim underwriter sees source-level evidence in the private app, the facility identity and original site geometry require independent site review. Actual verified service-provider/meter matches **0**; independently proven insured building power outages **0**; carrier-confirmed paid BI claims **0**. No source-only record authorizes changing those values.

## 7. Coordinator merge and deployment approval

PR #77 is a source package; PR #83 is a *stacked* private serving adapter. Independent coordinator should review and merge PR #77 first, retarget PR #83 to main, rerun full CI, official-source real-backend smoke and hosted service checks. Only after a durable private backend is provisioned, mounted sources/backup restore tested and auth/tenant/browser reviewed should the relevant Source Health state change to deployed. **Do not self-merge the ingestion PR, and do not mark GitHub Pages deployed from CI.**
