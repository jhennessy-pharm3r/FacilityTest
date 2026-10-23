# Lane D — utility reliability / outage / interruption evidence

Scope: all industries and all facility types. This branch contains a **standalone staging importer**, not a UI integration or production dataset.

## Official evidence and use restrictions

- EIA-861 2025 final ZIP: https://www.eia.gov/electricity/data/eia861/zip/f8612025.zip (discover archive vintages at https://www.eia.gov/electricity/data/eia861/). EIA describes this as utility-reported non-momentary SAIDI / SAIFI where collected, with IEEE/other reporting methods and major-event conventions. Source utility ID is **not** a facility ID.
- EIA-861 Service Territory worksheet: county-level equipment/service territory, not proof of any insured property's serving utility. For future separate utility/provider candidate linkage only.
- DOE-417 official incident reports: https://doe417.energy.gov/ — disturbance-report evidence, potentially broad geographic areas; not a comprehensive customer outage register or claims source. Its historical files require their own importer and event-specific native-identifier review.
- Business-interruption outcomes: company filings may document economic impact; maintain filing accession, passage, reporting period, event date, company ID and separately corroborated site before attributing losses. Outage ≠ downtime ≠ lost revenue ≠ insured claim.
- Source publication is U.S. federal government data; confirm each downstream redistribution condition and attribution on original archive.

## Reproduce / validate

```bash
pip install openpyxl
python -m unittest discover -s tests -p 'test_lane_d_eia861.py' -v
python -m facilityrisk.lane_d.ingest_eia861 --year 2025 --output ./private/lane-d/eia861-2025
# In restricted environments first download official ZIP out-of-band:
python -m facilityrisk.lane_d.ingest_eia861 --year 2025 --zip /path/to/f8612025.zip --output ./private/lane-d/eia861-2025
```

Importer hashes original archive/member/row, preserves original utility ID (including leading zeros) and all workbook fields, counts exact-row duplicates and invalid IDs without conflating different method/state/utility rows. Results: `eia861_reliability.jsonl`, `eia861_rejected.jsonl`, `manifest.json`. Retain the complete raw source archive in restricted data storage, not GitHub. `NORMALIZED` is a pipeline processing state, **not** a source quality, site evidence or deployment verification guarantee.

## Run / validation ledger, 2026-10-23

| Source | Web page/metadata | Real archive downloaded into runner | Accepted | Rejected | Indexed | Verified facility records | Deployed |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| EIA-861 2025 | Official 2025 final archive URL confirmed | BLOCKED (runner DNS) | Not measured | Not measured | 0 | 0 | 0 |
| DOE-417 disturbance events | Official archive landing identified | NOT TESTED (archive ingestion) | Not measured | Not measured | 0 | 0 | 0 |
| Site-specific public outage | Dataset not selected or ingested | NOT TESTED | Not measured | Not measured | 0 | 0 | 0 |
| SEC/issuer interruption outcomes | No accession-level evidence ingested | NOT TESTED | Not measured | Not measured | 0 | 0 | 0 |

The environment executing validation returned DNS resolution failure for both `www.eia.gov` and `github.com` from its shell. **No real source rows were ingested or validated.** Test fixture rows are synthetic and expressly excluded from source counts. Independent production refresh, archive schema inspection, service-area crosswalk, backend query/index integration and live app verification remain blocked/pending. This PR must not update Source Health to VERIFIED or DEPLOYED. Coordinator owns cross-lane integration and shared UI.

Do not estimate facility-specific outage probability, utility provider assignment, BI loss, policy coverage or claims from EIA metrics, nearby events or absence of a record.
