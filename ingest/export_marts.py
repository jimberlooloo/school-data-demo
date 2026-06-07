#!/usr/bin/env python3
"""Export the Snowflake marts to a local DuckDB file for the decoupled (deployed) app.

Run once (re-runnable) with Snowflake access:
    python ingest/export_marts.py

Reads ANALYTICS.{dim_school, fct_attendance_weekly, fct_ks4_results} via key-pair and
writes app/marts.duckdb — a small, read-only serving copy so the deployed dashboard needs
no live Snowflake (and survives the trial). This is the "serving layer in front of the
warehouse" pattern, at indie scale.
"""
import os

import duckdb
from snow import connect

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "app", "marts.duckdb")
TABLES = ["dim_school", "fct_attendance_weekly", "fct_ks4_results"]


def main():
    if os.path.exists(OUT):
        os.remove(OUT)  # rebuild clean
    sf = connect(schema="ANALYTICS")
    duck = duckdb.connect(OUT)
    try:
        for t in TABLES:
            df = sf.cursor().execute(f"select * from ANALYTICS.{t}").fetch_pandas_all()
            df.columns = [c.lower() for c in df.columns]
            duck.execute(f"create or replace table {t} as select * from df")
            print(f"  {t}: {len(df):,} rows")
    finally:
        duck.close()
        sf.close()
    print(f"wrote {OUT} ({os.path.getsize(OUT) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
