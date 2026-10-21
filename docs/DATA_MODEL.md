# Data model and provenance

The research app stores the analyst's workbook in SQLite while preserving the original contents and qualifications. `facility_id` resolves a specific physical site—not an ultimate parent or company alone.

| Table | Grain | Important keys and fields |
| --- | --- | --- |
| `facilities` | One curated site | stable slug ID, FEI (if known), researched coordinates, address, operating company, coverage notes |
| `evidence` | One source claim, monitoring observation or source summary associated with a site | source, program, `date_raw`, record_type, finding, source_url, scope, match quality, limitations, availability_date, spatial_distance_km |
| `sec_findings` | One analyst-extracted filing finding (not a unique insurance event) | finding ID, issuer, incident window, financial/supply consequences, recoveries, caveats, optional facility_id, event_group |
| `public_evidence` | One supplemental public-source reference for SEC review | reference ID, group relationships, observation, timing, limitations, URL |
| `sources` | Source family in workbook catalog | source name, record level, history, methods and limitations |
| `field_catalog` | One researched source table/field set | field names, join keys, risk fields and source documentation |
| `raw_snapshots` | Original JSON response from an opt-in live adapter | source, facility, endpoint URL, retrieval timestamp, unmodified response JSON |
| `ingestion_runs` | One workbook ingestion run | time, checksum, status, counts and summary JSON |

The imported workbook uses a stable `origin` value, making repeated ingestion replacement-safe. Evidence from separately ingested sources is not overwritten by workbook re-import.

## Interpretation rules

1. `date_raw` is **untyped**: event date, reporting vintage, observation date, permit expiration or range. Do not interpret it uniformly as an incident date.
2. `availability_date` is NULL unless publication timing has been independently confirmed. `retrieval_at` is the date our system fetched the record, **not** its initial public availability date.
3. `match_quality` is an analyst-authored statement in imported rows, not a calculated probability or verification of ownership. Use FEI/FRS identity or verified addresses before applying site-level evidence.
4. `event_group` groups related SEC disclosures, but does not mean identical financial line items can be summed. Subsequent filing revisions and insurance recoveries need reconciliation.
5. `risk_domain` is a descriptive source grouping, **not a severity score**.
6. Spatial distance is a proximity filter; it is not modeled damage, structural vulnerability, flood depth or utility interruption.
7. Unobserved or missing records must not be interpreted as zero risk.
