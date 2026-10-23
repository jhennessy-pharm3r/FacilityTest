# EPA Lane B — private host deployment and source-bundle recovery

**Scope:** EPA ECHO, RCRAInfo, TRI Basic 1987–2024, and the public EPA FRS-RMP program-interest layer. Every industry and facility type is in scope. Source IDs are **not independently verified physical insured facilities, events, or insurance claims**.

**Status 2026-10-23:** [Lane B merged PR #76](https://github.com/jhennessy-pharm3r/FacilityTest/pull/76); coordinator [PR #82](https://github.com/jhennessy-pharm3r/FacilityTest/pull/82) integrates read-only routes/UI. [Full end-to-end official-source SHA/replay evidence](../scripts/lane_b_epa/INTEGRATION_RELEASE.md). All source artifacts existed in GitHub Actions at last check, but **no attached durable private host, encrypted source volume, backups, network TLS/SSO/tenancy, or production risk-case site review have been supplied or verified**. Actual persistent production-deployed records **0**. This document is an executable operator runbook, **not evidence of a completed deployment**.

## 1. Recover exact official source artifacts before expiry

Use an **operator-controlled Linux host with encrypted, backed-up private storage**, GitHub CLI authenticated to `jhennessy-pharm3r/FacilityTest`, Python 3.11+, and sufficient free disk for original archives + decompressed indexes + rollback. Allow **at least 50–60 GB free** for this EPA set plus temporary transfer headroom; size to actual producer artifacts and existing FRS/NOAA data. Retention differs per run (historical source artifacts were uploaded with only 3-day retention). After expiry, re-run official-source ingestion and verify new source/vintage and hashes; **never claim an old snapshot was recovered from a newer publisher download**.

On the private host, create a restricted directory outside the repository:

```bash
umask 077
mkdir -p /srv/facilityrisk/private-archives/epa-20261023
cd /srv/facilityrisk/FacilityTest
gh auth status
# DO NOT copy resulting data files into Git, Pages, or /app/data/insured workspace.
```

ECHO (single national official ZIP + 3 SQLite-index chunks + matching manifests):

```bash
A=/srv/facilityrisk/private-archives/epa-20261023
gh run download 39982893655 -R jhennessy-pharm3r/FacilityTest -n lane-b-echo-official-raw-zip -D "$A/echo/raw"
gh run download 39982893655 -R jhennessy-pharm3r/FacilityTest -n lane-b-echo-complete-manifests -D "$A/echo/meta"
for n in 000 001 002; do
  gh run download 39982893655 -R jhennessy-pharm3r/FacilityTest -n "lane-b-echo-index-part-$n" -D "$A/echo/parts"
done
```

RCRAInfo (single national ZIP + 2 full-index chunks + matching manifests):

```bash
gh run download 39982893655 -R jhennessy-pharm3r/FacilityTest -n lane-b-rcra-official-raw-zip -D "$A/rcra/raw"
gh run download 39982893655 -R jhennessy-pharm3r/FacilityTest -n lane-b-rcra-complete-manifests -D "$A/rcra/meta"
for n in 000 001; do
  gh run download 39982893655 -R jhennessy-pharm3r/FacilityTest -n "lane-b-rcra-index-part-$n" -D "$A/rcra/parts"
done
```

TRI Basic (original annual source CSV, compressed SQLite and matching provenance for **all 38 complete official reporting years**):

```bash
for YEAR in $(seq 1987 2024); do
  if [ "$YEAR" -le 2019 ]; then
    RUN=39985627343
    SRC="lane-b-tri-historical-$YEAR-source-index"
    META="lane-b-tri-historical-$YEAR-qa"
  else
    RUN=39980692415
    SRC="lane-b-tri-$YEAR-source-index-staging"
    META="lane-b-tri-$YEAR-qa"
  fi
  gh run download "$RUN" -R jhennessy-pharm3r/FacilityTest -n "$SRC" -D "$A/tri/tri_$YEAR/source"
  gh run download "$RUN" -R jhennessy-pharm3r/FacilityTest -n "$META" -D "$A/tri/tri_$YEAR/meta"
done
```

Public RMP registry (only **public FRS program-interest records**, never restricted plans/OCA):

```bash
gh run download 39981171808 -R jhennessy-pharm3r/FacilityTest -n lane-b-public-frs-rmp-source-only-index -D "$A/rmp"
```

**Immediate archive gates:** confirm every artifact downloaded without truncation; original national URLs, source-year counts, hashes and distinct key semantics must agree with [integration ledger](../scripts/lane_b_epa/INTEGRATION_RELEASE.md). ECHO ZIP SHA `116f6e53117b52f7891c6d2466d662f4ee5e29946b065fdb7b97eaf095615899`; RCRA ZIP SHA `babf48b1e2388b7f27cfc186cb1e9eb0ecfa26f53476fc81908712e41dfe09f3`; matching public RMP raw JSONL SHA `c86acb52b94cac31b0e3c725591e345743c0193261b7f22ac03a18339c162d76`. All 38 original TRI CSV SHA hashes are in the two annual validation ledgers. Never combine RMP JSONL/index from different producer runs.

## 2. Install source-only immutable snapshots

All bundle installers check the supplied **original publisher file SHA**, full SQLite hash and counts, require a NEW versioned directory, refuse overwrites and keep source rejections independently. Relative paths of restored artifacts can vary; run `find "$A" -name 'echo.manifest.json'` etc. and provide the paths to the actual files retrieved together.

```bash
cd /srv/facilityrisk/FacilityTest
mkdir -p source-index/epa-tri

python -m scripts.lane_b_epa.install_snapshot --source echo \
  --official-zip "$A/echo/raw/echo_exporter.zip" \
  --manifest "$A/echo/meta/echo.manifest.json" \
  --parts-dir "$A/echo/parts" \
  --chunks-manifest "$A/echo/meta/chunk-manifest.json" \
  --destination source-index/epa-echo-20261023

python -m scripts.lane_b_epa.install_snapshot --source rcra \
  --official-zip "$A/rcra/raw/rcra_downloads.zip" \
  --manifest "$A/rcra/meta/rcra.manifest.json" \
  --parts-dir "$A/rcra/parts" \
  --chunks-manifest "$A/rcra/meta/chunk-manifest.json" \
  --destination source-index/epa-rcra-20261023

# For 2024 only, repeat each year 1987–2024, choosing its unique original CSV, gzip and manifest.
python -m scripts.lane_b_epa.install_auxiliary tri --year 2024 \
  --official-csv "$A/tri/tri_2024/source/tri_2024_US.csv" \
  --index-gz "$A/tri/tri_2024/source/tri.sqlite.gz" \
  --manifest "$A/tri/tri_2024/meta/tri.manifest.json" \
  --destination source-index/epa-tri/tri_2024

python -m scripts.lane_b_epa.install_auxiliary rmp-public \
  --original-jsonl "$A/rmp/rmp_frs_public.raw.jsonl" \
  --index "$A/rmp/rmp_frs_public.sqlite" \
  --manifest "$A/rmp/rmp_frs_public.manifest.json" \
  --destination source-index/epa-rmp-public-20261023
```

**All 38** TRI year directories, both national source bundles and public RMP must pass installation before enabling a complete-cohort mount. Old immutable snapshot versions are retained for rollback. Do not register partial-year TRI as full 1987–2024 coverage.

### Container UID permissions — tested against an actual official index

The private Docker image runs as **UID:GID 10001:10001** (not root). The source installers intentionally seal newly created snapshot directories as 0700, so an owner installed as a different host user must **explicitly transfer ownership**, without making original sources world-readable.

```bash
cd /srv/facilityrisk/FacilityTest
sudo chown -R 10001:10001 source-index
sudo find source-index -type d -exec chmod 750 {} +
sudo find source-index -type f -exec chmod 440 {} +
```

`compose.yaml` mounts `./source-index` under `/app/source-index:ro`, separately from the writeable insured-research `./data` directory. The actual nonroot Docker test [run 40004791507](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/40004791507) verified source SHA, real RMP program-ID query and HTTP 200/401/403/503 with `--read-only`, source-only read-only volume, no additional container capabilities. That was CI, **not your production server**.

## 3. Enable private API and validate the host

Keep `.env` untracked. Its key source-only settings inside the container are:

```dotenv
FACILITY_RISK_LANE_B_ROUTES_ENABLED=1
FACILITY_RISK_LANE_B_ECHO_DIRECTORY=/app/source-index/epa-echo-20261023
FACILITY_RISK_LANE_B_RCRA_DIRECTORY=/app/source-index/epa-rcra-20261023
FACILITY_RISK_LANE_B_TRI_ROOT=/app/source-index/epa-tri
FACILITY_RISK_LANE_B_TRI_YEARS=1987-2024
FACILITY_RISK_LANE_B_RMP_DIRECTORY=/app/source-index/epa-rmp-public-20261023
```

Before external access, provision **TLS/SSO identity-aware proxy, service-auth, individual reviewer+approver credentials/tenant separation, encrypted storage and restore-tested backups**. `FACILITY_RISK_ENABLE_WRITES=0` initially, until policy/site review workflow is independently audited. Bind only `127.0.0.1:8765` on the server; access externally only through the approved proxy or VPN, **never expose this port directly**.

```bash
docker compose build facility-risk
docker compose up -d --no-deps facility-risk
docker compose ps
# On an authenticated operator shell, verify private source status and source-native ID query.
curl -fsS -u 'analyst:<private-password>' http://127.0.0.1:8765/api/epa/lane-b/status
curl -fsSG -u 'analyst:<private-password>' --data-urlencode 'native_id=<actual-official-RMP-program-ID>' \
  http://127.0.0.1:8765/api/epa/lane-b/rmp_public/identity
```

Replace illustrative IDs/password tokens with **real private operator inputs**, never commit them. The API is part of the existing FastAPI app and is **disabled** with `FACILITY_RISK_LANE_B_ROUTES_ENABLED=0`; if source snapshot is missing/unvalidated, return `unavailable` and 503. Anonymous data routes return 401; unauthorized original raw attributes return 403. UI: **Research → EPA regulatory evidence** (the private app; public Pages is *only* a static research preview).

Verify against official manifest: **ECHO 3,208,008 accepted + 21,303 source-key quarantined; RCRA 7,022,589 table records; TRI 3,218,093 chemical filings across 38 annual partitions; public RMP 21,853 programme interests**. A valid mounted-source status is **not proof of production insurer deployment, complete U.S. facility census, injury, property exposure, or loss**. Record separately the host URL, real service SHA/vintage, TLS/SSO readiness and independent physical property review.

## 4. Atomic refresh, backup, rollback, and release gate

- Always download **fresh official source**, hash **original bytes**, preserve prior source ZIP/CSV/JSONL and QA; compare downloaded vs accepted/rejected and native-key/geometry source changes before approving a replacement.
- Create a **new versioned source directory**. Never write into a currently mounted immutable SQLite (no WAL mutation).
- Quiesce/restart readers for environment-path change, verify the newly mounted source status and exact-ID queries, then independently review any source-to-physical-property crosswalk. Retain prior snapshot and original source bytes for rollback.
- On a failure, restore previous env paths, restart only the private service and verify the previous manifest/count/source IDs; do not overwrite or silently substitute a smaller dataset.
- Public Source Health must distinguish **downloaded → normalized → temporary indexed → private mounted → independently verified production deployed**; newly merged code does **not** change production-deployed from zero.
- External client release remains **BLOCKED** until authenticated TLS/SSO/tenancy, secure hosting, backed-up source data, exact API QA, and >=25 independently corroborated cross-industry physical-property match tests are signed off. Source-key join candidates or geographic proximity are not human-verified property identities.
- Restricted RMP plans/offsite-consequence data were not authorized for bulk; TRI Basic 2025 endpoint returned HTTP 404 in verified source probe and is **unavailable, not zero TRI activity**.

For upstream raw provenance, see [Lane B complete handoff](../scripts/lane_b_epa/INTEGRATION_RELEASE.md). For hosting hard requirements see [issue #39](https://github.com/jhennessy-pharm3r/FacilityTest/issues/39), [secure deployment](SECURE_DEPLOYMENT.md) and coordinator [issue #73](https://github.com/jhennessy-pharm3r/FacilityTest/issues/73).
