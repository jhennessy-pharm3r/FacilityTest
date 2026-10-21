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
from .security import validate_private_bind
from .registry_catalog import import_catalog
from .source_extensions import probe_extensions, import_geo_csv, review_event_candidate
from .fei_api import lookup_fei
from .assessment import export_assessment
from .pilot import export_pilot_manifest
from .research import start_research,research_history,run_source
from .site_workspace import (intake_site, import_official_registry_csv,
                             search_external_registry, stage_identity_candidate, import_ireland_leap_catalog, import_canada_npri_catalog)


def main(argv=None) -> int:
    p=argparse.ArgumentParser(prog='facilityrisk',description='Facility risk evidence app; local development only')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('init-db')
    ing=sub.add_parser('ingest-workbook');ing.add_argument('xlsx')
    sub.add_parser('qa')
    reg=sub.add_parser('import-registry');reg.add_argument('catalog_json')
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
    lookup=sub.add_parser('lookup-fda-fei',help='Use FDA-issued API credentials for an unverified FEI source observation')
    lookup.add_argument('--facility',required=True)
    vf=sub.add_parser('review-fei');vf.add_argument('--facility',required=True);vf.add_argument('--reviewer',required=True);vf.add_argument('--source',required=True);vf.add_argument('--note',required=True)
    loc=sub.add_parser('review-location');loc.add_argument('--facility',required=True);loc.add_argument('--precision',required=True,choices=['city','approximate','site_verified','property_polygon']);loc.add_argument('--reviewer',required=True);loc.add_argument('--source',required=True);loc.add_argument('--note',default='')
    fema=sub.add_parser('refresh-fema');fema.add_argument('--facility',required=True)
    ec=sub.add_parser('refresh-verified-echo');ec.add_argument('--facility',required=True)
    fda=sub.add_parser('ingest-fda-inspections-csv');fda.add_argument('csv_path')
    sub.add_parser('seed-cases');sub.add_parser('probe-sources')
    sub.add_parser('probe-extended-sources')
    geo=sub.add_parser('stage-incident-csv',help='Stage proximity-only records from an official CSV; verified site points only')
    geo.add_argument('csv_path');geo.add_argument('--source',required=True)
    geo.add_argument('--id-column',default='id');geo.add_argument('--lat-column',default='latitude')
    geo.add_argument('--lon-column',default='longitude');geo.add_argument('--date-column',default='date_start')
    geo.add_argument('--title-column',default='description');geo.add_argument('--url-column',default='')
    geo.add_argument('--precision-column',default='');geo.add_argument('--radius-km',type=float,default=25.0)
    intake=sub.add_parser('intake-site',help='Create a manual unverified research site')
    intake.add_argument('--name',required=True)
    intake.add_argument('--company',default='');intake.add_argument('--country',default='')
    intake.add_argument('--city',default='');intake.add_argument('--state',default='')
    intake.add_argument('--address',default='');intake.add_argument('--sector',default='')
    intake.add_argument('--source-url',default='')
    external=sub.add_parser('import-source-registry',help='Import official registry CSV as source identities only')
    external.add_argument('csv_path');external.add_argument('--source',required=True)
    external.add_argument('--source-url',required=True)
    external.add_argument('--id-column',default='source_id')
    external.add_argument('--name-column',default='name')
    external.add_argument('--company-column',default='')
    external.add_argument('--address-column',default='address')
    external.add_argument('--city-column',default='')
    external.add_argument('--state-column',default='')
    external.add_argument('--country-column',default='country')
    external.add_argument('--sector-column',default='')
    external.add_argument('--operations-column',default='')
    external.add_argument('--notes',default='')
    ireland=sub.add_parser('import-ireland-leap',help='Import downloaded official LEAP public JSON catalog')
    ireland.add_argument('catalog_json')
    canada=sub.add_parser('import-canada-npri',help='Import official Canadian NPRI public JSON catalog')
    canada.add_argument('catalog_json')
    search_external=sub.add_parser('search-source-registry')
    search_external.add_argument('--query',default='')
    search_external.add_argument('--source',default='')
    search_external.add_argument('--country',default='')
    candidate=sub.add_parser('stage-identity-candidate')
    candidate.add_argument('--facility',required=True)
    candidate.add_argument('--external-id',required=True)
    event_review=sub.add_parser('review-external-event')
    event_review.add_argument('--candidate',required=True)
    event_review.add_argument('--decision',required=True,choices=['reviewed_relevant','rejected'])
    event_review.add_argument('--reviewer',required=True)
    event_review.add_argument('--source-url',required=True)
    event_review.add_argument('--reason',required=True)
    pilot=sub.add_parser('build-pilot',help='Create 25-row UNVERIFIED source-based research pilot')
    pilot.add_argument('--output',default='data/pilot-research-candidates.csv')
    research=sub.add_parser('plan-research',help='Create a durable, explicit facility research plan')
    research.add_argument('--facility',required=True)
    summary=sub.add_parser('research-status',help='Show current site research plan and source attempts')
    summary.add_argument('--facility',required=True)
    run=sub.add_parser('run-research-source',help='Perform one explicitly authorized source query')
    run.add_argument('--facility',required=True)
    run.add_argument('--source',required=True,choices=['fema_flood','wri_water','epa_echo','usgs_earthquake'])
    run.add_argument('--start',default='');run.add_argument('--end',default='')
    run.add_argument('--radius-km',type=float,default=150.0)
    report=sub.add_parser('export-assessment',help='Export a private source-evidence HTML facility assessment')
    report.add_argument('--facility',required=True)
    report.add_argument('--output',required=True)
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
        elif args.command=='import-registry':output=import_catalog(conn,args.catalog_json)
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
        elif args.command=='lookup-fda-fei':output=lookup_fei(conn,args.facility,'local-cli')
        elif args.command=='review-fei':output=verify_fei(conn,args.facility,args.reviewer,args.source,args.note)
        elif args.command=='review-location':output=review_location(conn,args.facility,args.precision,args.source,args.reviewer,args.note)
        elif args.command=='refresh-fema':output=fetch_fema(conn,args.facility)
        elif args.command=='refresh-verified-echo':output=fetch_verified_echo(conn,args.facility)
        elif args.command=='ingest-fda-inspections-csv':output=ingest_fda_inspections_csv(conn,args.csv_path)
        elif args.command=='build-pilot':
            output=export_pilot_manifest(args.output)
        elif args.command=='plan-research':
            output=start_research(conn,args.facility,'local-cli')
        elif args.command=='research-status':
            output=research_history(conn,args.facility)
        elif args.command=='run-research-source':
            output=run_source(conn,args.facility,args.source,'local-cli',
                              start=args.start,end=args.end,radius_km=args.radius_km)
        elif args.command=='export-assessment':
            output=export_assessment(conn,args.facility,args.output)
        elif args.command=='seed-cases':output=seed_cases(conn)
        elif args.command=='probe-sources':output={'checks':source_probe(conn)}
        elif args.command=='probe-extended-sources':output={'checks':probe_extensions(conn)}
        elif args.command=='stage-incident-csv':output=import_geo_csv(conn,args.csv_path,args.source,
            id_column=args.id_column, latitude_column=args.lat_column,
            longitude_column=args.lon_column, date_column=args.date_column,
            title_column=args.title_column, url_column=args.url_column,
            precision_column=args.precision_column, radius_km=args.radius_km)
        elif args.command=='intake-site':
            output=intake_site(conn,{k:getattr(args,k) for k in
                ('name','company','country','city','state','address','sector','source_url')},'local-cli')
        elif args.command=='import-source-registry':
            output=import_official_registry_csv(conn,args.csv_path,args.source,args.source_url,
                id_column=args.id_column,name_column=args.name_column,
                company_column=args.company_column,address_column=args.address_column,
                city_column=args.city_column,state_column=args.state_column,
                country_column=args.country_column,sector_column=args.sector_column,
                operations_column=args.operations_column,notes=args.notes)
        elif args.command=='import-ireland-leap':
            output=import_ireland_leap_catalog(conn,args.catalog_json)
        elif args.command=='import-canada-npri':
            output=import_canada_npri_catalog(conn,args.catalog_json)
        elif args.command=='search-source-registry':
            output=search_external_registry(conn,query=args.query,source_key=args.source,country=args.country)
        elif args.command=='stage-identity-candidate':
            output=stage_identity_candidate(conn,args.facility,args.external_id,'local-cli')
        elif args.command=='review-external-event':
            output=review_event_candidate(conn,args.candidate,args.decision,args.reviewer,
                                         args.source_url,args.reason)
        else: p.error('unknown command')
        print(json.dumps(output,indent=2,ensure_ascii=False,default=str))
        return 0


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print(f'ERROR: {exc}',file=sys.stderr)
        sys.exit(1)