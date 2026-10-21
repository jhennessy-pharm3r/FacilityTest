"""Command-line ingestion and local service entry point."""
from __future__ import annotations
import argparse
import json
import sys
from .db import connect,initialize,quality_report
from .ingest import ingest_workbook
from .browser_export import export_browser_snapshot
from .connectors import fetch_usgs,fetch_aqueduct,fetch_echo,ingest_noaa_csv


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
    args=p.parse_args(argv)
    if args.command=='serve':
        import uvicorn
        uvicorn.run('facilityrisk.app:app',host=args.host,port=args.port,reload=False)
        return 0
    with connect() as conn:
        initialize(conn)
        if args.command=='init-db': output={'status':'initialized'}
        elif args.command=='qa':output=quality_report(conn)
        elif args.command=='ingest-workbook':output=ingest_workbook(conn,args.xlsx)
        elif args.command=='export-browser':output=export_browser_snapshot(conn,args.output_json)
        elif args.command=='refresh-usgs':output=fetch_usgs(conn,args.facility,args.start,args.end,args.radius_km,args.min_magnitude)
        elif args.command=='refresh-aqueduct':output=fetch_aqueduct(conn,args.facility)
        elif args.command=='refresh-echo':output=fetch_echo(conn,args.facility,args.registry_id)
        elif args.command=='ingest-noaa-csv':output=ingest_noaa_csv(conn,args.csv_gz,args.radius_km)
        else: p.error('unknown command')
        print(json.dumps(output,indent=2,ensure_ascii=False,default=str))
        return 0


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print(f'ERROR: {exc}',file=sys.stderr)
        sys.exit(1)