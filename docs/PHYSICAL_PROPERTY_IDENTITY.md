# Facility physical-property hierarchy — identity review

**Purpose:** prevent the application from treating a company, regulatory
identifier, campus, individual building, leased unit, parcel, utility node
and insured premises as synonyms. Every industry is eligible.

## Entity boundaries

- **Research facility:** a working investigation context in `facilities`.
  Its location review can corroborate a single point, but it is not an
  automatic building/parcel identification for every structure at a campus.
- **Physical asset candidate:** one campus, building, leased unit, parcel,
  warehouse, utility node or other element in `facility_assets`. Parent
  references (e.g. a building within a campus) are explicit and must point
  to an asset in the **same** research facility. The parent link is
  immutable after creation and must not be silently rewritten.
- **Source observation:** reported address, operator, parent name, coordinate,
  URL and original record ID. These may be incomplete or outdated.
  *Reported parent* is not a verified ultimate-parent corporate relationship.
- **Independently corroborated identity:** two distinct named authenticated
  individuals reviewed the candidate description and its evidence. Approval
  does **not** promote a source-observed latitude/longitude to a verified
  parcel/building coordinate. Separate site coordinate review and GIS
  evidence are required before natural-hazard point screening.
- **Insured location:** a policy schedule and contract determination,
  handled separately. An approved asset is not proof that the property is
  insured, protected, or eligible for a parametric payment.

## Private API

Read operations (authenticated backend only):
- `GET /api/facilities/{facility_id}/assets`
- `GET /api/asset-reviews?facility_id=...&status=pending`

Write operations require `FACILITY_RISK_ENABLE_WRITES=1`,
`FACILITY_RISK_DUAL_REVIEW=1`, individually authenticated reviewer and
approver roles:
- `POST /api/facilities/{facility_id}/assets`: create an unverified
  campus/building/parcel/leased unit, with optional complete source point.
- `PATCH /api/assets/{asset_id}`: revise source-observed details and
  **invalidate** any earlier identity approval. Revision numbers prevent
  approving a changed asset with stale evidence.
- `POST /api/assets/{asset_id}/propose-review`: propose
  `identity_corroborated` or `rejected` with original HTTPS evidence URL
  and detailed rationale.
- `POST /api/asset-reviews/{review_id}/decide`: a separate approver
  accepts/rejects; self-approval and outdated candidate revisions fail.
  Rejected identity remains rejected until the source candidate is
  explicitly revised.

The facility Risk evidence drawer and private printable assessment show
physical asset candidates, their hierarchy and identity-review status,
without claiming a loss score or location verification.

## Required next evidence gates

1. Independently verify physical building/parcel geocodes with map,
   municipal parcel, engineering survey, lease or other eligible
   authoritative evidence; store original source scope/vintage.
2. Corroborate insured property schedule references against particular
   building or leased-unit candidates. A string match is not proof.
3. Add insurer/client organization authorization and tenant isolation
   before storing confidential location schedules or policy documents.
4. Validate at least 25 actual properties across industrial, healthcare,
   commercial, warehousing, utility and other sectors, recording
   false-positive and false-negative identity matches.
5. Keep parent-company resolution distinct from reported operator and
   tenant/landlord/insured-interest relationships.

No automatic national geocode, hazard score, loss model, legal ownership,
policy attachment or parcel boundaries are delivered by this module.
