# USCG National Response Center annual source — exploratory validation

## Why this matters

The National Response Center receives and records initial notifications of oil and chemical releases, as well as other reportable environmental incidents. It is broader than NOAA OR&R IncidentNews, which covers selected scientifically supported responses. NRC source records may indicate regional industrial, infrastructure, transport and storage incidents affecting various types of facilities. **Notification alone is not independently verified evidence that a particular insured property was damaged.**

Official publisher: https://nrc.uscg.mil/

Annual FOIA source examples:
- https://nrc.uscg.mil/FOIAFiles/CY25.xlsx
- https://nrc.uscg.mil/FOIAFiles/CY26.xlsx

The public reports are Excel workbooks with multiple linked sheets. An incident can occur in more than one material/substance row, so summing worksheet rows is not an incident count. The year of filing may differ from the event date.

## What the first integration does

The workflow `probe-uscg-nrc.yml` downloads actual official 2025 and 2026 workbooks and verifies HTTPS host, ZIP/XLSX integrity, sheet names, table headers, number of reported rows and SHA256. Its reports clearly state `schema_probe_only_not_imported`.

It deliberately does not publish workbook contents, incident names, company names, or coordinates to GitHub Pages. Actual source row counts cannot be called ingested until a separate extractor reconstructs report identities and checks material-table multiplicity.

## Mandatory next gates

1. Verify each workbook's primary incident identifier (e.g., SEQNOS), incident vs reported date and jurisdiction/address quality. Review the schema probe artifacts.
2. Construct a deterministic source-only import keyed to *unique* report IDs; join commodities and quantities only under documented one-to-many relations, preserving native units, material qualifiers and unknown locations.
3. Reject duplicates, invalid date ranges, missing annual files and schema drift, with independent file hash/vintage manifests.
4. Test actual official workbooks in a private SQLite index, then expose authenticated source searches. Geographic proximity remains only a review candidate for independently verified physical property points.
5. Publish a sanitary Source Health row with *distinct verified reports*, not sheet-row totals, and explicitly distinguish initial unverified reports from confirmed violations, spills, property damage, BI and claims.
6. Backfill historical years from the publisher as separate validated cohorts and establish a durable authenticated server refresh strategy.

No insurance loss, policy coverage, facility attribution or site risk score is implied by the probe.