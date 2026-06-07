"""Shared Snowflake connection helper for the pipeline scripts.

Connection config comes from environment variables (nothing hardcoded, no secrets
in code) — see .env.example:
    SNOWFLAKE_ACCOUNT            required, e.g. ab12345-xy67890
    SNOWFLAKE_PRIVATE_KEY_PATH   optional, default ~/.snowflake/rsa_key.p8

Auth is key-pair (no password). Role/warehouse/db/schema are caller args with
sane defaults (the least-privilege service identity).
"""
import os

import snowflake.connector


from envload import load_dotenv  # noqa: E402

load_dotenv()


def connect(user="DBT_SVC", role="TRANSFORMER", warehouse="COMPUTE_WH",
            database="SCHOOLS", schema="RAW"):
    account = os.environ.get("SNOWFLAKE_ACCOUNT")
    if not account:
        raise SystemExit("Set SNOWFLAKE_ACCOUNT (see .env.example).")
    key_path = os.path.expanduser(
        os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH", "~/.snowflake/rsa_key.p8"))
    return snowflake.connector.connect(
        account=account, user=user, role=role, warehouse=warehouse,
        database=database, schema=schema, private_key_file=key_path,
        client_session_keep_alive=True,  # heartbeat so long-running app sessions don't expire
    )
