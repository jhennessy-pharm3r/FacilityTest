# Private deployment blueprint (non-production prototype)

## Threat boundary

GitHub Pages is public and static. It serves only public case studies and has no API credentials. **Never upload the analyst workbook, insured loss runs, full research snapshot, tokens, API keys or SQLite database to the public repo, frontend source or GitHub Pages.** An uploaded private snapshot is read into the browser in memory; use the private server instead for client-confidential records.

## Single-tenant local server

1. Provision a controlled Windows/Linux server and install Python 3.12 or Docker.
2. Copy the repo and obtain research data through an approved private channel. Keep `data/` out of Git.
3. Create an untracked `.env` from `.env.example`; generate a random token with at least 32 characters.
4. Create a writable `data/` volume owned by UID 10001 for Compose (Linux: `sudo chown -R 10001:10001 data`) or use a managed dedicated persistent storage volume. Validate backups/recovery before loading client content.
5. `docker compose up --build -d`. The server binds only `127.0.0.1:8765` on the host, and requires a bearer/basic secret.
6. Access locally over localhost; for remote access use a separately configured HTTPS reverse proxy, VPN and enterprise SSO/identity-aware access. Do not expose direct 8765 to public internet.
7. For the Python-only route, `FACILITY_RISK_REQUIRE_AUTH=1 FACILITY_RISK_AUTH_TOKEN=... python -m facilityrisk serve --host 127.0.0.1`.

The container is unprivileged and read-only apart from the database volume and tmpfs. Secret injection via managed service is preferable to Compose environment variables in production. The `.env` file can still be read by a local administrator. Rotate credentials regularly and do not log Authorization headers.

## Write protection and governance

- Basic/Bearer authentication is a *single-tenant demonstration guard*, not multi-user RBAC, per-client authorization, MFA, SSO or fine-grained audit authorization. This blueprint is **not production authorization**.
- All write endpoints are disabled unless `FACILITY_RISK_ENABLE_WRITES=1`; even when enabled, require reverse-proxy OIDC and proper organization scoping before handling client information.
- Identity matches and reviewed coordinates require a named reviewer and corroborating URL. Record versioned source evidence, original timestamps, publication timestamps and record provenance.
- Daily encrypted backups of the SQLite volume; weekly restore tests; retention and deletion schedules; zero trust network controls and perimeter logs before production.
- Risk values and insured losses require a separate private datastore/permissions, not GitHub Pages static data or public GitHub Actions artifacts.

## Refresh operations

- `python -m facilityrisk discover-frs --facility ... --name ... --state ...` only creates **candidates**.
- After checking legal name, facility address and operator, `review-frs --candidate ... --decision accepted --reviewer ... --source https://... --note ...` documents identity evidence.
- `refresh-verified-echo` requires a verified EPA FRS identity.
- `review-location` requires a corroborated site point before `refresh-fema` is enabled; FEMA zone absence is **not mapped**, not safe.
- `refresh-usgs` captures nearby epicenters, not structural shaking damage; NOAA ingests source CSV; FDA inspections require an official export; WRI is modeled basin stress.
- GitHub Actions `Public source connectivity check` is scheduled weekly. It checks public endpoints without sending client site names or database content. It does not ingest live facility data or validate data quality. Check the Actions artifact before relying on a source.

## Hard requirements still outstanding before external client access

Implement OIDC/SSO with tenant-scoped roles, CSRF protection for cookie-authenticated writes, row-level separation of clients, database access encryption/backup and restore, peer-reviewed risk definitions, change control, monitoring/alerting, enterprise secrets, and a security penetration assessment. Do not represent the app as production secure or as an actuarially calibrated insurer rating system.


## Independent human review of consequential site matches

The private backend includes a *two-distinct-authenticated-account* review mode for three actions: approving a physical site location, promoting an observed FDA FEI to verified, or accepting/rejecting an EPA/other regulatory identity crosswalk. This is **not** enterprise OIDC or insurer multi-tenant RBAC.

To enable it on a controlled private deployment:

1. Generate a **different** 16+ character password for each person. Derive salted PBKDF2-SHA256 verifiers without writing passwords to a file:
   ```powershell
   python -c "from facilityrisk.security import make_password_hash; import getpass; print(make_password_hash(getpass.getpass('Individual password: ')))"
   ```
2. Store a JSON secret in the secret manager as `FACILITY_RISK_USERS_JSON`, with distinct, non-shared usernames and roles. Shape: `{"analystA":{"role":"reviewer","password_hash":"pbkdf2_sha256$260000$..."},"managerB":{"role":"approver","password_hash":"pbkdf2_sha256$260000$..."}}`. **Do not copy example verifiers.**
3. Enable `FACILITY_RISK_DUAL_REVIEW=1` and `FACILITY_RISK_ENABLE_WRITES=1`. Serve behind TLS and an identity-aware proxy/VPN. In dual mode, shared service Bearer tokens cannot make protected decisions; viewer accounts cannot write.
4. A reviewer authenticated as `reviewer` or `admin` submits the existing location/FEI/crosswalk review POST request. It returns `pending`, with no underlying identity/point promoted.
5. A separate authenticated `approver` or `admin` queries `GET /api/review-approvals?status=pending` and submits `POST /api/review-approvals/{approval_id}/decide` with `{"decision":"approve","note":"Independently checked corroborating source and site address"}`. Same-account approvals are rejected. Changed coordinates/FEI/upstream candidates invalidate the proposal and require new evidence.
6. Audit records preserve both user IDs and the source snapshot. A second approver may explicitly reject an application without promoting evidence.

`FACILITY_RISK_DUAL_REVIEW=0` preserves the existing *local prototype* single-review behavior for backward compatibility. **Any non-loopback deployment with private writes enabled now refuses to start unless dual review is configured.** Local CLI commands run as a trusted operator and are not independently authenticated reviewers; restrict shell access and do not use CLI direct-review commands for production decisions. Historical source reviews made before dual mode remain legacy and must not be presented as two-person-approved. Tenant scoping, SSO/MFA, CSRF protection for cookie-based auth, external authorization audit, and penetration testing remain mandatory for insurance-client production access.
