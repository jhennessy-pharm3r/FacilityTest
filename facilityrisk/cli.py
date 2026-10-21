"""Command-line ingestion and local service entry point."""
from __future__ import annotations
import argparse
import json
import sys
from .db import connect,initialize,quality_report
from .ingest import ingest_workbook
from .browser_export import export_browser_snapshot
from .connectors import fetch_usgs,fetch_aqueduct,fetch_echo,ingest_noaa_csv
from .advanced_sources import discover_frs, fetch_verified_echo, fetch_fema, ingest_fda_inspections_csv, source_probe
from .intelligence import decide_candidate,review_location,intelligence_quality,verify_fei
from .case_studies import seed_cases
from .source_extensions import probe_extensions, import_geo_csv
from .security import validate_private_bind


def main(argv=None) -> int:
    p=argparse.ArgumentParser(prog='facilityrisk',description='Facility risk evidence app; local development only')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('init-db')
    ing=sub.add_parser('ingest-workbook');ing.add_argument('xlsx')
    sub.add_parser('qa')
    exp=sub.add_parser('export-browser',help='Create PRIVATE JSON snapshot to load in GitHub Pages; never commit the JSON')
    exp.add_argument('output_json')
    srv=sub.add_parser('serve');srv.add_argument('--port',type=int,default=8765);srv.add_argument('--host',default='127.0.0.1')
    usgs=sub.add_parser('refresh-usgs');usgs.add_argument('--facility',required=True)
    usgs.add_argument('--start',required=True);usgs.add_argument('--end',required=True)
    usgs.add_argument('--radius-km',type=float,default=150)
    usgs.add_argument('--min-magnitude',type=float,default=4)
    wri=sub.add_parser('refresh-aqueduct');wri.add_argument('--facility',required=True)
    echo=sub.add_parser('refresh-echo');echo.add_argument('--facility',required=True)
    echo.add_argument('--registry-id',required=True,help='Operator-verified EPA FRS ID (not FDA FEI)')
    noaa=sub.add_parser('ingest-noaa-csv');noaa.add_argument('csv_gz')
    noaa.add_argument('--radius-km',type=float,default=40)
    frs=sub.add_parser('discover-frs');frs.add_argument('--facility',required=True);frs.add_argument('--name',required=True);frs.add_argument('--state',required=True)
    rv=sub.add_parser('review-frs');rv.add_argument('--candidate',required=True);rv.add_argument('--decision',choices=['accepted','rejected'],required=True);rv.add_argument('--reviewer',required=True);rv.add_argument('--source',required=True);rv.add_argument('--note',required=True)
    vf=sub.add_parser('review-fei');vf.add_argument('--facility',required=True);vf.add_argument('--reviewer',required=True);vf.add_argument('--source',required=True);vf.add_argument('--note',required=True)
    loc=sub.add_parser('review-location');loc.add_argument('--facility',required=True);loc.add_argument('--precision',required=True,choices=['city','approximate','site_verified','property_polygon']);loc.add_argument('--reviewer',required=True);loc.add_argument('--source',required=True);loc.add_argument('--note',default='')
    fema=sub.add_parser('refresh-fema');fema.add_argument('--facility',required=True)
    ec=sub.add_parser('refresh-verified-echo');ec.add_argument('--facility',required=True)
    fda=sub.add_parser('ingest-fda-inspections-csv');fda.add_argument('csv_path')
    sub.add_parser('seed-cases');sub.add_parser('probe-sources')
    sub.add_parser('probe-extended-sources')
    geo=sub.add_parser('stage-incident-csv',help='Stage proximity-only records from a licensed official CSV; verified site points only')
    geo.add_argument('csv_path');geo.add_argument('--source',required=True)
    geo.add_argument('--id-column',default='id');geo.add_argument('--lat-column',default='latitude')
    geo.add_argument('--lon-column',default='longitude');geo.add_argument('--date-column',default='date_start')
    geo.add_argument('--title-column',default='description');geo.add_argument('--url-column',default='')
    geo.add_argument('--precision-column',default='');geo.add_argument('--radius-km',type=float,default=25.0)
    args=p.parse_args(argv)
    if args.command=='serve':
        validate_private_bind(args.host)
        import uvicorn
        uvicorn.run('facilityrisk.app:app',host=args.host,port=args.port,reload=False)
        return 0
    with connect() as conn:
        initialize(conn)
        if args.command=='init-db': output={'status':'initialized'}
        elif args.command=='qa':output={**quality_report(conn),'intelligence':intelligence_quality(conn)}
        elif args.command=='ingest-workbook':output=ingest_workbook(conn,args.xlsx)
        elif args.command=='export-browser':output=export_browser_snapshot(conn,args.output_json)
        elif args.command=='refresh-usgs':output=fetch_usgs(conn,args.facility,args.start,args.end,args.radius_km,args.min_magnitude)
        elif args.command=='refresh-aqueduct':output=fetch_aqueduct(conn,args.facility)
        elif args.command=='refresh-echo':
            verified=conn.execute("SELECT identifier FROM identity_links WHERE facility_id=? AND namespace='EPA_FRS' AND status='verified'",(args.facility,)).fetchone()
            if not verified or verified['identifier'] != args.registry_id:
                raise ValueError('ECHO refresh requires an accepted and audited EPA FRS identity match; use discover-frs and review-frs first')
            output=fetch_verified_echo(conn,args.facility)
        elif args.command=='ingest-noaa-csv':output=ingest_noaa_csv(conn,args.csv_gz,args.radius_km)
        elif args.command=='discover-frs':output=discover_frs(conn,args.facility,args.name,args.state)
        elif args.command=='review-frs':output=decide_candidate(conn,args.candidate,args.decision,args.reviewer,args.source,args.note)
        elif args.command=='review-fei':output=verify_fei(conn,args.facility,args.reviewer,args.source,args.note)
        elif args.command=='review-location':output=review_location(conn,args.facility,args.precision,args.source,args.reviewer,args.note)
        elif args.command=='refresh-fema':output=fetch_fema(conn,args.facility)
        elif args.command=='refresh-verified-echo':output=fetch_verified_echo(conn,args.facility)
        elif args.command=='ingest-fda-inspections-csv':output=ingest_fda_inspections_csv(conn,args.csv_path)
        elif args.command=='seed-cases':output=seed_cases(conn)
        elif args.command=='probe-sources':output={'checks':source_probe(conn)}
        elif args.command=='probe-extended-sources':output={'checks':probe_extensions(conn)}
        elif args.command=='stage-incident-csv':output=import_geo_csv(conn,args.csv_path,args.source,
            id_column=args.id_column, latitude_column=args.lat_column,
            longitude_column=args.lon_column, date_column=args.date_column,
            title_column=args.title_column, url_column=args.url_column,
            precision_column=args.precision_column, radius_km=args.radius_km)
        else: p.error('unknown command')
        print(json.dumps(output,indent=2,ensure_ascii=False,default=str))
        return 0


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print(f'ERROR: {exc}',file=sys.stderr)
        sys.exit(1)
