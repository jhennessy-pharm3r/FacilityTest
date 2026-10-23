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


def query_http(params, *, timeout=25, attempts=3):
    url = FEMA_LAYER + "/query?" + urllib.parse.urlencode(params)
    last_error = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "FacilityRisk-FEMA-NFHL-Paged-Source-QA/1.0",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read(15_000_001)
                final_url = response.geturl()
            if len(raw) > 15_000_000:
                raise ValueError("JSON response exceeds 15 MB per-batch limit")
            result = json.loads(raw)
            if not isinstance(result, dict) or result.get("error"):
                raise ValueError("ArcGIS error: " + str(result.get("error") if isinstance(result, dict) else type(result))[:300])
            return result, raw, final_url
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(attempt + 1)
    raise RuntimeError("FEMA official request failed after " + str(attempts) +
                       " attempts: " + str(last_error)[:450])


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
      feature_json TEXT NOT NULL, first_seen_utc TEXT NOT NULL
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
    doc, raw, url = fetch(params)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return doc, {"source_url": url,
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
    if manifest["source_metadata"] is None:
        # No reliable source schema: do not report a complete successful ingestion.
        (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        db.close()
        return manifest

    for name, bbox in samples.items():
        win = {"bbox_wgs84": list(bbox), "status": "FAILED",
               "id_count": None, "server_count": None,
               "accepted_count": 0, "rejected_count": 0, "duplicated_ids": 0,
               "retrieved_ids": 0, "source_citations": {}, "chunks": []}
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
            for k in range(0, len(ids), batch_size):
                subset = ids[k:k + batch_size]
                qparams = {
                    "f": "json", "where": "1=1",
                    "objectIds": ",".join(str(i) for i in subset),
                    "outFields": "*", "returnGeometry": "true", "outSR": 4326,
                }
                payload, chunk_receipt = capture(fetch, qparams,
                    rawdir / (name + ".batch_" + str(k // batch_size).zfill(4) + ".json"))
                chunk_receipt["requested_objectids"] = subset
                chunk_receipt["response_feature_count"] = len(payload.get("features", []))
                chunk_receipt["exceeded_transfer_limit"] = bool(payload.get("exceededTransferLimit"))
                win["chunks"].append(chunk_receipt)
                if payload.get("exceededTransferLimit"):
                    raise ValueError("Official batch transfer limit; reduce batch_size")
                if payload.get("geometryType") not in ("esriGeometryPolygon", None):
                    raise ValueError("Unexpected geometry type")
                spatial_ref = payload.get("spatialReference", {})
                if spatial_ref and spatial_ref.get("wkid") not in (4326, 4269):
                    raise ValueError("Official query did not return expected WGS84 CRS")
                feats = payload.get("features")
                if not isinstance(feats, list):
                    raise ValueError("Official batch missing feature list")
                actual = {f.get("attributes", {}).get("OBJECTID") for f in feats}
                if actual != set(subset):
                    raise ValueError("Missing/extra OBJECTIDs in batch: expected " +
                                     repr(subset) + " got " + repr(sorted(actual)))
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
                            "INSERT INTO fema_source_features VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            (key, oid, attrs.get("DFIRM_ID"), attrs.get("FLD_AR_ID"),
                             attrs.get("FLD_ZONE"), attrs.get("ZONE_SUBTY"),
                             attrs.get("SFHA_TF"), attrs.get("SOURCE_CIT"),
                             attrs.get("VERSION_ID"), packed,
                             datetime.now(timezone.utc).isoformat()))
                        db.execute("INSERT INTO fema_source_bounds VALUES(?,?,?,?,?)",
                                   (cur.lastrowid, bounds[0], bounds[2], bounds[1], bounds[3]))
                    db.execute("INSERT OR IGNORE INTO fema_window_membership VALUES(?,?)", (name, key))
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
        except (RuntimeError, ValueError, KeyError, sqlite3.Error, TypeError) as exc:
            win["status"] = "INCOMPLETE"
            win["error"] = str(exc)[:800]
            win["retrieved_ids"] = db.execute(
                "SELECT COUNT(*) FROM fema_window_membership WHERE window=?", (name,)
            ).fetchone()[0]
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
    manifest["all_requested_windows_complete"] = (
        manifest["successful_windows"] == manifest["requested_windows"]
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
