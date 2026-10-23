"""Publish evidence-limited public source probe and catalog status for GitHub Pages.

This file only writes connectivity and *published source identity* metadata.
It never republishes raw government exports, site coordinates, private matches,
insured data, or facility-specific hazard/insurance conclusions.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

# Script entry points run with scripts/ as sys.path[0] in GitHub Actions.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from facilityrisk.advanced_sources import SOURCE_META
from facilityrisk.registry_catalog import SOURCE_DEVICE, SOURCE_DRUG
from facilityrisk.source_extensions import SOURCES

EXTENDED_BY_NAME = {source["name"]: source for source in SOURCES}
PRIMARY_STATES = {"reachable", "failed", "requires_file"}
EXTENDED_STATES = {"docs_reachable", "schema_reachable", "failed"}

# Sector filters are SOURCE labels, not independently verified property counts.
CATALOGS = (
    ("FDA device registrations", "catalog.json", "fda_device", SOURCE_DEVICE, "Medical device"),
    ("FDA drug establishments", "catalog.json", "fda_drug", SOURCE_DRUG, "Pharmaceutical"),
    ("Ireland EPA LEAP", "ireland-leap.json", "ireland_leap", None, "Environmental licence"),
    ("Canada NPRI", "canada-npri.json", "canada_npri", None, "Environmental reporting"),
)


def checks_from_file(path: Path, metadata: dict, permitted_states: set, checked_at: str):
    payload = json.loads(path.read_text(encoding="utf-8"))
    checks = payload.get("checks")
    if not isinstance(checks, list):
        raise ValueError(f"{path}: missing checks")
    found = {}
    for check in checks:
        if not isinstance(check, dict):
            raise ValueError(f"{path}: unexpected check type")
        name = check.get("source")
        if name not in metadata or name in found:
            raise ValueError(f"{path}: unknown or duplicate source {name!r}")
        if check.get("state") not in permitted_states:
            raise ValueError(f"{path}: invalid probe state {check.get('state')!r}")
        info = metadata[name]
        doc = info["documentation"] if isinstance(info, dict) else info[0]
        found[name] = {
            "source": name,
            "state": check["state"],
            "checked_at": checked_at,
            "details": str(check.get("details", ""))[:360],
            "documentation": doc,
            "probe_url": str(check.get("url", ""))[:400],
            "test_level": "documentation_or_connectivity_only",
        }
    if set(found) != set(metadata):
        missing = sorted(set(metadata) - set(found))
        raise ValueError(f"{path}: incomplete source checks: {missing}")
    return list(found.values())


def published_catalogs(directory: Path):
    result = []
    loaded = {}
    for name, filename, key, source_label, sector in CATALOGS:
        path = directory / filename
        if filename not in loaded:
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("schema_version") != "1.0" or not isinstance(data.get("rows"), list) or not isinstance(data.get("sources"), dict):
                    raise ValueError(f"Invalid published catalog {path}")
                if "sector" not in data.get("fields", []) or "source" not in data["fields"]:
                    raise ValueError(f"Missing source/sector columns: {path}")
                loaded[filename] = data
            else:
                loaded[filename] = None
        data = loaded[filename]
        if not data:
            result.append({"source": name, "state": "not_published", "records": None,
                           "checked_at": None, "scope": "published regulatory source identities",
                           "details": "Catalog file absent; no ingestion claim", "documentation": ""})
            continue
        meta = data["sources"].get(key, {})
        status = str(meta.get("status", "unknown"))
        fields = data["fields"]
        sector_pos, source_pos = fields.index("sector"), fields.index("source")
        count = sum(1 for row in data["rows"] if len(row) == len(fields) and row[sector_pos] == sector
                    and (source_label is None or row[source_pos] == source_label))
        if status in {"imported", "stale_preserved"} and count < 1:
            raise ValueError(f"{path}: {key} claims import but has no cohort")
        result.append({
            "source": name,
            "state": status,
            "records": count if status in {"imported", "stale_preserved"} else None,
            "checked_at": data.get("generated_at"),
            "scope": "published regulatory source identities (not verified physical properties)",
            "details": ("Published source identities; no facility hazard or insurance linkage"
                        if status == "imported" else "Not a verified current import; consult original source status"),
            "documentation": str(meta.get("url", ""))[:400],
        })
    result.append({
        "source": "EPA FRS national indexed registry",
        "state": "private_index_not_deployed",
        "records": None,
        "checked_at": None,
        "scope": "national identity index retained separately from Pages",
        "details": "Workflow-only indexed database; not durably hosted or available to the public search",
        "documentation": "https://github.com/jhennessy-pharm3r/FacilityTest/actions/workflows/validate-frs-index.yml",
    })
    return result


PUBLIC_INGESTION_STATES = {"staged_source_artifact", "imported_private_backend", "published_source_catalog"}
# Only independently reviewed, non-personal aggregate manifests are admitted.
PUBLIC_INGESTION_SOURCES = {"NOAA Storm Events Details"}


def published_external_ingestions(directory: Path):
    """Read reviewed aggregate-only manifests from other source-ingest workflows.

    Future source types may be added to the allowlist after a separate privacy
    and domain-semantics review. No arbitrary JSON fields get copied to Pages.
    """
    if not directory.is_dir():
        return []
    found = {}
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        name = data.get("source")
        state = data.get("state")
        if (data.get("schema_version") != "1.0" or
                name not in PUBLIC_INGESTION_SOURCES or
                state not in PUBLIC_INGESTION_STATES or
                name in found):
            raise ValueError(f"Invalid or duplicate public ingestion manifest: {path.name}")
        count = data.get("records")
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError(f"Nonpositive or missing published ingestion record count: {path.name}")
        date = data.get("checked_at")
        if not isinstance(date, str) or "T" not in date or not date.endswith(("+00:00", "Z")):
            raise ValueError(f"Missing UTC source retrieval time: {path.name}")
        link = data.get("artifact_run_url", "")
        if link and not str(link).startswith("https://github.com/jhennessy-pharm3r/FacilityTest/actions/runs/"):
            raise ValueError("Unexpected public artifact workflow reference")
        found[name] = {
            "source": name,
            "state": state,
            "records": count,
            "checked_at": date,
            "scope": str(data.get("scope", ""))[:260],
            "details": str(data.get("details", ""))[:460],
            "documentation": str(data.get("documentation", ""))[:400],
            "artifact_run_url": link,
        }
    return list(found.values())


def merge_existing_public_status(path: Path, ingestion_dir: Path):
    """Update ingestion rows only, preserving actual prior probe timestamps."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1.0" or not isinstance(payload.get("ingestions"), list):
        raise ValueError("Cannot update unrecognized or missing public source-health report")
    additions = published_external_ingestions(ingestion_dir)
    known = {x["source"] for x in additions}
    payload["ingestions"] = [x for x in payload["ingestions"] if x.get("source") not in known] + additions
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                    encoding="utf-8")
    return additions


def build(primary: Path, extended: Path, catalog_dir: Path, generated_at: str, run_url: str, ingestion_dir: Path | None = None):
    extended_meta = {name: {"documentation": spec["documentation"]}
                     for name, spec in EXTENDED_BY_NAME.items()}
    primary_meta = {name: {"documentation": docs}
                    for name, (docs, _) in SOURCE_META.items()}
    return {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "run_url": run_url,
        "meaning": "Connectivity and registered source-identity publication only. Not facility matching or peril screening.",
        "checks": checks_from_file(primary, primary_meta, PRIMARY_STATES, generated_at),
        "extended_checks": checks_from_file(extended, extended_meta, EXTENDED_STATES, generated_at),
        "ingestions": published_catalogs(catalog_dir) + published_external_ingestions(ingestion_dir or Path("web/ingestion")),
    }


def main():
    parser = argparse.ArgumentParser(description="Build public source health metadata only")
    parser.add_argument("--primary", type=Path, default=Path("source-health-report.json"))
    parser.add_argument("--extended", type=Path, default=Path("extended-source-report.json"))
    parser.add_argument("--catalog-dir", type=Path, default=Path("web/registry"))
    parser.add_argument("--output", type=Path, default=Path("web/source-status.json"))
    parser.add_argument("--ingestion-dir", type=Path, default=Path("web/ingestion"))
    parser.add_argument("--merge-only", action="store_true", help="Update ingestion metadata without implying a new probe")
    args = parser.parse_args()
    if args.merge_only:
        added = merge_existing_public_status(args.output, args.ingestion_dir)
        print(f"Updated {len(added)} validated ingestion metadata record(s); probe timestamps unchanged")
        return
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    repo = os.getenv("GITHUB_REPOSITORY", "jhennessy-pharm3r/FacilityTest")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    run_url = f"https://github.com/{repo}/actions/runs/{run_id}" if run_id else ""
    data = build(args.primary, args.extended, args.catalog_dir, now, run_url, args.ingestion_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"Published metadata: {len(data['checks'])} primary checks, "
          f"{len(data['extended_checks'])} extended checks, "
          f"{len(data['ingestions'])} ingestion states to {args.output}")


if __name__ == "__main__":
    main()
