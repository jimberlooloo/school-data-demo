"""Data access layer: DuckDB (bundled, for deploy) or Snowflake (local dev).

Backend selection:
  - DATA_BACKEND env ('duckdb' | 'snowflake') forces it; otherwise
  - 'snowflake' if SNOWFLAKE_ACCOUNT is set, else 'duckdb' (the bundled read-only file).

So local dev (with .env) hits live Snowflake; the deployed app (no Snowflake secret) reads
the read-only DuckDB copy — a serving layer in front of the warehouse, no DB credential at
the edge. Queries use bare table names + plain SQL so they run on either backend.
"""
import functools
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "ingest"))
from envload import load_dotenv  # noqa: E402

load_dotenv()

DUCKDB_PATH = os.path.join(REPO, "app", "marts.duckdb")


def backend():
    forced = os.environ.get("DATA_BACKEND")
    if forced:
        return forced.lower()
    return "snowflake" if os.environ.get("SNOWFLAKE_ACCOUNT") else "duckdb"


@functools.lru_cache(maxsize=1)
def _duck():
    import duckdb
    return duckdb.connect(DUCKDB_PATH, read_only=True)  # read-only = a hard guardrail


@functools.lru_cache(maxsize=1)
def _snow():
    from snow import connect
    return connect(schema="ANALYTICS")


def query(sql):
    """Run read-only SQL and return a pandas DataFrame."""
    if backend() == "duckdb":
        return _duck().execute(sql).fetch_df()
    return _snow().cursor().execute(sql).fetch_pandas_all()
