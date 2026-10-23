"""Read-only Lane A coordinator interface to an installed, validated source release.

The coordinator supplies its own authenticated/tenant-safe API; this module
reads publisher-native identities only. It never geocodes/matches a facility
or infers loss from missing FEMA/WHP source observations.
"""
import json
import pathlib
import re
import sqlite3

from facilityrisk.lane_a_source_query import source_whp_record, source_fema_polygon
from facilityrisk.lane_a_geospatial import query_fema_point

INSTALL_SCHEMA = "facility_risk_lane_a_read_only_release_v1"
INDEX_PATHS = {
    "fema_nfhl": "paged_windows/fema-window-index.sqlite",
    "usda_summary": "whp_official_index/whp2023-source-geographies.sqlite",
    "usda_continuous": "whp_regions/whp-regional-source-only.sqlite",
    "usda_classified": "whp_classified/whp-classified-source-only.sqlite",
}


def installed_release(destination):
    """Return trusted release files, scoped to a validated non-escaping pointer."""
    root = pathlib.Path(destination).resolve()
    pointer_path = root / "current.json"
    if not pointer_path.is_file() or pointer_path.is_symlink():
        raise FileNotFoundError("No activated Lane A source-only release")
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    if pointer.get("schema_version") != INSTALL_SCHEMA:
        raise ValueError("Unexpected Lane A release pointer schema")
    release_id = pointer.get("release_id")
    if not isinstance(release_id, str) or re.fullmatch(r"[0-9a-f]{24}", release_id) is None:
        raise ValueError("Invalid Lane A release identifier")
    expected = "releases/" + release_id + "/data/lane_a"
    if pointer.get("relative_root") != expected:
        raise ValueError("Lane A pointer references a non-canonical release path")
    source_root = root / expected
    if not source_root.is_dir() or not source_root.resolve().is_relative_to(root):
        raise ValueError("Activated Lane A source-only release not on authorized root")
    return source_root, pointer


def index_file(destination, source):
    """Get a physically existing immutable source-only SQLite path."""
    if source not in INDEX_PATHS:
        raise ValueError("Unsupported source-grain query")
    root, pointer = installed_release(destination)
    path = root / INDEX_PATHS[source]
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError("This original source index is not installed")
    if source not in pointer.get("verified_source_only_rows", {}):
        raise ValueError("Source was not verified before pointer activation")
    return path


def query_publisher_id(destination, source, *, original_id, geography_type=None):
    if source == "usda_summary":
        return source_whp_record(index_file(destination, source),
                                 geography_type, original_id)
    if source == "fema_nfhl":
        return source_fema_polygon(index_file(destination, source), original_id)
    raise ValueError("These source products do not publish site-level native IDs")


def query_raster_probe(destination, source, *, region, grid_index):
    """Fetch a *sampled* original 2023 QA raster observation, NOT a facility pixel."""
    if source not in ("usda_continuous", "usda_classified"):
        raise ValueError("Only original USDA WHP 2023 geographic QA probes supported")
    if (not isinstance(region, str) or
            not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", region) or
            not isinstance(grid_index, int) or isinstance(grid_index, bool) or
            not (0 <= grid_index <= 4)):
        raise ValueError("Invalid USDA geographic QA region/grid identity")
    dbpath = index_file(destination, source)
    table = ("whp_geographic_probes" if source == "usda_continuous"
             else "usfs_whp_classified_probes")
    cols = ("whp_release AS raster_release,pixel_state,pixel_value"
            if source == "usda_continuous" else
            "raster_release,class_state,class_value,class_label")
    with sqlite3.connect("file:" + str(dbpath.resolve()) + "?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        row = db.execute(
            "SELECT region,probe_index,longitude,latitude,"
            "source_url,raw_sha256," + cols + " FROM " + table +
            " WHERE region=? AND probe_index=?", (region, grid_index)
        ).fetchone()
    if row is None:
        return {
            "source": source, "state": "NOT_IN_BOUNDED_QA_SAMPLING_INDEX",
            "region": region, "grid_index": grid_index,
            "hazard_coverage": "UNKNOWN", "insured_site_assessment": False,
        }
    result = dict(row)
    result.update({
        "source": source,
        "status": "ORIGINAL_QA_RASTER_SAMPLE_NOT_FACILITY",
        "source_native_pixel_id": None,
        "hazard_score_calibrated_to_property_losses": False,
        "physical_site_verified": False,
        "live_app_deployed": False,
    })
    return result


def query_reviewed_coordinate(destination, *, longitude, latitude,
                              site_reference, coordinate_evidence,
                              coordinates_corroborated):
    """Source geometry only, not a risk determination or an automatic site match."""
    root, _ = installed_release(destination)
    return query_fema_point(
        index_file(destination, "fema_nfhl"),
        root / "paged_windows/manifest.json",
        longitude=longitude, latitude=latitude,
        site_reference=site_reference,
        coordinate_evidence=coordinate_evidence,
        coordinates_corroborated=coordinates_corroborated,
    )
