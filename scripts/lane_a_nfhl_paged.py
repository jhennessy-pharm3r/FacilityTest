"""FEMA NFHL source-only exhaustive retrieval *inside explicit geographic envelopes*.

Uses official layer OBJECTID enumeration, bounded source API batches, native IDs,
retained raw responses, independent source-only SQLite/rtree and run manifests.
This is NOT nationwide NFHL ingestion, insured property matching, or risk scoring.
"""
import argparse
import hashlib
import json
import math
import pathlib
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

FEMA_LAYER = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28"
# Public geographic test windows; NOT actual insured or corroborated property sites.
WINDOWS = {
    "new_orleans": (-90.084, 29.946, -90.080, 29.950),
    "houston": (-95.375, 29.758, -95.371, 29.762),
    "sacramento": (-121.502, 38.579, -121.498, 38.583),
    "miami": (-80.199, 25.765, -80.195, 25.769),
    "new_york": (-74.012, 40.707, -74.008, 40.711),
    "seattle": (-122.338, 47.601, -122.334, 47.605),
}
REQUIRED_FIELDS = {"OBJECTID", "DFIRM_ID", "FLD_AR_ID", "FLD_ZONE", "SOURCE_CIT"}


def envelope(bbox):
    if (len(bbox) != 4 or not all(isinstance(v, (int, float)) and
            math.isfinite(v) for v in bbox)):
        raise ValueError("Invalid WGS84 envelope")
    left, south, right, north = bbox
    if not (-180 <= left < right <= 180 and -90 <= south < north <= 90):
        raise ValueError("Invalid WGS84 envelope limits")
    return json.dumps({"xmin": left, "ymin": south, "xmax": right, "ymax": north,
                       "spatialReference": {"wkid": 4326}}, separators=(",", ":"))


def query_http(params, *, timeout=23, attempts=4):
    """Official ArcGIS GET+POST transport retries (same authenticated-free endpoint).

    The POST method is explicitly supported by ArcGIS REST. A successful attempt
    retains its actual transport and the exact application/x-www-form-urlencoded
    request parameters in the archived receipt. No caching or alternate mirror.
    """
    encoded = urllib.parse.urlencode(params).encode("ascii")
    endpoint = FEMA_LAYER + "/query"
    last_error = None
    for attempt in range(attempts):
        method = "GET" if attempt % 2 == 0 else "POST"
        try:
            req = urllib.request.Request(
                endpoint + "?" + encoded.decode("ascii") if method == "GET" else endpoint,
                data=None if method == "GET" else encoded,
                method=method,
                headers={
                    "User-Agent": "FacilityRisk-FEMA-NFHL-Paged-Source-QA/1.1",
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                }
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read(15_000_001)
                final_url = response.geturl()
            if len(raw) > 15_000_000:
                raise ValueError("JSON response exceeds 15 MB per-batch limit")
            result = json.loads(raw)
            if not isinstance(result, dict) or result.get("error"):
                raise ValueError("ArcGIS error: " + str(
                    result.get("error") if isinstance(result, dict) else type(result))[:300])
            return result, raw, final_url, {
                "http_method": method, "attempt_count": attempt + 1,
                "official_arcgis_query_endpoint": endpoint,
            }
        except (urllib.error.URLError, TimeoutError, OSError, ValueError,
                json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(min(attempt + 1, 2))
    raise RuntimeError(
        "FEMA official GET+POST request failed after " + str(attempts) +
        " authorized attempts: " + str(last_error)[:450])


def source_key(attrs):
    if not isinstance(attrs, dict):
        raise ValueError("Missing FEMA source attributes")
    dfirm, area, oid = attrs.get("DFIRM_ID"), attrs.get("FLD_AR_ID"), attrs.get("OBJECTID")
    if dfirm and area:
        return "dfirm:" + str(dfirm) + ":fld_ar:" + str(area)
    if isinstance(oid, int) and not isinstance(oid, bool):
        return "service_objectid:" + str(oid)
    raise ValueError("Missing FEMA polygon native source ID")


def geometry_bbox(feature):
    geometry = feature.get("geometry")
    rings = geometry.get("rings") if isinstance(geometry, dict) else None
    if not isinstance(rings, list) or not rings:
        raise ValueError("FEMA polygon missing rings")
    xmin, ymin, xmax, ymax = 180., 90., -180., -90.
    for ring in rings:
        if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
            raise ValueError("FEMA polygon ring unclosed or invalid length")
        for p in ring:
            if (not isinstance(p, list) or len(p) < 2 or
                not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                        and math.isfinite(v) for v in p[:2]) or
                not (-180 <= p[0] <= 180 and -90 <= p[1] <= 90)):
                raise ValueError("FEMA polygon coordinate is not WGS84")
            xmin, ymin, xmax, ymax = (min(xmin, p[0]), min(ymin, p[1]),
                                      max(xmax, p[0]), max(ymax, p[1]))
    if xmin >= xmax or ymin >= ymax:
        raise ValueError("FEMA polygon has zero-size bounding box")
    return xmin, ymin, xmax, ymax


def init_db(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS fema_source_features(
      source_key TEXT PRIMARY KEY,
      objectid INTEGER NOT NULL, dfirm_id TEXT,
      fld_ar_id TEXT, flood_zone TEXT, zone_subtype TEXT,
      sfha_tf TEXT, source_cit TEXT, version_id TEXT,
      feature_json TEXT NOT NULL, first_seen_utc TEXT NOT NULL,
      original_reply_sha256 TEXT NOT NULL, geometry_tolerance_degrees REAL NOT NULL
    );
    CREATE UNIQUE INDEX IF NOT EXISTS fema_native_objectid ON
      fema_source_features(objectid);
    CREATE TABLE IF NOT EXISTS fema_window_membership(
      window TEXT NOT NULL, source_key TEXT NOT NULL,
      PRIMARY KEY (window,source_key),
      FOREIGN KEY(source_key) REFERENCES fema_source_features(source_key)
    );
    CREATE INDEX IF NOT EXISTS fema_window_key ON fema_window_membership(source_key);
    CREATE VIRTUAL TABLE IF NOT EXISTS fema_source_bounds USING rtree(
      feature_rowid,min_lon,max_lon,min_lat,max_lat
    );
    """)
    return db


def capture(fetch, params, target):
    response = fetch(params)
    if len(response) == 4:
        doc, raw, url, transport = response
    else:
        doc, raw, url = response
        transport = {"http_method": "fixture_or_unspecified"}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return doc, {"source_url": url,
                 "original_request_parameters": params,
                 "transport": transport,
                 "raw_file": target.name,
                 "sha256": hashlib.sha256(raw).hexdigest(),
                 "bytes": len(raw)}


def run(outdir, fetch=query_http, windows=None, *, max_ids_per_window=250,
        batch_size=4):
    if batch_size < 1 or batch_size > 20 or max_ids_per_window < 1:
        raise ValueError("Invalid bounded query size")
    outdir = pathlib.Path(outdir)
    rawdir = outdir / "raw"
    outdir.mkdir(parents=True, exist_ok=True)
    db = init_db(outdir / "fema-window-index.sqlite")
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "publisher": "FEMA", "dataset": "NFHL S_Fld_Haz_Ar", "layer_id": 28,
        "source_url": FEMA_LAYER,
        "scope": "source_polygon_complete_within_test_envelopes_NOT_national",
        "actual_physical_site_matches": 0, "durable_deployed_records": 0,
        "national_source_complete": False, "effective_date_coverage": "unverified_per_DFIRM",
        "windows": {}, "source_only_sqlite": "fema-window-index.sqlite",
        "source_metadata": None,
    }
    samples = windows if windows is not None else WINDOWS
    if not samples:
        raise ValueError("At least one explicit bounding box required")
    try:
        # Metadata captured with the same audited transport, but /28 rather than /28/query.
        # Query 1=0 returns the actual field schema without transferring polygons.
        metadata_params = {"f": "json", "where": "1=0",
                           "outFields": "*", "returnGeometry": "false"}
        meta, meta_receipt = capture(fetch, metadata_params, rawdir / "field_probe.json")
        names = {f.get("name") for f in meta.get("fields", []) if isinstance(f, dict)}
        if not REQUIRED_FIELDS.issubset(names):
            raise ValueError("Official FEMA query has unexpected missing fields: "
                             + repr(sorted(REQUIRED_FIELDS - names)))
        manifest["source_metadata"] = {**meta_receipt, "reported_fields": sorted(names),
                                        "reported_geometry_type": meta.get("geometryType"),
                                        "published_effective_dates_not_in_this_schema": True}
    except (RuntimeError, ValueError, KeyError) as exc:
        manifest["metadata_error"] = str(exc)
    # A transient metadata failure does not prevent collecting independently
    # verifiable source rows; it DOES block the final schema-complete gate.

    for name, bbox in samples.items():
        win = {"bbox_wgs84": list(bbox), "status": "FAILED",
               "id_count": None, "server_count": None,
               "accepted_count": 0, "rejected_count": 0, "duplicated_ids": 0,
               "retrieved_ids": 0, "source_citations": {}, "chunks": [],
               "simplified_geometry_records": 0, "attempt_errors": []}
        manifest["windows"][name] = win
        try:
            geometry = envelope(bbox)
            common = {"f": "json", "geometry": geometry,
                      "geometryType": "esriGeometryEnvelope", "inSR": 4326,
                      "spatialRel": "esriSpatialRelIntersects", "where": "1=1"}
            ids_doc, receipt = capture(fetch,
                {**common, "returnIdsOnly": "true"},
                rawdir / (name + ".ids.json"))
            win["source_ids_receipt"] = receipt
            ids = ids_doc.get("objectIds")
            if not isinstance(ids, list) or not all(
                isinstance(i, int) and not isinstance(i, bool) for i in ids
            ):
                raise ValueError("Official returnIdsOnly did not provide valid numeric IDs")
            if len(ids) != len(set(ids)):
                raise ValueError("Official ID listing duplicates OBJECTIDs")
            ids = sorted(ids)
            win["id_count"] = len(ids)
            if len(ids) > max_ids_per_window:
                raise ValueError("Bounded test window exceeds max_ids_per_window (" +
                                 str(len(ids)) + " > " + str(max_ids_per_window) + ")")
            count_doc, count_receipt = capture(fetch,
                {**common, "returnCountOnly": "true"},
                rawdir / (name + ".count.json"))
            win["source_count_receipt"] = count_receipt
            server_count = count_doc.get("count")
            if not isinstance(server_count, int) or server_count != len(ids):
                raise ValueError("Official count/IDs disagree " + str(server_count) +
                                 " != " + str(len(ids)))
            win["server_count"] = server_count
            observed = set()

            def iter_completed_batches(ids_subset, suffix, *, tolerance=None):
                # One oversized/failed geometry must not discard already
                # downloaded sibling IDs. Original retries are explicitly logged.
                params = {
                    "f": "json", "where": "1=1",
                    "objectIds": ",".join(str(i) for i in ids_subset),
                    "outFields": "*", "returnGeometry": "true", "outSR": 4326,
                }
                if tolerance is not None:
                    # FEMA-native source polygons, generalized server-side:
                    # evidence is unsuitable for surveyed boundary decisions.
                    params["maxAllowableOffset"] = tolerance
                path_name = (name + ".batch_" + suffix +
                             (".generalized_" + str(tolerance) if tolerance else "") + ".json")
                try:
                    payload, receipt = capture(fetch, params, rawdir / path_name)
                    receipt.update({
                        "requested_objectids": list(ids_subset),
                        "geometry_tolerance_degrees": tolerance or 0,
                        "response_feature_count": len(payload.get("features", []))
                                                  if isinstance(payload.get("features"), list) else None,
                        "exceeded_transfer_limit": bool(payload.get("exceededTransferLimit")),
                    })
                    win["chunks"].append(receipt)
                    if payload.get("exceededTransferLimit"):
                        raise RuntimeError("ArcGIS exceededTransferLimit for IDs " + str(ids_subset))
                    if not isinstance(payload.get("features"), list):
                        raise ValueError("FEMA batch does not contain features list")
                    yield payload, receipt
                    return
                except (RuntimeError, ValueError) as exc:
                    win["attempt_errors"].append({
                        "requested_objectids": list(ids_subset),
                        "tolerance_degrees": tolerance, "error": str(exc)[:500],
                    })
                    if len(ids_subset) > 1:
                        mid = len(ids_subset) // 2
                        yield from iter_completed_batches(ids_subset[:mid], suffix + "a")
                        yield from iter_completed_batches(ids_subset[mid:], suffix + "b")
                        return
                    tolerances = (0.000005, 0.00005)
                    if tolerance is None:
                        yield from iter_completed_batches(ids_subset, suffix, tolerance=tolerances[0])
                        return
                    if tolerance == tolerances[0]:
                        yield from iter_completed_batches(ids_subset, suffix, tolerance=tolerances[1])
                        return
                    raise

            for k in range(0, len(ids), batch_size):
                subset = ids[k:k + batch_size]
                for payload, chunk_receipt in iter_completed_batches(
                    subset, str(k // batch_size).zfill(4)
                ):
                    if payload.get("geometryType") not in ("esriGeometryPolygon", None):
                        raise ValueError("Unexpected geometry type")
                    spatial_ref = payload.get("spatialReference", {})
                    if spatial_ref and spatial_ref.get("wkid") not in (4326, 4269):
                        raise ValueError("Official query did not return expected WGS84 CRS")
                    feats = payload.get("features")
                    if not isinstance(feats, list):
                        raise ValueError("Official batch missing feature list")
                    actual = {f.get("attributes", {}).get("OBJECTID") for f in feats}
                    if actual != set(chunk_receipt["requested_objectids"]):
                        raise ValueError("Missing/extra OBJECTIDs in batch: expected " +
                                         repr(chunk_receipt["requested_objectids"]) + " got " + repr(sorted(actual)))
                    for feature in feats:
                        attrs = feature["attributes"]
                        key = source_key(attrs)
                        bounds = geometry_bbox(feature)
                        oid = attrs["OBJECTID"]
                        if oid in observed:
                            raise ValueError("Duplicate OBJECTID across chunk responses")
                        observed.add(oid)
                        packed = json.dumps(feature, separators=(",", ":"), sort_keys=True)
                        stored = db.execute("SELECT feature_json FROM fema_source_features WHERE source_key=?", (key,)).fetchone()
                        if stored is not None and stored[0] != packed:
                            raise ValueError("Conflicting official geometry for same FEMA source key")
                        if stored is None:
                            cur = db.execute(
                                "INSERT INTO fema_source_features VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                (key, oid, attrs.get("DFIRM_ID"), attrs.get("FLD_AR_ID"),
                                 attrs.get("FLD_ZONE"), attrs.get("ZONE_SUBTY"),
                                 attrs.get("SFHA_TF"), attrs.get("SOURCE_CIT"),
                                 attrs.get("VERSION_ID"), packed,
                                 datetime.now(timezone.utc).isoformat(),
                                 chunk_receipt["sha256"],
                                 chunk_receipt["geometry_tolerance_degrees"]))
                            db.execute("INSERT INTO fema_source_bounds VALUES(?,?,?,?,?)",
                                       (cur.lastrowid, bounds[0], bounds[2], bounds[1], bounds[3]))
                        db.execute("INSERT OR IGNORE INTO fema_window_membership VALUES(?,?)", (name, key))
                        if chunk_receipt["geometry_tolerance_degrees"]:
                            win["simplified_geometry_records"] += 1
                        citation = str(attrs.get("SOURCE_CIT") or "MISSING")
                        win["source_citations"][citation] = win["source_citations"].get(citation, 0) + 1
            win["retrieved_ids"] = len(observed)
            win["accepted_count"] = len(observed)
            if observed != set(ids):
                raise ValueError("Missing IDs after all batches: " + str(sorted(set(ids) - observed)))
            indexed = db.execute("SELECT COUNT(*) FROM fema_window_membership WHERE window=?", (name,)).fetchone()[0]
            if indexed != len(ids):
                raise ValueError("Source window membership index does not reconcile")
            # Limit strictness: rtree candidates may include shapes not intersecting the window.
            minx, miny, maxx, maxy = bbox
            rtree_candidates = db.execute(
                "SELECT COUNT(DISTINCT r.feature_rowid) FROM fema_source_bounds r "
                "WHERE r.min_lon<=? AND r.max_lon>=? AND r.min_lat<=? AND r.max_lat>=?",
                (maxx, minx, maxy, miny)).fetchone()[0]
            if rtree_candidates < indexed:
                raise ValueError("Rtree is missing indexed FEMA polygon candidates")
            win["rtree_candidate_count"] = rtree_candidates
            win["status"] = "COMPLETE_WITHIN_WINDOW"
            win["all_geometry_native_resolution"] = win["simplified_geometry_records"] == 0
        except (RuntimeError, ValueError, KeyError, sqlite3.Error, TypeError) as exc:
            win["status"] = "INCOMPLETE"
            win["error"] = str(exc)[:800]
            win["retrieved_ids"] = db.execute(
                "SELECT COUNT(*) FROM fema_window_membership WHERE window=?", (name,)
            ).fetchone()[0]
            win["accepted_count"] = win["retrieved_ids"]
        finally:
            db.commit()

    manifest["source_feature_count"] = db.execute("SELECT COUNT(*) FROM fema_source_features").fetchone()[0]
    manifest["window_membership_count"] = db.execute("SELECT COUNT(*) FROM fema_window_membership").fetchone()[0]
    manifest["rtree_index_count"] = db.execute("SELECT COUNT(*) FROM fema_source_bounds").fetchone()[0]
    manifest["distinct_dfirm_ids"] = db.execute(
        "SELECT COUNT(DISTINCT dfirm_id) FROM fema_source_features").fetchone()[0]
    manifest["null_dfirm_ids"] = db.execute("SELECT COUNT(*) FROM fema_source_features WHERE dfirm_id IS NULL").fetchone()[0]
    manifest["null_source_citations"] = db.execute("SELECT COUNT(*) FROM fema_source_features WHERE source_cit IS NULL").fetchone()[0]
    manifest["zone_distribution"] = dict(db.execute(
        "SELECT COALESCE(flood_zone,'UNKNOWN'),COUNT(*) FROM fema_source_features GROUP BY 1").fetchall())
    manifest["sqlite_quick_check"] = db.execute("PRAGMA quick_check").fetchone()[0]
    manifest["successful_windows"] = sum(w["status"] == "COMPLETE_WITHIN_WINDOW" for w in manifest["windows"].values())
    manifest["requested_windows"] = len(manifest["windows"])
    manifest["geometry_generalized_observations"] = sum(
        w["simplified_geometry_records"] for w in manifest["windows"].values()
    )
    manifest["all_native_resolution"] = manifest["geometry_generalized_observations"] == 0
    manifest["all_requested_windows_complete"] = (
        manifest["successful_windows"] == manifest["requested_windows"]
        and manifest["source_metadata"] is not None
        and manifest["rtree_index_count"] == manifest["source_feature_count"]
        and manifest["sqlite_quick_check"] == "ok"
    )
    db.close()
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", default="data/lane_a/paged_windows")
    p.add_argument("--max-per-window", type=int, default=250)
    p.add_argument("--batch-size", type=int, default=4)
    args = p.parse_args(argv)
    m = run(args.out_dir, max_ids_per_window=args.max_per_window, batch_size=args.batch_size)
    print("LANE_A_NFHL_PAGED=" + json.dumps({
        "all_requested_windows_complete": m.get("all_requested_windows_complete", False),
        "windows": {n: {"status": w["status"], "count": w["id_count"],
                         "accepted": w["accepted_count"], "indexed": w["retrieved_ids"],
                         "error": w.get("error")} for n, w in m["windows"].items()},
        "source_feature_count": m.get("source_feature_count"),
        "rtree_index_count": m.get("rtree_index_count"),
        "zone_distribution": m.get("zone_distribution"),
        "effective_date_coverage": m["effective_date_coverage"],
    }, sort_keys=True))
    return 0 if m.get("all_requested_windows_complete", False) else 2


if __name__ == "__main__":
    sys.exit(main())
