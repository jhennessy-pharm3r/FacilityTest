"""Lane D full-year ORNL EAGLE-I 2025 ORIGINAL 15-minute county readings.

Public author-provided Figshare release DOI 10.6084/m9.figshare.24237376.v4;
1,402,347,695-byte original 'eaglei_outages_2025.csv', CC BY 4.0.

**EAGLE-I county/customer-out readings are NOT outage episodes or insured
properties.** Missing county×15-minute records can be zero, no utility feed or
failed capture; absence cannot establish continuity/low risk. Never infer
individual customer overlap, duration or paid claims from samples.

Original full file SHA256 and publisher MD5 are verified BEFORE ingest.
Every accepted county/timestamp SOURCE READING remains separately represented
in compressed Parquet with original-position provenance; county-day SQLite is
an explicitly coarser QUERY SUMMARY, not a site outage/event index.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sqlite3

FIGSHARE="https://api.figshare.com/v2/articles/24237376"
SOURCE_ID=62164877
SOURCE_NAME="eaglei_outages_2025.csv"
SOURCE_SIZE=1402347695
PUBLISHER_MD5="cd2feb1282a42fb048cb6885398bc1cc"
HEADERS=["fips_code","county","state","customers_out","run_start_time"]


def hash_file(path):
    md5=hashlib.md5()
    sha=hashlib.sha256()
    size=0
    with Path(path).open("rb") as f:
        for part in iter(lambda:f.read(8*1024*1024),b""):
            md5.update(part)
            sha.update(part)
            size+=len(part)
    return sha.hexdigest(),md5.hexdigest(),size


def source_metadata(meta_path,csv_path,allow_fixture=False):
    raw=Path(meta_path).read_bytes()
    meta=json.loads(raw)
    if meta.get("id")!=24237376 or meta.get("version")!=4:
        raise ValueError("Unrecognized original EAGLE-I 2025 published release/version")
    if (meta.get("license") or {}).get("name")!="CC BY 4.0":
        raise ValueError("Original published file license not CC BY 4.0")
    files=[f for f in (meta.get("files") or []) if f.get("name")==SOURCE_NAME and f.get("id")==SOURCE_ID]
    if len(files)!=1:
        raise ValueError("Original 2025 EAGLE-I file absent or ambiguous")
    info=files[0]
    if info.get("download_url")!="https://ndownloader.figshare.com/files/62164877":
        raise ValueError("Original 2025 publisher download location changed")
    if not allow_fixture and (info.get("size")!=SOURCE_SIZE or info.get("computed_md5")!=PUBLISHER_MD5):
        raise ValueError("Official Figshare file identity/byte size or MD5 differs from vetted release")
    original_sha,actual_md5,actual_size=hash_file(csv_path)
    if actual_md5!=info.get("computed_md5") or actual_size!=info.get("size"):
        raise ValueError("Downloaded full original publisher CSV MD5/length does not match release metadata")
    return {
        "original_metadata_json_sha256":hashlib.sha256(raw).hexdigest(),
        "original_source_csv_sha256":original_sha,
        "original_source_csv_md5":actual_md5,
        "original_source_csv_bytes":actual_size,
        "publisher_version":meta["version"],
        "publisher_license":meta["license"],
        "publisher_file_id":SOURCE_ID,
        "publisher_doi":meta.get("doi"),
        "publisher_original_download_url":info["download_url"],
    }


def run(csv_path,meta_path,out,allow_fixture=False):
    try:
        import duckdb
    except ImportError as e:
        raise RuntimeError("DuckDB source ingestion dependency not installed") from e
    csv_path=Path(csv_path).resolve()
    out=Path(out)
    out.mkdir(parents=True,exist_ok=True)
    source=source_metadata(meta_path,csv_path,allow_fixture=allow_fixture)
    db_path=out/"eaglei_2025_ephemeral.duckdb"
    accepted_parquet=out/"eaglei_2025_readings.parquet"
    reject_file=out/"rejected_original_rows.jsonl"
    county_day=out/"eaglei_2025_county_day_staging.sqlite"
    if any(p.exists() for p in (db_path,accepted_parquet,reject_file,county_day)):
        raise FileExistsError("Destination has source index outputs; use a fresh immutable stage path")
    db=duckdb.connect(str(db_path))
    try:
        db.execute("SET preserve_insertion_order = true")
        db.execute("SET threads = 3")
        db.execute("SET memory_limit = '3GB'")
        db.execute("""CREATE TABLE original_rows AS
              SELECT row_number() OVER () AS original_source_position_1based,
                     fips_code,county,state,customers_out,run_start_time
              FROM read_csv(?,auto_detect=false,header=true,
                  columns={'fips_code':'VARCHAR','county':'VARCHAR',
                           'state':'VARCHAR','customers_out':'VARCHAR',
                           'run_start_time':'VARCHAR'})""",[str(csv_path)])
        scanned=db.execute("SELECT COUNT(*) FROM original_rows").fetchone()[0]
        validated="""regexp_full_match(fips_code,'[0-9]{5}') AND
             length(trim(coalesce(county,'')))>0 AND
             length(trim(coalesce(state,'')))>0 AND
             regexp_full_match(customers_out,'[0-9]+') AND
             try_strptime(run_start_time,'%Y-%m-%d %H:%M:%S') >= TIMESTAMP '2025-01-01 00:00:00' AND
             try_strptime(run_start_time,'%Y-%m-%d %H:%M:%S') < TIMESTAMP '2026-01-01 00:00:00'"""
        db.execute("""CREATE TABLE readings AS
             SELECT original_source_position_1based,
                    fips_code AS original_fips_code,
                    county AS original_county,
                    state AS original_state,
                    cast(customers_out AS BIGINT) AS original_customers_out,
                    try_strptime(run_start_time,'%Y-%m-%d %H:%M:%S') AS original_timestamp_utc
             FROM original_rows WHERE """+validated)
        db.execute("""CREATE TABLE rejected_original_rows AS
             SELECT *,CASE
                 WHEN NOT regexp_full_match(coalesce(fips_code,''),'[0-9]{5}') THEN 'invalid_fips'
                 WHEN length(trim(coalesce(county,'')))=0 THEN 'missing_county'
                 WHEN length(trim(coalesce(state,'')))=0 THEN 'missing_state'
                 WHEN NOT regexp_full_match(coalesce(customers_out,''),'[0-9]+') THEN 'invalid_customer_count'
                 ELSE 'invalid_or_out_of_2025_utc_time' END AS reject_reason
             FROM original_rows WHERE NOT ("""+validated+")")
        accepted=db.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
        rejected=db.execute("SELECT COUNT(*) FROM rejected_original_rows").fetchone()[0]
        if scanned!=accepted+rejected or accepted==0:
            raise RuntimeError("Full original EAGLE-I reading reconciliation failed")
        db.execute("COPY readings TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",[str(accepted_parquet)])
        db.execute("""COPY (
            SELECT original_source_position_1based,fips_code,county,state,
                   customers_out,run_start_time,reject_reason
            FROM rejected_original_rows ORDER BY original_source_position_1based
        ) TO ? (FORMAT JSON)""",[str(reject_file)])
        db.execute("""CREATE TABLE daily_source_observation_summary AS
            SELECT original_fips_code,
                   cast(original_timestamp_utc AS DATE) AS observed_day_utc,
                   COUNT(*) AS original_accepted_rows,
                   COUNT(DISTINCT original_timestamp_utc) AS distinct_observed_15min_timestamps,
                   COUNT(*)-COUNT(DISTINCT original_timestamp_utc) AS repeated_county_timestamp_keys,
                   MAX(original_customers_out) AS largest_reported_customers_out_one_reading,
                   AVG(original_customers_out) AS avg_customers_out_across_reported_readings,
                   MIN(original_timestamp_utc) AS first_reported_utc,
                   MAX(original_timestamp_utc) AS last_reported_utc
            FROM readings GROUP BY 1,2 ORDER BY 1,2""")
        summary=db.execute("""SELECT
            COUNT(DISTINCT original_fips_code),
            COUNT(DISTINCT original_state),
            MIN(original_timestamp_utc),MAX(original_timestamp_utc),
            SUM(CASE WHEN original_customers_out=0 THEN 1 ELSE 0 END),
            MIN(original_customers_out),MAX(original_customers_out)
            FROM readings""").fetchone()
        daily=db.execute("""SELECT COUNT(*), SUM(original_accepted_rows),
            SUM(repeated_county_timestamp_keys) FROM daily_source_observation_summary""").fetchone()
        missing=db.execute("""SELECT reject_reason, COUNT(*) FROM rejected_original_rows GROUP BY 1""").fetchall()
        parquet_count=db.execute("SELECT COUNT(*) FROM read_parquet(?)",[str(accepted_parquet)]).fetchone()[0]
        if parquet_count!=accepted or daily[1]!=accepted:
            raise RuntimeError("Full reading Parquet or county/day reconciliation failed")
        with sqlite3.connect(county_day) as target:
            target.execute("""CREATE TABLE observed_county_day (
                county_fips TEXT NOT NULL,observed_date_utc TEXT NOT NULL,
                accepted_source_readings INTEGER NOT NULL,
                distinct_observed_15min_slots INTEGER NOT NULL,
                repeated_county_time_keys INTEGER NOT NULL,
                max_reported_customers_out INTEGER,
                observed_readings_mean_customers_out REAL,
                first_observed_utc TEXT,last_observed_utc TEXT,
                PRIMARY KEY(county_fips,observed_date_utc)
            )""")
            cursor=db.execute("""SELECT original_fips_code,
                cast(observed_day_utc AS VARCHAR),original_accepted_rows,
                distinct_observed_15min_timestamps,repeated_county_timestamp_keys,
                largest_reported_customers_out_one_reading,
                avg_customers_out_across_reported_readings,
                cast(first_reported_utc AS VARCHAR),cast(last_reported_utc AS VARCHAR)
                FROM daily_source_observation_summary ORDER BY 1,2""")
            while True:
                batch=cursor.fetchmany(10000)
                if not batch:break
                target.executemany("INSERT INTO observed_county_day VALUES (?,?,?,?,?,?,?,?,?)",batch)
            target.execute("CREATE INDEX idx_eaglei_day ON observed_county_day(observed_date_utc)")
            target.commit()
            if target.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                raise RuntimeError("EAGLE-I summarized serving SQLite integrity failed")
            summary_index_count=target.execute("SELECT COUNT(*) FROM observed_county_day").fetchone()[0]
            summary_index_readings=target.execute("SELECT SUM(accepted_source_readings) FROM observed_county_day").fetchone()[0]
        if summary_index_count!=daily[0] or summary_index_readings!=accepted:
            raise RuntimeError("Daily aggregated serving index not reconciled to full source readings")
        receipt={
            "source":"ORNL_EAGLEI_2025_FIGSHARE_ORIGINAL_15MIN_COUNTY_READINGS",
            "observed_utc":datetime.now(timezone.utc).isoformat(),
            "source_original_publisher":FIGSHARE,
            "source_grain":"PUBLISHER_REPORTED_COUNTY_CUSTOMERS_OUT_15MIN_READING_NOT_OUTAGE_EPISODE",
            "original_full_file_identity":source,
            "downloaded_original_source_rows":scanned,
            "accepted_normalized_source_readings":accepted,
            "rejected_original_source_rows":rejected,
            "rejected_original_reasons":dict(missing),
            "staged_readonly_parquet_original_reading_rows":parquet_count,
            "staged_county_day_sqlite_aggregate_rows":summary_index_count,
            "staged_county_day_original_reading_reconciliation":summary_index_readings,
            "staged_sqlite_aggregate_sha256":hash_file(county_day)[0],
            "staged_parquet_sha256":hash_file(accepted_parquet)[0],
            "staged_parquet_bytes":accepted_parquet.stat().st_size,
            "first_original_reported_timestamp_utc":str(summary[2]),
            "last_original_reported_timestamp_utc":str(summary[3]),
            "distinct_county_fips_in_accepted_source":summary[0],
            "distinct_original_state_names":summary[1],
            "original_zero_customers_out_reading_rows":summary[4],
            "min_reported_customers_out_in_one_source_reading":summary[5],
            "max_reported_customers_out_in_one_source_reading":summary[6],
            "repeated_same_county_timestamp_source_keys":daily[2],
            "independently_verified_physical_property_power_outages":0,
            "independently_verified_paid_insured_bi_claims":0,
            "persistent_backend_indexed":0,
            "deployed":0,
            "restrictions":[
                "Only source county×15-minute CUSTOMER-OUT observations; one record is NOT one power outage episode/customer/property",
                "The original raw file can omit zero-outage time slots or missing data collection; absence is UNKNOWN, not zero risk",
                "Repeated FIPS/timestamp records are retained in source Parquet; county/day aggregation reports repeated keys separately",
                "County/day average is across PUBLISHED readings, often nonzero-biased, not a blackout probability or SAIDI/SAIFI denominator",
                "Time field is interpreted UTC per ORNL EAGLE-I research publication, and requires independent property service verification",
                "New public 2025 EAGLE-I original 15-minute readings overlap the historic PNNL 2014-2023 DERIVED episode/correlation data by publisher lineage, not additive to PNNL outages",
                "ORNL public release is CC BY 4.0: attribute authors/date/source/version/license; no approval to infer paid carrier claims",
            ],
        }
        (out/"manifest.json").write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+"\n")
        return receipt
    finally:
        db.close()


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--csv",type=Path,required=True)
    p.add_argument("--release-metadata",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(run(a.csv,a.release_metadata,a.output),indent=2,ensure_ascii=False))


if __name__=="__main__":
    main()
