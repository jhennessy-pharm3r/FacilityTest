"""EPA Lane B source-preserving importer. Python 3 standard library."""
import argparse,csv,datetime,hashlib,io,json,re,sqlite3,tempfile,urllib.request,zipfile
from pathlib import Path
URLS={"echo":"https://echo.epa.gov/files/echodownloads/echo_exporter.zip","rcra":"https://echo.epa.gov/files/echodownloads/rcra_downloads.zip"}
KEYS={"echo":("REGISTRY_ID","FRS_ID","FACILITY_ID"),"rcra":("HANDLER_ID","RCRA_ID","EPA_ID","RCRA_HANDLER_ID","PGM_SYS_ID","FACILITY_ID","RCRA_FACILITY_ID","EPA_ID_NUMBER","ID_NUMBER"),"tri":("2_TRIFD","TRIFD","TRI_FACILITY_ID","FACILITY_ID")}
def name(s): return re.sub("[^A-Z0-9]+","_",s.upper().strip()).strip("_")
def coordinate(s,low,high):
    try:
        x=float(s)
        return x if low<=x<=high else None
    except (ValueError,TypeError): return None
def ingest(source,path,out,source_url=None,year=None):
    if source not in KEYS: raise ValueError("RMP is access-restricted; no bulk importer")
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    target=out/(source+".sqlite")
    if target.exists():raise FileExistsError(target)
    digest=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1048576),b""):digest.update(block)
    archive=zipfile.ZipFile(path) if zipfile.is_zipfile(path) else None
    members=[x for x in archive.infolist() if not x.is_dir() and x.filename.lower().endswith((".csv",".txt"))] if archive else [None]
    db=sqlite3.connect(target)
    db.execute("CREATE TABLE observation(source TEXT,source_id TEXT,member TEXT,row_number INTEGER,payload TEXT,row_sha256 TEXT,latitude REAL,longitude REAL,activity_location TEXT,PRIMARY KEY(source,member,row_number))")
    db.execute("CREATE INDEX idx_sourceid ON observation(source,source_id,activity_location)")
    db.execute("CREATE TABLE rejected(member TEXT,row_number INTEGER,reason TEXT,row_sha256 TEXT,payload_json TEXT)")
    scanned=accepted=rejected=coords=duplicates=0;seen=set();inventory={};reject_reasons={}
    try:
        for item in members:
            member=item.filename if item else Path(path).name
            stream=archive.open(item) if item else open(path,"rb")
            with stream:
                reader=csv.DictReader(io.TextIOWrapper(stream,encoding="utf-8-sig",errors="replace",newline=""))
                keys=[name(x) for x in (reader.fieldnames or [])]
                if len(keys)!=len(set(keys)):raise ValueError("duplicate CSV fields "+member)
                identity=next((k for k in KEYS[source] if k in keys),None)
                if not identity:
                    inventory[member]={"state":"skipped_no_identity_column","observed_headers":keys[:70]}
                    continue
                lat=next((k for k in ("LATITUDE","FAC_LATITUDE","LATITUDE83","12_LATITUDE","FAC_LAT") if k in keys),None)
                lon=next((k for k in ("LONGITUDE","FAC_LONGITUDE","LONGITUDE83","13_LONGITUDE","FAC_LONG") if k in keys),None)
                rows=0
                for n,row in enumerate(reader,2):
                    scanned+=1;rows+=1
                    obj={name(k):(v or "").strip() for k,v in row.items() if k is not None}
                    sid=obj.get(identity,"")
                    if not sid or None in row:
                        rejected+=1
                        reason="malformed_csv" if None in row else "missing_native_id"
                        reject_reasons[reason]=reject_reasons.get(reason,0)+1
                        quarantined=json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(",",":"))
                        db.execute("INSERT INTO rejected VALUES (?,?,?,?,?)",(member,n,reason,hashlib.sha256(quarantined.encode()).hexdigest(),quarantined))
                        continue
                    if (member,sid) in seen:duplicates+=1
                    seen.add((member,sid))
                    a=coordinate(obj.get(lat),-90,90) if lat else None
                    b=coordinate(obj.get(lon),-180,180) if lon else None
                    if a is not None and b is not None:coords+=1
                    raw=json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(",",":"))
                    db.execute("INSERT INTO observation VALUES (?,?,?,?,?,?,?,?,?)",(source,sid,member,n,raw,hashlib.sha256(raw.encode()).hexdigest(),a,b,obj.get("ACTIVITY_LOCATION","")) )
                    accepted+=1
                    if scanned%10000==0:db.commit()
                inventory[member]={"state":"normalized","scanned":rows,"identity_column":identity,
                                  "header_columns":keys,"activity_location_in_header":"ACTIVITY_LOCATION" in keys}
        db.commit()
        if not accepted:raise ValueError("No source records had accepted native keys; inspect archive and official headers")
        indexed=db.execute("SELECT COUNT(*) FROM observation").fetchone()[0]
        check=db.execute("PRAGMA integrity_check").fetchone()[0]
        if indexed!=accepted or scanned!=accepted+rejected or check!="ok":raise AssertionError("reconciliation failed")
        result=dict(source=source,schema_version=2,raw_rejected_payloads_preserved=True,rcra_join_rule="ID_NUMBER + ACTIVITY_LOCATION (do not join by name or ID_NUMBER alone)" if source=="rcra" else None,state="INDEXED",deployment_state="NOT_DEPLOYED",retrieved_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_url=source_url,year=year,archive_sha256=digest.hexdigest(),scanned_rows=scanned,accepted_rows=accepted,rejected_rows=rejected,reject_reason_counts=reject_reasons,indexed_rows=indexed,valid_coordinate_pairs=coords,duplicate_member_ids=duplicates,archive_members=inventory,integrity=check,source_identity_only=True)
        (out/(source+".manifest.json")).write_text(json.dumps(result,indent=2)+"\n")
        return result
    except Exception:
        db.close();target.unlink(missing_ok=True);raise
    finally:
        db.close()
        if archive:archive.close()
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",choices=["echo","rcra","tri","rmp"],required=True)
    p.add_argument("--input",type=Path)
    p.add_argument("--url")
    p.add_argument("--year",type=int)
    p.add_argument("--output",required=True)
    p.add_argument("--raw-dir",type=Path,help="Private durable directory to retain original EPA archive downloaded via URL")
    a=p.parse_args()
    if a.source=="rmp":p.error("RMP non-OCA authorization must be reviewed; unrestricted bulk is disabled")
    if a.source=="tri" and not a.year:p.error("TRI requires a report year")
    url=a.url or URLS.get(a.source)
    if not a.input and not url:p.error("supply official --input or --url")
    with tempfile.TemporaryDirectory() as tmp:
        raw=a.input
        if raw is None:
            if a.raw_dir:
                a.raw_dir.mkdir(parents=True,exist_ok=True)
                raw=a.raw_dir/(a.source+"_"+datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")+".zip")
                if raw.exists():raise FileExistsError("Original archive already exists: "+str(raw))
            else:
                raw=Path(tmp)/"official_archive"
            with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"FacilityRisk-LaneB/1.0"}),timeout=120) as response,raw.open("wb") as f:
                import shutil;shutil.copyfileobj(response,f)
        print(json.dumps(ingest(a.source,raw,a.output,url,a.year),indent=2))
if __name__=="__main__":main()
