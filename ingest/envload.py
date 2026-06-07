"""Load KEY=VALUE lines from the repo's .env into os.environ — no override, no deps.

Used by both the Snowflake helper and the DuckDB data layer so config/keys live in one
gitignored .env regardless of which backend runs (and without dragging the Snowflake
connector into the lightweight DuckDB path).
"""
import os


def load_dotenv():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                if key.startswith("export "):
                    key = key[len("export "):].strip()
                if key:
                    os.environ.setdefault(key, val.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass
