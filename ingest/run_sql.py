#!/usr/bin/env python3
"""Run a .sql file against Snowflake using key-pair auth.

Usage:
    python ingest/run_sql.py <file.sql> [--user U] [--role R]

Connection config (account, key path) comes from env vars via ingest/snow.py.
Defaults connect as the least-privilege service identity (DBT_SVC / TRANSFORMER).
For one-off admin setup, pass --user <admin> --role ACCOUNTADMIN.
No password anywhere — auth is key-pair.
"""
import argparse

from snow import connect


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sqlfile")
    ap.add_argument("--user", default="DBT_SVC")
    ap.add_argument("--role", default="TRANSFORMER")
    ap.add_argument("--warehouse", default="COMPUTE_WH")
    ap.add_argument("--database", default="SCHOOLS")
    args = ap.parse_args()

    con = connect(user=args.user, role=args.role,
                  warehouse=args.warehouse, database=args.database)
    try:
        with open(args.sqlfile) as f:
            for cur in con.execute_stream(f):
                first = (cur.query or "").strip().splitlines()
                print(f"OK  {first[0][:70] if first else '(stmt)'}")
    finally:
        con.close()


if __name__ == "__main__":
    main()
