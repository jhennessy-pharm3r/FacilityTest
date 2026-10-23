"""Coordinator-only merge resolution for already merged main Lane A/B endpoints.

Invoked after a GitHub Actions temporary merge of current main into the
stacked Lane D integration branch. Retains every lane A/B route and config
verbatim and inserts only Lane D private source integration.
Never touches importer code or commits to main.
"""
from __future__ import annotations

from pathlib import Path


def insert_once(path, old, new, label):
    text=path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError("Unexpected latest-main API contract: "+label)
    path.write_text(text.replace(old,new,1),encoding="utf-8")


def reconcile():
    app=Path("facilityrisk/app.py")
    src=app.read_text(encoding="utf-8")
    if "from .lane_a_service import" not in src or "from scripts.lane_b_epa.integration_api import" not in src:
        raise RuntimeError("Main-side Lane A and B API features absent; refusing unsafe overwrite")

    import_target="from .incident_news import nearby_reviewed_site as nearby_incidentnews_site"
    import_replace=import_target+"\nfrom .lane_d.private_api import router as lane_d_private_router, installed_status as lane_d_installed_status"
    insert_once(app,import_target,import_replace,"lane_d import")

    app_router="app.include_router(lane_b_router())"
    insert_once(app,app_router,app_router+"\napp.include_router(lane_d_private_router)","lane_d router")

    base_status="return {**source_index_status(), 'lane_b_epa': lane_b_status()}"
    new_status="return {**source_index_status(), 'lane_b_epa': lane_b_status(), 'lane_d': lane_d_installed_status()}"
    insert_once(app,base_status,new_status,"combined private Source Health")

    compose=Path("compose.yaml")
    text=compose.read_text(encoding="utf-8")
    if "FACILITY_RISK_LANE_A_INDEX_ROOT:" not in text or "FACILITY_RISK_LANE_B_ROUTES_ENABLED:" not in text:
        raise RuntimeError("Upstream main Lane A/B Compose contract absent")
    line="      FACILITY_RISK_LANE_B_RMP_DIRECTORY: $"+"{FACILITY_RISK_LANE_B_RMP_DIRECTORY:-}"
    addition=(line+"\n      FACILITY_RISK_LANE_D_INDEX_ROOT: $"+"{FACILITY_RISK_LANE_D_INDEX_ROOT:-}"
              +"\n      FACILITY_RISK_LANE_D_ODIN_USE_APPROVED: $"+"{FACILITY_RISK_LANE_D_ODIN_USE_APPROVED:-0}")
    insert_once(compose,line,addition,"Lane D mount and rights environment")
    bind_old="      - ./source-index:/app/source-index:ro"
    bind_new="      - $"+"{FACILITY_RISK_SOURCE_INDEX_HOST:-./source-index}:/app/source-index:ro"
    insert_once(compose,bind_old,bind_new,"persistent host source-only mount")

    env=Path(".env.example")
    text=env.read_text(encoding="utf-8")
    if "FACILITY_RISK_LANE_B_ROUTES_ENABLED" not in text or "FACILITY_RISK_LANE_A_INDEX_ROOT" not in text:
        raise RuntimeError("Upstream source environment features missing")
    if "FACILITY_RISK_LANE_D_INDEX_ROOT" not in text:
        env.write_text(text.rstrip()+"\n\n"+(
            "# Lane D: only after official source SHA-pinned installation on a protected host.\n"
            "# FACILITY_RISK_LANE_D_INDEX_ROOT=/app/source-index/lane-d\n"
            "# Optional private host-side source volume (persistent, backed up).\n"
            "# FACILITY_RISK_SOURCE_INDEX_HOST=/srv/facilityrisk/source-index\n"
            "# ORNL public snapshots remain unserved pending applicable commercial data-use rights.\n"
            "# FACILITY_RISK_LANE_D_ODIN_USE_APPROVED=0\n"
        ),encoding="utf-8")
    updated=app.read_text(encoding="utf-8")
    assert updated.count("app.include_router(lane_d_private_router)")==1
    assert updated.count("'lane_b_epa': lane_b_status()")==1
    assert updated.count("'lane_d': lane_d_installed_status()")==1
    assert "app.include_router(lane_b_router())" in updated
    assert "from .lane_a_service import" in updated
    for file in (app,compose,env):
        text=file.read_text(encoding="utf-8")
        if any(sep in text for sep in ("<<<<<<< ","=======\n",">>>>>>> ")):
            raise RuntimeError("Merge conflict marker remained in "+str(file))
    print("Merged latest main Lane A/B features retained; Lane D private router, source health and mounted read-only indexes added")


if __name__ == "__main__":
    reconcile()
