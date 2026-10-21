# Pre-hardening evidence attribution remediation

Older private databases may have evidence attached before v0.6 introduced mandatory physical-point and FEI verification. **Do not assume old NOAA, FDA inspection, WRI or USGS rows are accepted facility-specific findings.**

Run the private, non-destructive audit first:

```powershell
python -m facilityrisk audit-attribution
python -m facilityrisk qa
```

The QA response includes `legacy_attribution_pending` and `legacy_attribution_reasons`. The audit identifies (a) old NOAA storm reports inserted into accepted site evidence solely by geographic proximity, (b) FDA inspection rows without an independently reviewed FEI-to-site identity at the time of import and (c) geographic source records lacking a valid point approval prior to source retrieval.

If the results have been reviewed and the private database has a tested backup, move the flagged records into a separate preservation table:

```powershell
python -m facilityrisk audit-attribution --apply --reviewer "Authorized Data Reviewer"
```

The operation saves each original database row as JSON in `legacy_evidence_quarantine`, records a timestamp and reviewer audit event, then removes only flagged records from the accepted `evidence` table. It **does not** erase the original source observations from the database. It is idempotent. Restoration or promotion must follow independent original-source review and site-identity confirmation; no automatic restore-to-accepted-evidence route is provided. No historical incident or insurer claim is inferred.

Do not run this on a public GitHub Pages dataset. This concerns the private facility SQLite instance. Keep the backup and quarantine JSON under controlled permissions, separate from public source catalogs.

## Official registration collisions

An FDA FEI appearing across different reported street addresses, operators, names or cities is not treated as proof of one immutable physical property. The registry publisher now preserves observed conflicts in `identity_conflicts` metadata and exposes them in the public registry detail drawer. The first-reported row remains discoverable for backward schema compatibility; both variants require an analyst to distinguish data corrections, relocation, separate buildings and actual site identity. **FEI/registration deduplication is source-record deduplication, never underwriting property deduplication.**
