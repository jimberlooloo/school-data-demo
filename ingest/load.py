#!/usr/bin/env python3
"""Block 2 ingest loader for the school-data pipeline.

Downloads three DfE open-data CSVs and lands them as STRING-typed tables in
SCHOOLS.RAW via a named stage + COPY INTO. NO filtering or casting happens here —
that is the dbt staging layer's job (visible, tested, version-controlled).
Connection comes from ingest/snow.py (config via env vars; key-pair, no password).

  GIAS  -> narrowed to 7 columns + snake_cased (source has 250+ messy headers)
  EES   -> attendance + KS4 landed whole (already clean snake_case; staging selects)
"""
import io
import os
import re
import datetime as dt
import urllib.request
import urllib.error

import pandas as pd

from snow import connect

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN_DIR = os.path.join(REPO, "data", "clean")

ATT_ID = "0bad0493-cb82-4312-a21f-5c7570f6eb5e"
KS4_ID = "5b3d308c-da72-467f-b2ef-ab77d576a455"
EES = "https://explore-education-statistics.service.gov.uk/data-catalogue/data-set/{}/csv"
GIAS = "https://ea-edubase-api-prod.azurewebsites.net/edubase/downloads/public/edubasealldata{:%Y%m%d}.csv"

GIAS_COLS = {
    "URN": "urn",
    "EstablishmentName": "establishment_name",
    "PhaseOfEducation (name)": "phase_name",
    "LA (code)": "la_code",
    "LA (name)": "la_name",
    "EstablishmentStatus (name)": "establishment_status",
    "GOR (name)": "region_name",
}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "school-data-demo/0.1"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def san(c):
    """Make a safe snake_case Snowflake identifier (also strips any BOM)."""
    return re.sub(r"[^0-9a-z]+", "_", c.strip().lower()).strip("_")


def download_gias():
    today = dt.date.today()
    last_err = None
    for back in range(3):  # date-stamped URL; fall back up to 2 days on 404
        d = today - dt.timedelta(days=back)
        url = GIAS.format(d)
        try:
            raw = fetch(url)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                last_err = e
                continue
            raise
        print(f"  GIAS: {url}")
        df = pd.read_csv(io.BytesIO(raw), encoding="latin-1", dtype=str, low_memory=False)
        missing = [c for c in GIAS_COLS if c not in df.columns]
        if missing:
            raise SystemExit(f"GIAS missing expected columns {missing}\nGot: {list(df.columns)[:40]}")
        return df[list(GIAS_COLS)].rename(columns=GIAS_COLS)
    raise SystemExit(f"GIAS download failed (no file in last 3 days): {last_err}")


def download_ees(dsid, label):
    url = EES.format(dsid)
    print(f"  {label}: {url}")
    return pd.read_csv(io.BytesIO(fetch(url)), dtype=str, low_memory=False)


def land(con, df, table):
    df = df.copy()
    df.columns = [san(c) for c in df.columns]
    os.makedirs(CLEAN_DIR, exist_ok=True)
    path = os.path.join(CLEAN_DIR, f"{table}.csv")
    df.to_csv(path, index=False)

    cols_ddl = ", ".join(f"{c} STRING" for c in df.columns)
    cur = con.cursor()
    cur.execute("CREATE FILE FORMAT IF NOT EXISTS SCHOOLS.RAW.ff_csv "
                "TYPE=CSV SKIP_HEADER=1 FIELD_OPTIONALLY_ENCLOSED_BY='\"' EMPTY_FIELD_AS_NULL=TRUE")
    cur.execute("CREATE STAGE IF NOT EXISTS SCHOOLS.RAW.load_stage FILE_FORMAT=SCHOOLS.RAW.ff_csv")
    cur.execute(f"CREATE OR REPLACE TABLE SCHOOLS.RAW.{table} ({cols_ddl})")
    cur.execute(f"PUT 'file://{path}' @SCHOOLS.RAW.load_stage OVERWRITE=TRUE AUTO_COMPRESS=TRUE")
    cur.execute(f"COPY INTO SCHOOLS.RAW.{table} FROM @SCHOOLS.RAW.load_stage/{table}.csv.gz "
                f"FILE_FORMAT=(FORMAT_NAME=SCHOOLS.RAW.ff_csv) ON_ERROR='ABORT_STATEMENT'")
    cur.execute(f"SELECT COUNT(*) FROM SCHOOLS.RAW.{table}")
    n = cur.fetchone()[0]
    print(f"  -> SCHOOLS.RAW.{table}: {n:,} rows x {len(df.columns)} cols")
    return n


def main():
    print("Downloading sources...")
    gias = download_gias()
    att = download_ees(ATT_ID, "attendance")
    ks4 = download_ees(KS4_ID, "ks4")
    print(f"  downloaded rows: gias={len(gias):,}  attendance={len(att):,}  ks4={len(ks4):,}")

    print("Loading into SCHOOLS.RAW (named stage + COPY INTO)...")
    con = connect()
    try:
        land(con, gias, "raw_gias")
        land(con, att, "raw_attendance")
        land(con, ks4, "raw_ks4")
    finally:
        con.close()
    print("Done.")


if __name__ == "__main__":
    main()
