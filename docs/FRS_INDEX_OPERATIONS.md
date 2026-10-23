# Operational runbook: indexed all-industry source discovery

This runbook covers the **public-authority EPA FRS national source identity index**,
not verified insured properties, geocoded property parcels or a completed insurance
risk model. GitHub Pages remains public and static: it does not host the 5M+ index.

## Automated source-to-index chain

1. **EPA FRS national source staging** runs weekly on Monday (and can be manually
   dispatched). It retrieves the official bulk EPA national file, rejects
   incomplete imports, records the download/output SHA-256 fingerprints and
   publishes a **source-only** artifact for 14 days.
2. After a successful stage, **Validate full EPA FRS indexed database** starts
   automatically via GitHub Actions `workflow_run`; the index job downloads
   the *actual upstream run's artifact*. There is **no hardcoded stale run ID**.
3. The index job checks source completeness (minimum five million valid
   official identities, valid + rejected = read, 64-char hashes), loads each
   into indexed SQLite FTS5, checks `PRAGMA quick_check`, performs real
   indexed source-ID/name search, and runs the search benchmark.
4. The job publishes `epa-frs-indexed-registry` containing a public-source-only
   SQLite database, QA JSON and search benchmark JSON. These are **temporary**
   GitHub Actions artifacts (currently 7-day retention). Each run's workflow
   logs show the precise source vintage and observed counts.

The index build refuses partial or unexpectedly small cohorts. It does **not**
pretend the source has a fixed unchanging 2026 row count. When source counts
change materially, investigate before replacing any approved production
snapshot.

## What is measured

`scripts/benchmark_frs_search.py` executes an actual set of identity/name,
country, source-ID prefix and paging lookups through the same
`universal_registry.search` logic used by the private API. It records sample
p50/p95 milliseconds, counts, warm query sample timings, parallel read-only
worker latency, SQLite bytes and runner process peak RSS.

Metrics are GitHub shared-runner observations, **not production SLOs** or
capacity/load tests against an internet service. They must not be fabricated
or silently reused for a later source vintage. No insurance risk, premium,
covered property or payout is inferred.

To run an independent benchmark against a previously imported **source-only**
SQLite file:

```sh
python scripts/benchmark_frs_search.py /secure/source-only-frs-index.sqlite \
  --out /secure/frs-benchmark.json --repeats 3 --concurrency 4
```

## Putting the index on a durable private host (external deployment gate)

The validated Actions ZIP alone is not persistent hosting. A separately
controlled Linux or Windows server / VM, encrypted volume, real backups and
authenticated HTTPS entrypoint are required to serve external users.

1. Obtain the latest successful `epa-frs-indexed-registry` artifact from the
   exact index workflow run, together with its upstream source manifest.
   Verify the GitHub run's success and JSON row counts; check hashes on the
   transferred artifact as part of the controlled change process.
2. Extract **only into a new empty private data volume**. Use a dedicated
   source-discovery database or make a fully audited migration plan before
   combining with another research database. **Never overwrite an existing
   `facility_risk.sqlite` containing analyst notes, insurance terms, review
   approvals or client records**.
3. Point a separately controlled private deployment's `FACILITY_RISK_DB`
   to the staged source-only SQLite. The public-source search endpoints are
   `GET /api/universal-facilities`, `/{id}`, and `/stats`, available only
   behind the application's private authentication boundary. Keep direct port
   8765 bound to localhost; provision TLS, access logs, encrypted backups,
   rate limits, SSO and tenant isolation before any insurer/client data.
4. Query name and exact source ID, compare API `/stats` to QA JSON, verify
   `/api/health` and a negative/unknown search. Record backup restore and
   rollback acceptance before swapping snapshots.
5. For ongoing refresh, stage the next validated database, test on a
   separate port/database, then use an operator-controlled atomic cutover
   after quiescing reads. Preserve historical source files, source dates,
   audits and client workspaces according to retention policy.

The current GitHub integration cannot provision, finance or authenticate a
durable host or transfer artifacts to an undisclosed private VM. Treat
**production hosting, SSO/tenant scoping and disaster recovery as BLOCKED
external deployment gates** until their configurations are reviewed.

## What is not ready

- Source identities are not deduplicated into real-world parcels/buildings;
  any merge requires distinct reviewers and original corroborating evidence.
- Source latitude/longitude is **not** property-verified. Hazards must not be
  attached to unreviewed coordinates.
- EPA is primarily a U.S. source and does not cover every global facility;
  other regulator and authorized-place cohorts remain separate.
- Public Pages and the FRS source index must never contain private insured
  facilities, claims, confidential policies, access tokens or personal contacts.
- End-to-end insured-property hazard, utility-dependency, geopolitical and
  policy-contract assessment remains a distinct validation programme.

See `docs/SECURE_DEPLOYMENT.md`, `docs/UNIVERSAL_FACILITIES.md` and
issues #39 (production search), #40 (insurance coverage), #41 (drug country)
for the remaining acceptance criteria.

## Fail-closed private source-only index installation

The private deployment has a safe local installer for an **already validated**
GitHub Actions index and its matching QA file. It does not download GitHub
artifacts, provision any server, copy insurance policies or configure SSO.

After inspecting a successful `epa-frs-indexed-registry` artifact and making
a separate secure, empty volume:

```sh
python scripts/install_frs_source_index.py \
  --source /secure/staging/full-frs-index.sqlite \
  --qa /secure/staging/full-frs-index-qa.json \
  --target /secure/facility-search/public-source-index.sqlite
```

The installer checks the original source/normalized SHA-256 fields in the QA
manifest, counts, original validation status, transfer integrity via SQLite
`quick_check`, that only EPA FRS identities were indexed, and that no
client/private research, review, claims or policy rows are stored. It writes to
a temporary file in the target directory and creates the final file using an
exclusive hard link, **refusing to overwrite an existing file** even in a
concurrent install attempt. Destination directories must exist and be secured
by the operator first.

A successful installation is **not** an operational deployment. Only after
separately configuring an authenticated private API, persistent storage,
backup/restore tests and firewall/TLS controls should the operator make the
index available to appropriately authorized users. The benchmark remains a
separate measurement of search performance on each full official source import.
