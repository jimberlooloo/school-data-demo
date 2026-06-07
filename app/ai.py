"""AI 'ask a question' layer — natural language -> SQL over the marts.

Provider-swappable via env var AI_PROVIDER: 'gemini' (default, free tier),
'anthropic', or 'openai'. Each just hits the provider's REST API with `requests`,
so swapping is a one-line change.

Guardrails (defence in depth):
  - the generated SQL is validated SELECT-only, single-statement, mart-scoped;
  - an auto-LIMIT is added;
  - the SQL is always shown to the user (the dashboard renders it);
  - and it should run under a read-only role (set SNOWFLAKE_AI_ROLE=READER after
    running snowflake/setup_reader.sql) so it physically cannot modify anything.
"""
import os
import re

import requests

SCHEMA = """You are writing plain standard SQL (it must run on both Snowflake and DuckDB).
Use the BARE table names below — no schema/database prefix (e.g. `dim_school`, not
`schema.dim_school`). Avoid vendor-specific functions. Only these tables exist:

dim_school (one row per school; PK urn):
  urn, establishment_name, phase, is_secondary (boolean), la_code, la_name, region

fct_attendance_weekly (grain: local authority x week x phase):
  attendance_key, la_code, academic_year, week_label,
  phase ('Primary' | 'Secondary' | 'Special'),
  possible_sessions, pct_overall_absence, pct_authorised_absence,
  pct_unauthorised_absence, pct_attendance

fct_ks4_results (grain: school x academic year; GCSE results, secondary only):
  ks4_key, urn, school_name, la_name, academic_year,
  attainment8_score, pct_grade5_eng_maths, ebacc_aps

Notes:
- la_name is a LOCAL AUTHORITY (e.g. 'Surrey', 'Barnet', 'Norfolk'). To filter by an
  area, use la_name — do NOT put an LA name in region.
- region is one of exactly: 'North East', 'North West', 'Yorkshire and the Humber',
  'East Midlands', 'West Midlands', 'East of England', 'London', 'South East', 'South West'.
- is_secondary is a boolean (use = TRUE / = FALSE).
- Attendance is only at local-authority grain — there is NO per-school attendance/absence.
  All schools in an LA share that LA's attendance, so you cannot rank individual schools
  by attendance; rank schools only by KS4 measures.
- Join attendance to schools via la_code; join KS4 to dim_school via urn.
- Match a named school with ILIKE '%name%' (case-insensitive, partial) — NEVER exact "=" or
  IN on a school name; users give informal names (e.g. 'Ash Manor' means 'Ash Manor School').
- To list or compare specific schools, query fct_ks4_results directly (it already has
  school_name) — do NOT go via dim_school, and do NOT join attendance (it is LA-level, not
  per-school). Compare schools on KS4 measures only.
- Many schools have NULL measures (suppressed, or not applicable — special/independent
  schools often have no Attainment 8). When ranking or filtering by a measure, exclude
  NULLs (e.g. WHERE attainment8_score IS NOT NULL) or use NULLS LAST — otherwise NULLs
  sort to the top in DESC and you get meaningless rows.

Write ONE read-only SELECT (or WITH ... SELECT) query that answers the question.
Return ONLY the SQL — no prose, no markdown fences."""

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|merge|grant|revoke|"
    r"call|use|copy|put|remove|comment|execute)\b", re.IGNORECASE)


def _prompt(question):
    return f"{SCHEMA}\n\nQuestion: {question}\nSQL:"


def _gemini(question):
    key = os.environ["GEMINI_API_KEY"]
    model = os.environ.get("AI_MODEL", "gemini-2.0-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    r = requests.post(url, headers={"x-goog-api-key": key},  # key in header, never in the URL/errors
                      json={"contents": [{"parts": [{"text": _prompt(question)}]}]}, timeout=30)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _anthropic(question):
    key = os.environ["ANTHROPIC_API_KEY"]
    model = os.environ.get("AI_MODEL", "claude-3-5-haiku-latest")
    r = requests.post("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                      json={"model": model, "max_tokens": 500,
                            "messages": [{"role": "user", "content": _prompt(question)}]},
                      timeout=30)
    r.raise_for_status()
    return r.json()["content"][0]["text"]


def _openai(question):
    key = os.environ["OPENAI_API_KEY"]
    model = os.environ.get("AI_MODEL", "gpt-4o-mini")
    r = requests.post("https://api.openai.com/v1/chat/completions",
                      headers={"Authorization": f"Bearer {key}"},
                      json={"model": model,
                            "messages": [{"role": "user", "content": _prompt(question)}]},
                      timeout=30)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _groq(question):
    # Groq is OpenAI-compatible and has a genuinely free tier (no card needed).
    key = os.environ["GROQ_API_KEY"]
    model = os.environ.get("AI_MODEL", "llama-3.3-70b-versatile")
    r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                      headers={"Authorization": f"Bearer {key}"},
                      json={"model": model,
                            "messages": [{"role": "user", "content": _prompt(question)}]},
                      timeout=30)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


_PROVIDERS = {"gemini": _gemini, "anthropic": _anthropic, "openai": _openai, "groq": _groq}


def _clean(text):
    t = text.strip()
    t = re.sub(r"^```(?:sql)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*```$", "", t)
    return t.strip().rstrip(";").strip()


def generate_sql(question):
    provider = os.environ.get("AI_PROVIDER", "gemini").lower()
    return _clean(_PROVIDERS[provider](question))


def validate_sql(sql):
    """Return (ok: bool, message: str). Read-only + mart-scoped guardrails."""
    low = sql.lower().strip()
    if not (low.startswith("select") or low.startswith("with")):
        return False, "Only SELECT queries are allowed."
    if ";" in sql.strip().rstrip(";"):
        return False, "Only a single statement is allowed."
    if FORBIDDEN.search(sql):
        return False, "Query contains a non-read-only keyword."
    if re.search(r"\b(raw|information_schema|snowflake)\s*\.", low):
        return False, "Query may only use the analytics marts (no raw/system schemas)."
    return True, "ok"


def with_limit(sql, n=1000):
    return sql if re.search(r"\blimit\b", sql, re.IGNORECASE) else f"{sql}\nlimit {n}"
