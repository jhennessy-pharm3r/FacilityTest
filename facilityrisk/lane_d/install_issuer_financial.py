"""Coordinator: reviewed issuer BI accounting case indexes, NOT insurance claims.

Two documented issuer source sets only. Each accepted financial fact, accounting
period and original source publication digest is pinned to a first-party
source-ingestion CI audit. Does not extrapolate to other facilities, infer
insurance policy cover, or reconstruct documents from unsupported SEC access.

Production installer copies only source financial SQLite + QA manifest into
versioned read-only directories. No individual insured property is linked.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from urllib.parse import urlparse
from uuid import uuid4

from .install_source_index import sha256_file

SPECS = {
    "crane": {
        "filename": "crane_issuer_financial_staging.sqlite",
        "issuer": "Crane Company", "cik": "1944013",
        "rows": 7, "records_manifest_key": "financial_records_extracted",
        "index_manifest_key": "local_staging_financial_records_indexed",
        "documents_key": "document_provenance", "digest_key": "original_pdf_sha256",
        "source_id_field": "native_publication_id",
        "stored_sha_field": "source_document_sha256",
        "original_document_host": "investors.craneco.com",
        "docs": {
            "crane-2024-10k-marion-hurricane": "0fdecf744b2a414316322de37ee5a7288e8932e617a3394a4372f5a5a02da546",
            "crane-2025-q2-10q-marion-hurricane": "e759a4eb321ff90387de6d69ed6f370cf9db4a1ffe2085b211922fe5704b4bde",
        },
        "financials": {
            ("crane-2024-10k-marion-hurricane","INCURRED_PROPERTY_REPAIR_REMEDIATION_EXPENSE","2024_FY"): 23300000,
            ("crane-2024-10k-marion-hurricane","RECEIVED_HURRICANE_INSURANCE_RECOVERY_UNALLOCATED","2024_FY"): 20000000,
            ("crane-2024-10k-marion-hurricane","REMAINING_INSURANCE_RECEIVABLE","2024_12_31_BALANCE"): 2800000,
            ("crane-2025-q2-10q-marion-hurricane","RECEIVED_BI_PROCEEDS_FOR_LOST_PROFITS","2025_Q2"): 4000000,
            ("crane-2025-q2-10q-marion-hurricane","CUMULATIVE_HURRICANE_DAMAGE_EXPENSE","2024_EVENT_THROUGH_2025_06_30"): 29100000,
            ("crane-2025-q2-10q-marion-hurricane","CUMULATIVE_HURRICANE_INSURANCE_RECOVERY_UNALLOCATED","2024_EVENT_THROUGH_2025_06_30"): 25000000,
            ("crane-2025-q2-10q-marion-hurricane","REMAINING_INSURANCE_RECEIVABLE","2025_06_30_BALANCE"): 3600000,
        },
    },
    "pebblebrook": {
        "filename": "issuer_bi_income_staging.sqlite",
        "issuer": "Pebblebrook Hotel Trust", "cik": "1474098",
        "rows": 5, "records_manifest_key": "financial_statement_records_normalized",
        "index_manifest_key": "financial_statement_records_staged_sqlite",
        "documents_key": "published_source_hashes", "digest_key": "original_sha256",
        "source_id_field": "source_document_id",
        "stored_sha_field": "document_sha256",
        "original_document_host": "investor.pebblebrookhotels.com",
        "docs": {
            "pebblebrook-fy2024-release-20250226": "033d6905706683e5bbe28ad2a30e32a5907bb5ca00bc3d6cb245048081fe5523",
            "pebblebrook-fy2025-release-20260225": "b9d27363b9172a45f17980f99a9a2ee8a3d66f0876ed125e551a191c24d7c61b",
        },
        "financials": {
            ("pebblebrook-fy2024-release-20250226","RECOGNIZED_BI_INSURANCE_INCOME","2024_FY"): 23800000,
            ("pebblebrook-fy2024-release-20250226","RECOGNIZED_BI_INSURANCE_INCOME_Q4_COMPONENT","2024_Q4"): 5400000,
            ("pebblebrook-fy2024-release-20250226","RECOGNIZED_BI_INSURANCE_INCOME_PRIOR_YEAR","2023_FY"): 33000000,
            ("pebblebrook-fy2025-release-20260225","RECOGNIZED_BI_INSURANCE_INCOME","2025_FY"): 12700000,
            ("pebblebrook-fy2025-release-20260225","RECOGNIZED_BI_INSURANCE_INCOME_Q4_COMPONENT","2025_Q4"): 3100000,
        },
    },
}
PRIVATE_TABLES = (
    "facilities", "evidence", "insurance_policies", "insurance_terms",
    "facility_assets", "sec_findings", "review_approvals", "universal_sites",
)


def _document_fingerprint(spec):
    data = json.dumps(spec["docs"], sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def _source_document_receipts(m, spec):
    raw = m.get(spec["documents_key"])
    if not isinstance(raw, list) or len(raw) != len(spec["docs"]):
        raise ValueError("Original issuer source publication evidence is missing")
    docs = {}
    for info in raw:
        if not isinstance(info, dict):
            raise ValueError("Invalid source document metadata")
        key = info.get("source_id")
        digest = info.get(spec["digest_key"])
        url = info.get("original_source_url", info.get("original_url"))
        parsed = urlparse(str(url))
        if (key not in spec["docs"] or digest != spec["docs"][key]
            or parsed.scheme != "https" or parsed.hostname != spec["original_document_host"]):
            raise ValueError("Issuer publication URL/identity/original hash not approved")
        if key in docs:
            raise ValueError("Duplicate source publication identity")
        if (info.get("insured_carrier_confirmation", False) or
            info.get("publisher_claim_cash_paid_verified", False)):
            raise ValueError("Issuer reports cannot be presented as independently carrier-confirmed")
        docs[key] = digest
    if docs != spec["docs"]:
        raise ValueError("Not all original issuer publication digests are present")
    return docs


def audit_bundle(path, dataset, expected_db_sha256=None):
    if dataset not in SPECS:
        raise ValueError("Unreviewed issuer case study source index family")
    spec = SPECS[dataset]
    path = Path(path)
    db_path = path / spec["filename"]
    m_path = path / "manifest.json"
    if path.is_symlink() or db_path.is_symlink() or m_path.is_symlink():
        raise ValueError("Symlinked source financial bundle is prohibited")
    if not db_path.is_file() or not m_path.is_file():
        raise FileNotFoundError("Original issuer source-only SQLite and manifest required")
    m = json.loads(m_path.read_text(encoding="utf-8"))
    count = spec["rows"]
    if (m.get(spec["records_manifest_key"]) != count
        or m.get(spec["index_manifest_key"]) != count
        or m.get("deployed", 0) != 0
        or m.get("durable_backend_indexed", 0) != 0):
        raise ValueError("Original issuer source counts or source stage not verified")
    if dataset == "crane":
        if (m.get("pdf_documents_downloaded_and_verified") != 2
            or m.get("pdf_documents_failed_or_blocked") != 0
            or m.get("independent_carrier_confirmed_claims", 0) != 0):
            raise ValueError("Crane original source PDF was not validated")
    else:
        if (m.get("downloaded_publisher_documents") != 2
            or m.get("failed_sources") != []
            or m.get("independently_insurer_verified_paid_bi_claims", 0) != 0):
            raise ValueError("Pebblebrook original issuer publication missing or failed")
    docs = _source_document_receipts(m, spec)
    sqlite_sha = sha256_file(db_path)
    if expected_db_sha256 is not None and sqlite_sha != expected_db_sha256:
        raise ValueError("Original issuer source SQL index hash not pinned")
    with sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Issuer source financial SQLite integrity failed")
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "source_financial_observations" not in tables or tables.intersection(PRIVATE_TABLES):
            raise ValueError("Issuer index is not an isolated source-only finance database")
        if dataset == "crane":
            sql = """SELECT evidence_key,source_id,document_sha256,financial_metric_kind,
                     accounting_period,reported_amount_usd,record_json
                     FROM source_financial_observations"""
        else:
            sql = """SELECT evidence_key,source_id,original_sha256,kind,
                     accounting_period,amount_usd,raw_json
                     FROM source_financial_observations"""
        known = {}
        for key, source_id, document_sha, kind, period, amount, raw in db.execute(sql):
            details = json.loads(raw)
            if (source_id not in docs or docs[source_id] != document_sha
                or details.get(spec["source_id_field"]) != source_id
                or details.get(spec["stored_sha_field"]) != document_sha
                or details.get("evidence_key") != key):
                raise ValueError("Original financial source identity or record hash mismatch")
            if (details.get("carrier_claim_payment_independently_verified")
                or details.get("independent_insurer_claim_payment_confirmed")
                or details.get("actual_site_power_outage_confirmed")
                or details.get("underlying_site_outage_verified")):
                raise ValueError("Cannot assert independently verified claims or site outage")
            source_item = (source_id, kind, period)
            if source_item in known:
                raise ValueError("Duplicate issuer financial observation key")
            if type(amount) is not int or amount != spec["financials"].get(source_item):
                raise ValueError("Issuer source-published accounting amount/period drift")
            known[source_item] = amount
        if known != spec["financials"]:
            raise ValueError("Missing original issuer typed accounting observation")
    return {
        "source_case": dataset,
        "source_issuer": spec["issuer"],
        "original_publisher_documents_verified": len(docs),
        "original_publication_digest_set_sha256": _document_fingerprint(spec),
        "source_financial_records": count,
        "index_sha256": sqlite_sha,
        "index_bytes": db_path.stat().st_size,
        "source_only_financial_index": True,
        "issuer_reported_not_independent_insurer_claims": True,
        "verified_insured_sites": 0,
        "deployed_public_pages_rows": 0,
    }


def install(bundle, destination, dataset, expected_db_sha256=None):
    report = audit_bundle(bundle, dataset, expected_db_sha256)
    spec = SPECS[dataset]
    dest = Path(destination)
    if dest.is_symlink() or (dest / dataset).is_symlink():
        raise ValueError("Issuer index destination cannot be symlinked")
    root = dest / dataset
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".install.lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.close(fd)
        version = (report["original_publication_digest_set_sha256"][:16] + "-" +
                   report["index_sha256"][:16])
        version_dir = root / "versions" / version
        if not version_dir.exists():
            version_dir.parent.mkdir(parents=True, exist_ok=True)
            tmp = Path(tempfile.mkdtemp(prefix=".staging-", dir=version_dir.parent))
            try:
                idx = tmp / spec["filename"]
                shutil.copyfile(Path(bundle) / spec["filename"], idx)
                shutil.copyfile(Path(bundle) / "manifest.json", tmp / "manifest.json")
                os.chmod(idx, 0o444)
                audit_bundle(tmp, dataset, expected_db_sha256=report["index_sha256"])
                (tmp / "source_validation.json").write_text(json.dumps(report, indent=2) + "\n")
                os.replace(tmp, version_dir)
            finally:
                if tmp.exists():
                    shutil.rmtree(tmp)
        else:
            audit_bundle(version_dir, dataset, expected_db_sha256=report["index_sha256"])
        ptr = {
            "dataset": dataset, "version": version, "index_sha256": report["index_sha256"],
            "publisher_digest_set_sha256": report["original_publication_digest_set_sha256"],
            "source_financial_records": report["source_financial_records"],
            "deployed_to_public_app": False,
        }
        temp_ptr = root / (".next-" + uuid4().hex)
        try:
            temp_ptr.write_text(json.dumps(ptr, indent=2) + "\n")
            os.replace(temp_ptr, root / "current.json")
        finally:
            temp_ptr.unlink(missing_ok=True)
        return verify_install(destination, dataset)
    finally:
        lock.unlink(missing_ok=True)


def resolve_current(dest, dataset):
    if dataset not in SPECS:
        raise ValueError("Unreviewed issuer case")
    root = Path(dest) / dataset
    ptr_path = root / "current.json"
    if ptr_path.is_symlink() or not ptr_path.is_file():
        raise FileNotFoundError("Issuer evidence index is not installed")
    info = json.loads(ptr_path.read_text())
    version = str(info.get("version", ""))
    import re
    if not re.fullmatch(r"[0-9a-f]{16}-[0-9a-f]{16}", version) or info.get("dataset") != dataset:
        raise ValueError("Untrusted issuer index pointer")
    idx = root / "versions" / version / SPECS[dataset]["filename"]
    if idx.is_symlink() or not idx.is_file():
        raise FileNotFoundError("Installed issuer financial index missing")
    return idx, info


def verify_install(dest, dataset):
    idx, pointer = resolve_current(dest, dataset)
    report = audit_bundle(idx.parent, dataset, pointer.get("index_sha256"))
    if (report["original_publication_digest_set_sha256"] != pointer.get("publisher_digest_set_sha256")
        or report["source_financial_records"] != pointer.get("source_financial_records")):
        raise ValueError("Original publisher financial source install receipt altered")
    return report


def main():
    parser = argparse.ArgumentParser()
    cmd = parser.add_subparsers(dest="command", required=True)
    ins = cmd.add_parser("install")
    ins.add_argument("--bundle", type=Path, required=True)
    ins.add_argument("--dest", type=Path, required=True)
    ins.add_argument("--case", choices=tuple(SPECS), required=True)
    ins.add_argument("--index-sha256")
    ck = cmd.add_parser("verify")
    ck.add_argument("--dest", type=Path, required=True)
    ck.add_argument("--case", choices=tuple(SPECS), required=True)
    args = parser.parse_args()
    value = (install(args.bundle, args.dest, args.case, args.index_sha256)
             if args.command == "install"
             else verify_install(args.dest, args.case))
    print(json.dumps(value, indent=2))


if __name__ == "__main__":
    main()
