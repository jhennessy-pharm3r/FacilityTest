"""Export private research data for in-memory browser viewing on static GitHub Pages.

The generated JSON is private research data. Never commit it to a public repository.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from .db import items
from .intelligence import get_intelligence,intelligence_quality
from .advanced_sources import SOURCE_META


def export_browser_snapshot(conn, output_path: str | Path) -> dict:
    """Write a self-contained, versioned read-only browser data snapshot."""
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    facility_rows = items(conn, 'SELECT * FROM facilities ORDER BY name')
    evidence_rows = items(conn, 'SELECT * FROM evidence ORDER BY facility_id,date_raw DESC')
    sec_rows = items(conn, 'SELECT * FROM sec_findings ORDER BY id')
    sources = items(conn, 'SELECT * FROM sources ORDER BY name')
    runs = items(conn, 'SELECT * FROM ingestion_runs ORDER BY started_at DESC LIMIT 20')
    valid_ids = {row['id'] for row in facility_rows}
    orphans = [x['id'] for x in evidence_rows if x['facility_id'] not in valid_ids]
    if orphans:
        raise ValueError(f'Orphan evidence records block export ({len(orphans)})')
    snapshot = {
        'schema_version': '1.0',
        'dataset_mode': 'private_local_browser_import',
        'dataset_label': 'Local facility research',
        'exported_at_utc': datetime.now(timezone.utc).isoformat(),
        'facilities': facility_rows,
        'evidence': evidence_rows,
        'sec_findings': sec_rows,
        'sources': sources,
        'ingestions': runs,
        'intelligence': {'sites':[dict(id=x['id'],name=x['name'],**get_intelligence(conn,x['id'])) for x in facility_rows], 'quality':intelligence_quality(conn), 'source_health':items(conn,'SELECT * FROM source_health ORDER BY source'), 'source_catalog':[{'source':key,'documentation':v[0]} for key,v in SOURCE_META.items()]},
        'important_caveats': [
            'Private local research snapshot; this file contains analyst-curated data and must not be committed to a public repository.',
            'Import occurs in browser memory only. Do not forward screenshots or exports without appropriate authorization.',
            'Source URLs in imported evidence are citations, not proof that live APIs were independently checked.',
            'Evidence availability dates and site-level crosswalks require validation before backtesting.',
            'SEC disclosures and insurer claims are different evidence classes; do not aggregate without reconciliation.',
            'Geographic proximity and compliance indicators do not establish insured property loss.',
        ],
    }
    output.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(',', ':'), default=str), encoding='utf-8')
    return {'status': 'exported_private_browser_snapshot', 'path': str(output),
            'facilities': len(facility_rows), 'evidence': len(evidence_rows),
            'sec_findings': len(sec_rows), 'sources': len(sources), 'bytes': output.stat().st_size}
