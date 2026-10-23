"""Public EPA FRS RMP-interest GeoPlatform import ONLY: no restricted RMP plans/OCA."""
import argparse,datetime,hashlib,json,sqlite3,time,urllib.parse,urllib.request
from collections import Counter
from pathlib import Path
URL="https://services.arcgis.com/cJ9YHowT8TU7DUyn/arcgis/rest/services/FRS_INTERESTS_RMP/FeatureServer/0/query"
def request(params,retries=3):
    body=urllib.parse.urlencode({"f":"json",**params}).encode()
    for attempt in range(retries):
        try:
            req=urllib.request.Request(URL,data=body,headers={"User-Agent":"FacilityRisk-LaneB/1.0","Content-Type":"application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req,timeout=75) as r:data=json.load(r)
            if "error" in data:raise RuntimeError("EPA feature service error: "+str(data["error"]))
            return data
        except (OSError,TimeoutError) as e:
            if attempt==retries-1:raise
            time.sleep(2**attempt)
def coord(value,low,high):
    try:
        x=float(value)
        return x if low<=x<=high else None
    except (TypeError,ValueError):return None
def import_public(output,fetch=request,page_size=100):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    dbpath=output/"rmp_frs_public.sqlite"
    raw=output/"rmp_frs_public.raw.jsonl"
    if dbpath.exists() or raw.exists():raise FileExistsError("New output directory required; preserving existing source evidence")
    count=fetch({"where":"1=1","returnCountOnly":"true"}).get("count")
    ids=fetch({"where":"1=1","returnIdsOnly":"true"}).get("objectIds")
    if not isinstance(count,int) or not isinstance(ids,list) or count!=len(ids):
        raise AssertionError("EPA count/ID response mismatch")
    if len(ids)!=len(set(ids)):raise AssertionError("Duplicated EPA OBJECTIDs")
    ids=sorted(ids)
    db=sqlite3.connect(dbpath)
    db.execute("CREATE TABLE rmp_frs_public(object_id INTEGER PRIMARY KEY,registry_id TEXT,program_id TEXT,raw_sha256 TEXT,latitude REAL,longitude REAL,attributes_json TEXT NOT NULL)")
    db.execute("CREATE INDEX rmp_registry ON rmp_frs_public(registry_id)")
    db.execute("CREATE INDEX rmp_program ON rmp_frs_public(program_id)")
    observed=set();registry_ids=set();program_ids=set();states=Counter();active=Counter();missing_registry=missing_program=valid_coords=zero_coord=0
    bounds=[90,-90,180,-180]
    sha=hashlib.sha256()
    try:
        with raw.open("wb") as out:
            for start in range(0,len(ids),page_size):
                group=ids[start:start+page_size]
                data=fetch({"objectIds":",".join(str(x) for x in group),"outFields":"*","returnGeometry":"true"})
                records=data.get("features")
                if not isinstance(records,list):raise AssertionError("Absent feature array in EPA response")
                for rec in sorted(records,key=lambda item:int((item.get("attributes") or {}).get("OBJECTID") or -1)):
                    a=rec.get("attributes") or {}
                    key=a.get("OBJECTID")
                    if not isinstance(key,int) or key not in group or key in observed:raise AssertionError("Unrequested/duplicate EPA object ID")
                    observed.add(key)
                    registry=str(a.get("REGISTRY_ID") or "").strip()
                    program=str(a.get("PGM_SYS_ID") or "").strip()
                    if not registry:missing_registry+=1
                    else:registry_ids.add(registry)
                    if not program:missing_program+=1
                    else:program_ids.add(program)
                    states[str(a.get("STATE_CODE") or "<empty>").strip()]+=1
                    active[str(a.get("ACTIVE_STATUS") or "<empty>").strip()]+=1
                    lat=coord(a.get("LATITUDE83"),-90,90)
                    lon=coord(a.get("LONGITUDE83"),-180,180)
                    if lat is not None and lon is not None:
                        valid_coords+=1
                        bounds=[min(bounds[0],lat),max(bounds[1],lat),min(bounds[2],lon),max(bounds[3],lon)]
                        if lat==0 and lon==0:zero_coord+=1
                    canonical=json.dumps(rec,sort_keys=True,separators=(",",":"),ensure_ascii=False)
                    line=(canonical+"\n").encode("utf-8")
                    sha.update(line);out.write(line)
                    db.execute("INSERT INTO rmp_frs_public VALUES (?,?,?,?,?,?,?)",(key,registry,program,hashlib.sha256(canonical.encode("utf-8")).hexdigest(),lat,lon,json.dumps(a,sort_keys=True,separators=(",",":"))))
                db.commit()
        if observed!=set(ids):raise AssertionError("EPA returned IDs incomplete")
        indexed=db.execute("SELECT COUNT(*) FROM rmp_frs_public").fetchone()[0]
        integrity=db.execute("PRAGMA integrity_check").fetchone()[0]
        if indexed!=count or integrity!="ok":raise AssertionError("EPA record/SQLite mismatch")
        dbsize=dbpath.stat().st_size
        dbdigest=hashlib.sha256()
        with dbpath.open("rb") as dbfile:
            for block in iter(lambda:dbfile.read(1048576),b""):dbdigest.update(block)
        manifest=dict(schema_version=2,index_sha256=dbdigest.hexdigest(),index_bytes=dbsize,distinct_program_ids=len(program_ids),distinct_registry_ids=len(registry_ids),state_counts=dict(states),active_status_counts=dict(active),zero_zero_coordinate_pairs=zero_coord,coordinate_bounds_minlat_maxlat_minlon_maxlon=bounds if valid_coords else None,source="EPA FRS RMP program interest",scope="Public EPA FRS RMP-linked facility identity records only; NO RMP plans, release quantities, accident outcomes or OCA",state="INDEXED",deployment_state="NOT_DEPLOYED",source_url=URL,utc_retrieved=datetime.datetime.now(datetime.timezone.utc).isoformat(),reported_feature_count=count,indexed_rows=indexed,object_id_coverage=len(observed),missing_registry_id=missing_registry,missing_program_id=missing_program,valid_coordinate_pairs=valid_coords,missing_coordinate_pairs=indexed-valid_coords,raw_jsonl_sha256=sha.hexdigest(),sqlite_integrity=integrity,site_match_status="NOT_REVIEWED")
        (output/"rmp_frs_public.manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
        return manifest
    except Exception:
        db.close();dbpath.unlink(missing_ok=True);raw.unlink(missing_ok=True);raise
    finally:db.close()
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True,help="Secure private staging directory (holds full public FRS records)")
    a=p.parse_args()
    print(json.dumps(import_public(a.output),indent=2))
if __name__=="__main__":main()
