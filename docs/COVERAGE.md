# Facility population, evidence, and loss-assessment coverage

## Product intent

The application must accept facilities in every industry for investigation, including offices, retail, industrial plants, utilities, hospitals, warehouses and life-science establishments. The **coverage universe** is not limited to the initial twelve analyst cases, and it is not limited to three public examples. All facilities discovered from official registries, permitted place datasets or manual entry are eligible for investigation.

That does **not** mean all physical manufacturing sites in the world can be positively enumerated from public records. The public catalog includes FDA device/drug sources, Canadian NPRI and Irish EPA. A separate private indexed EPA FRS corpus contains 5,354,716 source identities; Overture international coverage has been pilot-tested. Neither is hosted on public GitHub Pages. These registries include foreign establishments involved in U.S.-market supply, but not facilities entirely outside U.S. market disclosure. Registrations are not evidence of FDA approval, active operation, or safe physical risk.

## Distinct layers

1. **Registry catalog:** FDA-reported establishment/source identity, legal operator, activity, location text, registration and FEI when disclosed. Public, broad coverage; may include historical listings. Never treat raw device *listing rows* as distinct physical facilities.
2. **Investigation workspace:** any registered facility or user-supplied site may be added. This does not constitute an audited FEI-to-FRS link or a verified property boundary.
3. **Facility risk evidence:** physical hazards, environmental violations, regulatory findings, operations, utility reliability and incident history are attached only after a reliable site match.
4. **Underwriting exposure:** replacement value, BI exposure, property construction, utilities, redundancy, protection and claims remain unpopulated until evidence is collected.
5. **Validated insurance score:** deliberately disabled pending outcome-based calibration.

## FDA official source refresh

- Data metadata: https://api.fda.gov/download.json — fetch every `results.device.registrationlisting.partitions` entry. FDA publishes 300k+ device registration/listing rows; deduplicate by observed FDA FEI or registration identifier **within that source**, retaining listing counts and role classes. Do not merge device and drug source entries on unreviewed names.
- Device original source and update description: https://www.fda.gov/medical-devices/device-registration-and-listing/establishment-registration-and-medical-device-listing-files-download
- Drug source: https://www.fda.gov/drugs/drug-approvals-and-databases/drug-establishments-current-registration-site-decrs
- Build: `python -m pip install 'ijson>=3.3,<4'`, then `python scripts/build_catalog.py --output web/registry/catalog.json`
- Private backend: `python -m facilityrisk import-registry web/registry/catalog.json` loads the bulk public catalog into a separate SQLite table. Analyst evidence remains in `facilities` / `evidence` tables.
- `.github/workflows/build-registry.yml` runs weekly and on changes to the builder. It commits only a compact establishment source catalog: no agent names/emails, US agents, contacts, phone numbers, products, or private insurance information.

## Public UI rules

- **All registered facilities:** searchable by site/company, FEI, city, location, country and sector; paginated.
- **Research cases:** only facilities with analyst evidence or newly opened investigations. Count not interchangeable with registry coverage.
- **Unknown / not evaluated:** default for all registry source identities; do not infer hazard or compliance score from registration.
- **Any other site:** manual intake in the browser preview, retained only in memory; production backend must authenticate creation and audit the actor.

## Important gaps

This is not a complete global pharmaceutical/device plant census. Non-FDA markets (EMA, EudraGMDP, MHRA, Health Canada, PMDA, NMPA and local environmental / labor registries) require additional data integration and individual license checks. A new source should have independent identifiers, freshness, deduplication rules, a source link, and an explicit completeness statement. FDA FEI is not an EPA FRS ID, and a mailing address does not establish a property centroid.

## Independent Irish environmental licensing discovery (2026-10)

The public browser also searches official **Ireland EPA LEAP licence profiles** from
`https://data.epa.ie/leap/api/v1/LicenceProfile/list`. This is an independent
regulatory identity population, not FDA-registered manufacturers. LEAP includes
nonmanufacturing activity such as ports, radiological licences and wastewater
sites; do not classify every listed entity as pharma, device, or even a factory.

Licence profile numbers, reporting organisation, county, town and licence class
are preserved, but no precise coordinates or environmental violations are
inferred. The official-source publisher URL is supplied for each profile.
To build: `python scripts/build_ireland_leap.py --output web/registry/ireland-leap.json`.
The scheduled workflow refuses unexpectedly small source results and retains
the last published file on retrieval failure.


## Independent Canadian environmental reporting coverage (2026-10)

A separate public catalogue uses the official [Canadian National Pollutant Release Inventory (NPRI)](https://maps-cartes.ec.gc.ca/arcgis/rest/services/STB_DGST/NPRI/MapServer/0) 2024 facility-reporting feature layer. Its dataset explicitly represents **2024 reporters**, not all Canadian industrial sites and not every manufacturer. The public export includes each source record's NPRI ID, 2024 reporting period, reported operator/facility, address and province, and NAICS/sector descriptor when published; it excludes full source geometry, personal contacts and reporting quantities. The presence of a reporter is not proof of a violation, emission severity, insured property damage or current operation in 2026.

Build with `python scripts/build_canada_npri.py --output web/registry/canada-npri.json`. The dedicated weekly GitHub Actions workflow checks the complete official ArcGIS ObjectID cohort, enforces the 2024 reporting vintage and publishes the compact public source catalog. The source's reported location is **not** an independently reviewed parcel centroid or production-building coordinate. No NPRI source record is automatically merged with an FDA FEI, Canadian device/drug site, Ireland EPA licence, or a proprietary insured facility.

The full browse list therefore combines distinct *regulatory source identities*, not a physically deduplicated plant count. An empty query lists all available source records; exact physical-site verification remains an investigation task.
