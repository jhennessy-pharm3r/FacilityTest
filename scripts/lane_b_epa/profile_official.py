"""Audit full official EPA ECHO/RCRA/TRI source archives without site attribution.

Streams each official member, counts native identities, missing coordinates,
published time-fields and jurisdiction distribution.  Aggregate output only.
"""
import argparse
import collections
import csv
import datetime as dt
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import sys
import urllib.request
import zipfile
from .ingest import URLS, KEYS, name, coordinate

TRI_URL="https://data.epa.gov/efservice/downloads/tri/mv_tri_basic_download/{year}_US/csv"
STATE_KEYS={"echo":("FAC_STATE","FAC_STATE_CODE","FAC_STATE_NAME","STATE_CODE"),
            "rcra":("STATE_CODE",),
            "tri":("8_ST","ST","STATE_CODE")}
COORD_KEYS={"echo":(("FAC_LAT","LATITUDE","FAC_LATITUDE"),("FAC_LONG","LONGITUDE","FAC_LONGITUDE")),
            "rcra":(("LATITUDE83","LATITUDE"),("LONGITUDE83","LONGITUDE")),
            "tri":(("12_LATITUDE","LATITUDE"),("13_LONGITUDE","LONGITUDE"))}
ALT_IDS=("PGM_SYS_ID","FAC_PGM_SYS_ID","NPDES_ID","NPDES_IDS","RCRA_ID","RCRA_IDS",
         "AIR_IDS","SDWA_IDS","TRI_IDS","GHG_IDS","FAC_NAME","FACILITY_NAME","DFR_URL")
ENUM_FIELDS={"echo":("FAC_ACTIVE_FLAG","FAC_COMPLIANCE_STATUS","FAC_SNC_FLG","RCRA_FLAG","AIR_FLAG","NPDES_FLAG","TRI_FLAG"),
             "rcra":("ENFORCEMENT_TYPE","EVALUATION_TYPE","FOUND_VIOLATION","VIO_FLAG","SNC_FLAG","ACTIVE_SITE","FED_WASTE_GENERATOR"),
             "tri":("49_FORM_TYPE","50_UNIT_OF_MEASURE","48_PFAS","43_CLASSIFICATION")}
DATE_EXACT={"ENFORCEMENT_ACTION_DATE","EVALUATION_START_DATE","DATE_VIOLATION_DETERMINED",
           "ACTUAL_RTC_DATE","SCHEDULED_COMPLIANCE_DATE","YRMONTH","1_YEAR","CREATE_DATE",
           "UPDATE_DATE","LAST_REPORTED_DATE"}
def year_of(value):
    v=(value or "").strip()
    if not v:return None
    try:
        if len(v)==10 and v[2]=="/" and v[5]=="/":
            return dt.datetime.strptime(v,"%m/%d/%Y").year
        if len(v)==10 and v[4]=="-" and v[7]=="-":
            return dt.date.fromisoformat(v).year
        if len(v)==8 and v.isdigit():
            return dt.datetime.strptime(v,"%Y%m%d").year
        if len(v)==6 and v.isdigit() and 1<=int(v[4:])<=12:
            return int(v[:4])
        if len(v)==4 and v.isdigit():
            return int(v)
    except (ValueError,OverflowError):
        pass
    return None
def hashfile(path):
    digest=hashlib.sha256()
    with open(path,"rb") as f:
        for piece in iter(lambda:f.read(1048576),b""):digest.update(piece)
    return digest.hexdigest()
def survey(source,source_file,publisher_url,year=None,last_modified=None):
    csv.field_size_limit(20_000_000)
    iszip=zipfile.is_zipfile(source_file)
    archive=zipfile.ZipFile(source_file) if iszip else None
    members=([m for m in archive.infolist() if not m.is_dir() and m.filename.lower().endswith((".csv",".txt"))]
             if archive else [None])
    if source=="rcra":members.sort(key=lambda m: (not m.filename.upper().endswith("RCRA_FACILITIES.CSV"),m.filename))
    audit={"source":source,"source_url":publisher_url,"source_year":year,"publisher_last_modified":last_modified,
           "retrieved_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"archive_sha256":hashfile(source_file),
           "archive_bytes":Path(source_file).stat().st_size,"members":{}}
    try:
        facility_keys=set()
        for m in members:
            filename=m.filename if m else Path(source_file).name
            stream=archive.open(m) if m else open(source_file,"rb")
            with stream:
                reader=csv.DictReader(io.TextIOWrapper(stream,encoding="utf-8-sig",errors="replace",newline=""))
                keys=[name(k) for k in (reader.fieldnames or [])]
                if len(set(keys))!=len(keys):raise ValueError("Duplicate/colliding header in "+filename)
                ident=next((k for k in KEYS[source] if k in keys),None)
                skey=next((k for k in STATE_KEYS[source] if k in keys),None)
                lk=next((k for k in COORD_KEYS[source][0] if k in keys),None)
                ok=next((k for k in COORD_KEYS[source][1] if k in keys),None)
                relevant=[k for k in keys if k in DATE_EXACT or (source=="echo" and "DATE" in k) or (k.endswith("_DATE") and source=="rcra")]
                enum_keys=[k for k in ENUM_FIELDS[source] if k in keys]
                rows=missing_id=malformed=valid_coords=zero_coords=invalid_coords=0
                observed=set();duplicate_id=0;coord_bounds=[90,-90,180,-180]
                missing_key_geocoded=0;unmatched_facility_join=0
                states=collections.Counter();alts=collections.Counter();dates={k:collections.Counter() for k in relevant}
                enum_values={k:collections.Counter() for k in enum_keys}
                for raw in reader:
                    rows+=1
                    obj={name(k):(v or "").strip() for k,v in raw.items() if k is not None}
                    if None in raw:malformed+=1
                    sid=obj.get(ident,"") if ident else ""
                    if not sid:
                        missing_id+=1
                        for k in ALT_IDS:
                            if obj.get(k):alts[k]+=1
                    elif (sid,obj.get("ACTIVITY_LOCATION","") if source=="rcra" else "") in observed:duplicate_id+=1
                    else:observed.add((sid,obj.get("ACTIVITY_LOCATION","") if source=="rcra" else ""))
                    if source=="rcra" and sid:
                        key=(sid,obj.get("ACTIVITY_LOCATION",""))
                        if filename.upper().endswith("RCRA_FACILITIES.CSV"):
                            facility_keys.add(key)
                        elif key not in facility_keys:
                            unmatched_facility_join+=1
                    if skey:states[obj.get(skey,"") or "<empty>"]+=1
                    if lk and ok:
                        lat=coordinate(obj.get(lk),-90,90)
                        lon=coordinate(obj.get(ok),-180,180)
                        if lat is not None and lon is not None:
                            if not sid:missing_key_geocoded+=1
                            valid_coords+=1
                            coord_bounds[0]=min(coord_bounds[0],lat)
                            coord_bounds[1]=max(coord_bounds[1],lat)
                            coord_bounds[2]=min(coord_bounds[2],lon)
                            coord_bounds[3]=max(coord_bounds[3],lon)
                            if lat==0 and lon==0:zero_coords+=1
                        elif obj.get(lk) or obj.get(ok):invalid_coords+=1
                    for k in enum_keys:
                        enum_values[k][obj.get(k,"") or "<empty>"]+=1
                    for k in relevant:
                        val=obj.get(k,"")
                        if val:
                            y=year_of(val)
                            dates[k][str(y) if y is not None else "invalid_format"]+=1
                audit["members"][filename]={
                    "headers":keys,"rows":rows,"native_key":ident,
                    "distinct_native_ids":len(observed),"duplicate_native_id_rows":duplicate_id,
                    "rows_without_native_id_but_with_valid_coordinates":missing_key_geocoded,
                    "nonfacility_rows_unmatched_by_two_native_join_keys":unmatched_facility_join if source=="rcra" and not filename.upper().endswith("RCRA_FACILITIES.CSV") else None,
                    "missing_native_id":missing_id,"malformed_overwide_rows":malformed,
                    "alternate_fields_on_missing_native_id":dict(alts),
                    "coordinate_columns":[lk,ok],"valid_coordinate_pairs":valid_coords,
                    "invalid_or_partial_coordinate_values":invalid_coords,
                    "zero_zero_coordinate_pairs":zero_coords,
                    "coordinate_bounds_minlat_maxlat_minlon_maxlon":coord_bounds if valid_coords else None,
                    "state_field":skey,"jurisdiction_counts":dict(states.most_common()),
                    "date_year_counts":{k:dict(v) for k,v in dates.items()},
                    "reported_field_value_counts":{k:dict(v) for k,v in enum_values.items()},
                }
        audit["total_member_rows"]=sum(v["rows"] for v in audit["members"].values())
        audit["missing_native_id_rows"]=sum(v["missing_native_id"] for v in audit["members"].values())
        return audit
    finally:
        if archive:archive.close()
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",choices=["echo","rcra","tri"],required=True)
    p.add_argument("--year",type=int)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if a.source=="tri" and a.year is None:p.error("--year required for TRI")
    url=TRI_URL.format(year=a.year) if a.source=="tri" else URLS[a.source]
    a.output.mkdir(parents=True,exist_ok=True)
    raw=a.output/("source.zip" if a.source!="tri" else "source.csv")
    if raw.exists():p.error("Existing raw source; use a new output directory")
    req=urllib.request.Request(url,headers={"User-Agent":"FacilityTest-EPA-SourceAudit/1.0"})
    with urllib.request.urlopen(req,timeout=180) as response,raw.open("wb") as f:
        last=response.headers.get("Last-Modified")
        shutil.copyfileobj(response,f)
    result=survey(a.source,raw,url,a.year,last)
    (a.output/"audit.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("SOURCE",a.source,"ROWS",result["total_member_rows"],"MISSING_KEYS",result["missing_native_id_rows"])
    for member,data in result["members"].items():
        print("MEMBER",member,"ROWS",data["rows"],"DISTINCT",data["distinct_native_ids"],
              "MISSING",data["missing_native_id"],"COORDS",data["valid_coordinate_pairs"],
              "DATES",json.dumps({k:list(v.items())[:8] for k,v in data["date_year_counts"].items()}))
        print("HEADERS",json.dumps(data["headers"]))
        print("JURISDICTIONS",json.dumps(data["jurisdiction_counts"]))
        print("MISSING_KEY_ALTERNATIVES",json.dumps(data["alternate_fields_on_missing_native_id"]))
        print("ENUM_FIELDS",json.dumps(data["reported_field_value_counts"]))
        print("UNMATCHED_RCRA_HANDLER_RELATIONS",data["nonfacility_rows_unmatched_by_two_native_join_keys"])
    print("ARCHIVE_SHA256",result["archive_sha256"])
if __name__=="__main__":main()
