# Lane C — Production Integration Handoff (Coordinator Lane E)

**State: SOURCE PACKAGE VALIDATED; AUTHENTICATED PRODUCTION INTEGRATION NOT DEPLOYED.**
Owner: Lane C, dedicated [draft PR #79](https://github.com/jhennessy-pharm3r/FacilityTest/pull/79). Coordinator: [Issue #73](https://github.com/jhennessy-pharm3r/FacilityTest/issues/73). Scope is **every facility type and industry**, subject only to the reporting jurisdiction of each regulatory source. Do not merge automatically or mutate shared facilities/Source Health/UI in Lane C. This is a **read-only, source-observation** package—not an authoritative register of physical insured premises, unique accidents, financial claims or facility loss exposure.

## 1. Evidence and independent stage counts

| Official reporting universe, native grain | Original observed rows | Accepted normalized | Rejected | Indexed in *ephemeral* Actions SQLite | Durable authenticated production indexed | Live application deployed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| USCG NRC CY2010–CY2026, annual received-notification master `SEQNOS` | 429,122 | **429,122** | 0 | **429,122** | **0** | **0** |
| CSB 2026-09-01 accidental-release release-specific rows | 675 | **674** | 1 undated row | **674** | **0** | **0** |
| **NRC + CSB current release, source-only observation index** | **429,797** | **429,796** | **1** | **429,796** | **0** | **0** |
| PHMSA Work Management System enforcement **case** rows (different grain) | 5,089 | **5,089** | 0 | **5,089 separately** | **0** | **0** |
| CSB 2026-06-01 historical release snapshot (not 651 extra accidents) | 652 | 651 | 1 undated row | release comparison only | **0** | **0** |
| PHMSA pipeline accident/incident operator ZIP and transport DOT 5800.1 hazmat reports | **NOT DOWNLOADED** | **NOT TESTED** | **NOT TESTED** | **NOT TESTED** | **0 AVAILABLE** | **0** |

**Data vintages / evidence:** [full official-source run 39985606674](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39985606674), [real 18-source bundle/SQL integrity run 39987550790](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39987550790) and aggregate [QA artifact 12516906139](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39987550790/artifacts/12516906139); [PHMSA first-party enforcement run 39985148724](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39985148724), [CSB June/September revision comparison 39985969191](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39985969191). Full per-year raw byte counts, **all original source URL and SHA-256 values, all normalized SHA-256 values, observed incident date ranges and geographic coverage**: [Lane C validated-source ledger](lane-c-industrial-incidents.md). The 2026 NRC workbook is *provisional*, not a final annual total. Audit includes **62,276 valid source-reported NRC DMS coordinates**, **366,846 without valid DMS**, **422 missing/ambiguous NRC child links** and **three undatable NRC masters**. The September CSB report has no normalized native coordinates. Original reported severity values are not a confirmed insured loss. NRC received-notification year is not necessarily incident year. Source IDs are always reporting-vintage scoped.

## 2. Required private host and reproducible source installation

**Do not run this on GitHub Pages or inside a public checkout.** Use a pre-provisioned encrypted filesystem accessible to an explicitly authorized ingestion operator and read-only backend service; secure at-rest keys, tenant/auth controls, audited access, retention, backups and incident-response plan are Lane E responsibilities. Files contain potentially sensitive original report text and identifying information. Do not expose original workbooks/SQLite in public CI artifacts or unauthenticated HTTP responses.

Execute from the checked-out PR branch on a network-capable authorized host with Python and dependencies installed:

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt openpyxl requests
python -m pytest -q tests/test_industrial_incidents.py tests/test_nrc_enriched.py tests/test_csb_release.py tests/test_lane_c_index.py tests/test_lane_c_candidates.py tests/test_lane_c_private_handoff.py tests/test_lane_c_install.py

# Change these to the operator's actually protected private mount:
mkdir -p -m 700 /srv/facility-risk/ingest-qa
mkdir -p -m 700 /srv/facility-risk/incoming
mkdir -p -m 700 /srv/facility-risk/lane-c

# Download REAL upstream files and validate master/child source IDs,
# accepted/rejected counts, geography, source SHA, repeated gzip SHA,
# merged temporary SQLite, exact source-only candidate link checks.
# Keep the original XLSX and normalized GZIP in an authorized PRIVATE bundle.
python scripts/run_lane_c_verified.py \
  --output /srv/facility-risk/ingest-qa \
  --private-bundle-dir /srv/facility-risk/incoming/lane-c-20261023

# Install a checksum-verified versioned source release *outside* the repo.
# Installer verifies all 18 publisher raw/normalized SHA-256 values, manifests,
# native source namespaces, indexed row counts, candidate status and SQLite.
# It creates a sealed read-only release, then atomically changes the active pointer.
python scripts/lane_c_install.py install \
  --bundle /srv/facility-risk/incoming/lane-c-20261023 \
  --root /srv/facility-risk/lane-c \
  --release-id lane-c-20261023
python scripts/lane_c_install.py status --root /srv/facility-risk/lane-c
python scripts/lane_c_install.py query \
  --root /srv/facility-risk/lane-c \
  --source nrc_2025 --state TX --since 2025-01-01 --page 1 --page-size 25
python scripts/lane_c_install.py query \
  --root /srv/facility-risk/lane-c \
  --source csb --page 1 --page-size 10

# To revert an approved release, switch the verified pointer atomically:
python scripts/lane_c_install.py rollback \
  --root /srv/facility-risk/lane-c \
  --release-id lane-c-previous-verified
```

Use a release ID that actually exists for rollback; **never** overwrite an existing immutable release. If a source fails or a digest changes without an approved new publisher vintage, abort installation, leave the *last known-good* active pointer untouched, escalate and investigate. Installer writes **no public credentials or authenticated API** and intentionally returns app-deployed **0**; Lane E must verify genuine persistence across process/server restarts and provision a serving account with **filesystem read access only**. Successful staging inside an ephemeral GitHub runner does **not** mean production indexing/deployment. CI's `--install-test-root` option validates copy/installation/query using a private runner mount, then erases the rehearsal. It is explicitly **NOT** persistent production.

## 3. Physical data model and read-only query contract

Immutable SQLite: `releases/<release_id>/indexes/lane-c-source.sqlite`; atomically selected by `active-release.json`. Key table `source_incidents` (429,796 accepted current NRC/CSB observations at the verified release), composite primary key **(`source`, `source_id`)**, `WITHOUT ROWID`. `source` is one of `nrc_2010` ... `nrc_2026` or `csb`. Published `source_vintage` is year or release date. The original NRC `SEQNOS` appears as `publisher_native_id` and `source_id`; CSB original `Number` is retained as `publisher_native_id`, with `source_id=csb:2026-09-01:<Number>`. CSB `Number` is **not permanent across quarters**: 19 source identity attributes changed from June to September 2026. Enforce release scope.

```sql
-- Never equate reported source latitude/longitude with an insured-property footprint.
SELECT source, source_id, publisher_native_id, source_vintage,
       incident_date, city, state, latitude, longitude,
       evidence_status, site_link_status, source_url
FROM source_incidents
WHERE source = 'nrc_2025' AND state = 'TX'
  AND incident_date >= '2025-01-01'
ORDER BY incident_date DESC, source_id
LIMIT 25;
```

`source_incidents` columns: `source`, `source_id`, `publisher_native_id`, `source_vintage`, nullable occurrence `incident_date`, as-reported `city` and `state`, optional source-reported `latitude`/`longitude`, `evidence_status`, review-only `site_link_status`, original `source_url`, and `source_json` with preserved normalized publisher row. Indexes: source/native composite primary key, `source_incidents_date`, `source_incidents_state`, `source_incidents_geo`. **Do not expose `source_json` in unrestricted client API**. Separate `lane_c_review_candidates` table has `nrc_source`, `nrc_source_id`, `csb_source`, `csb_source_id`, `match_rule`, `status='review_candidate_not_corrob'`; **135 candidate pairs / 83 CSB records**, no independent same-event verification or site-level corroboration. CSB may legally report by reusing an NRC reference, so cross-agency overlap does NOT prove independent corroboration.

`lane_c_install.py query` uses read-only SQLite, parameterized filters, bounded `page_size` 1–200, and deliberately returns only source-identifying, dated and geographic fields—not original report free text. The private service must authorize every request and redact sensitive source fields by role/tenant.

**Proposed Lane E API (not yet implemented):**

| Authenticated endpoint | Inputs / behavior | Guard |
| --- | --- | --- |
| `GET /api/v1/lane-c/sources` | One row per native source namespace, release/vintage, accepted/rejected counts, raw/normalized SHA and verification timestamp | Operator/reviewer only; no free text |
| `GET /api/v1/lane-c/observations` | Required `source`; optional `state`, `since`; `page`, `page_size<=200`; results from `lane_c_install.py query` | Auth, rate limit, audited tenant scope; all are **unverified source observations** |
| `GET /api/v1/lane-c/observations/{source}/{source_id}` | Native report-level context, immutable provenance, explicit null/uncertainty | Privileged reviewer; avoid personal free-text leakage |
| `GET /api/v1/lane-c/review-candidates` | Candidate pairs with rule and `review_candidate_not_corrob` | Admin/reviewer only; **never** automatically promote to verified sites |
| `GET /api/v1/lane-c/health` | Last refresh, active indexed snapshot, operational failures, PHMSA access blockage and deployment verification | Source Health must distinguish downloaded/normalized/CI indexed/private installed/live deployed |

Auth, deployment, frontend integration, canonical facility verification and physical location corroboration belong to **Lane E**, not this ingestion PR. **No facility-scoped list for “all facilities” can legitimately be derived solely from these incident-report sources.** Absence from a regulatory incident report does not mean low or zero facility risk.

## 4. PHMSA enforcement is a separate source and cannot replace incidents

The [real first-party PHMSA enforcement job 39985148724](https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/39985148724) produces `build_phmsa_enforcement.py` source manifests and a **distinct enforcement-case index** with `enforcement_cases` and indexes `enforcement_cases_native`, `enforcement_cases_report`, `enforcement_cases_operator`. True source fields: `CPF_Number`, `WMS_Activity_Seq`, `Operator_ID`, `Operator_Name`, `Pipeline_Type`, `Case_Type`, `Case_Status`, `Opened_Date`, `Report_Type`, `Report_Number`, `Data_as_of`. 5,089 native case IDs, 453 report-reference rows, 403 distinct typed report references; unique source snapshot and case activity remain distinct from NRC `SEQNOS`. The **PHMSA full pipeline/hazmat incident census is NOT DOWNLOADED/NOT TESTED**. Four official pipeline ZIPs returned HTTP 403 from GitHub runners; official hazmat portal redirected to an inaccessible login. Only permitted publisher/agency export can resolve this. No mirror, access bypass, synthetic incident counts, or category substitution.

For authorized PHMSA enforcement replay:
```bash
python -m pytest -q tests/test_phmsa_enforcement.py
python scripts/probe_lane_c_phmsa_enforcement.py --output /srv/facility-risk/ingest-qa/phmsa
```
The PHMSA **case** index is currently disposable CI only until a separately authenticated private service installer/refresh is approved by Lane E. **Do not add 5,089 case rows to the 429,796 NRC/CSB observations as though they were 5,089 accidents.**

## 5. Refresh, versioning, failure recovery, monitoring

1. **Scheduled source status scan:** coordinator-run job checks official publisher availability and most recent NRC annual/current partial workbook, CSB quarterly release and PHMSA first-party enforcement snapshot; do not assume source frequencies when publisher has not specified them. Source inventory should expose `last_attempt`, `last_success`, exact original URL/vintage/SHA, downloaded/accepted/rejected counts and error state.
2. **Reproducible download and validation:** fetch only authorized HTTPS publisher endpoints, hash original bytes SHA-256, inventory actual schema and native identifiers, normalize deterministically, keep null coordinates/date; recount all rows and archive per-vintage provenance. **Never** use downloaded byte count, a synthetic fixture, HTTP 200 metadata or an index in ephemeral CI as a substitute for true source-record coverage.
3. **Private staged bundle / atomic install:** validate complete original/normalized SHA, SQLite `quick_check`, expected per-source namespace counts and candidate statuses. Do not update active pointer until every gate passes. Existing release remains readable during ingestion and validation; immutable releases make rollback quick.
4. **Deployment acceptance (Lane E):** verify private datastore is durable across restart, running under an auth-controlled read-only identity, with backup/restore, audit logs and tenant isolation; query actual source IDs before wiring facility page. Confirm Source Health and live endpoint counts, and negative test that unauthenticated user cannot query personal report details.
5. **Failure conditions:** schema drift, duplicate master keys, ambiguous NRC child severity, CSB changed Number semantics, wrong coordinate hemisphere, unexpected row-count collapse, short publisher response, HTTP 403, checksum mismatch, missing source index, SQL integrity fail, disk full or auth failure => stop that source publication and label **BLOCKED / STALE LAST-VALID** rather than zero; record error/time, preserve prior active release and evidence, retry by approved official source channel. Incomplete sources must never silently convert to `DEPLOYED`.
6. **Review controls:** preserve `site_link_status=candidate_only_not_matched` until a separately recorded reviewer corroborates source location, insured address/FEI/company and independent incident/outcome evidence. Store reviewer decision/provenance outside immutable source index, maintain revision history and two-person approval if adopted by Lane E. Never infer insurer coverage, paid loss or business interruption from a federal report.

## 6. Explicit readiness and ownership

**Lane C deliverable:** documented, first-party NRC/CSB source download and normalization with actual geographic/year/status QA and SHA provenance; 429,796-row temporary queryable SQLite; reproducible restricted source bundle; versioned private installer/rollback/read-only query contract and real CI installation smoke verification; separate PHMSA WMS case source. The latest official real-run evidence and issue comment are required to mark installer claims independently supported.

**Lane E remaining:** provision a *durable* private host/storage, install verified bundle, wire authenticated API and Source Health, independently verify insured-site crosswalk and sensitive source-data handling, test refresh/recovery and browser, confirm persisted/deployed counts, then review and merge PR #79. **No Lane C PR self-merge.**

**Hard external blocker:** full PHMSA pipeline/hazmat source ZIPs HTTP 403/inaccessible official export. Lane C cannot claim full PHMSA incident coverage or entire Issue #73 definition of done. Keep these as `NOT_TESTED` until authorized official file access is secured.
