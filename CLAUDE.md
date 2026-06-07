# Project guide

England schools data pipeline: **Snowflake + dbt** over public DfE open data (school register,
weekly attendance, KS4/GCSE results), modelled into a tested star schema and surfaced in a
**Streamlit** dashboard. See [SPEC.md](SPEC.md) for the contract.

## Layout
- `ingest/` — Python loaders (download DfE CSVs → Snowflake `RAW` via stage + `COPY INTO`) and the
  app data layer (`db.py`, which reads live Snowflake locally or the bundled DuckDB for deploy).
- `models/` — dbt: `stg_<source>` staging **views** → `dim_`/`fct_` mart **tables**, with tests.
- `analyses/` — dbt analyses (the insight queries).
- `app/` — Streamlit dashboard (`dashboard.py`) + AI NL→SQL layer (`ai.py`), reading the marts only.
- `snowflake/` — role-setup SQL (least-privilege service + read-only roles).

## Conventions
- **Spec-first:** SPEC.md is the contract; flag anything not covered there before building.
- **Layering:** source → `stg_<source>` (views, rename/recast) → `dim_`/`fct_` (tables).
  `snake_case` columns; `is_` booleans; `_date` date suffixes; surrogate keys via `md5()` of the grain.
- **Marts only in the app** — never query the raw schema.
- **Reviewed changes:** work on a branch, open a PR with an honest description (including known
  weaknesses); the human reviews and merges.
- **Never** commit credentials, account identifiers, `profiles.yml`, or raw data files.

## Run
See the README "Run it" section.
