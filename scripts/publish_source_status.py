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


def build(primary: Path, extended: Path, catalog_dir: Path, generated_at: str, run_url: str):
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
        "ingestions": published_catalogs(catalog_dir),
    }


def main():
    parser = argparse.ArgumentParser(description="Build public source health metadata only")
    parser.add_argument("--primary", type=Path, default=Path("source-health-report.json"))
    parser.add_argument("--extended", type=Path, default=Path("extended-source-report.json"))
    parser.add_argument("--catalog-dir", type=Path, default=Path("web/registry"))
    parser.add_argument("--output", type=Path, default=Path("web/source-status.json"))
    args = parser.parse_args()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    repo = os.getenv("GITHUB_REPOSITORY", "jhennessy-pharm3r/FacilityTest")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    run_url = f"https://github.com/{repo}/actions/runs/{run_id}" if run_id else ""
    data = build(args.primary, args.extended, args.catalog_dir, now, run_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"Published metadata: {len(data['checks'])} primary checks, "
          f"{len(data['extended_checks'])} extended checks, "
          f"{len(data['ingestions'])} ingestion states to {args.output}")


if __name__ == "__main__":
    main()
