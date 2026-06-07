# SPEC — England school-data pipeline

> Spec-first contract, written before any building.
> Nothing gets built that isn't covered here without flagging it.

## 1. Goal & scope

**Goal (dual — both must survive every decision):** (1) build a small, canonical Snowflake + dbt artifact that demonstrates analytics-engineering fundamentals (raw → staging → marts, a conformed-dimension star schema, dbt tests); and (2) demonstrate an AI-first way of working — spec-first, agentic execution, human PR review, honest failure logging — where the *process evidence* matters as much as the code. Every trade-off biases toward "teaches the concept and is explainable" over cleverness or completeness.

**Pitch (one paragraph):** A small, canonical Snowflake + dbt pipeline over English schools open data. It lands two public DfE datasets, models them through raw → staging → marts into a conformed-dimension star schema (`dim_school` + two facts at two different grains), proves quality with dbt tests, and surfaces a handful of genuinely interesting insights — including a cross-domain one linking **pupil absence** to **GCSE attainment** — in a README and a small Streamlit dashboard. The build is run AI-first (spec-first, agentic execution, human PR review, honest failure logging); the process evidence matters as much as the code.

**In scope:**
- Three sources: GIAS (schools), DfE weekly attendance, DfE Key Stage 4 (GCSE) results.
- Layered dbt project: sources → `stg_` views → `dim_`/`fct_` tables.
- dbt tests: `unique`, `not_null`, `accepted_values`, `relationships` (incl. one clean FK-to-PK).
- 2–3 insight queries (results pasted into README), one of them cross-fact (absence × attainment).
- Streamlit dashboard over the **marts** (never raw), local only + screenshots.
- Optional AI layer (Block 6b) — only after 0–6 done and reviewed.

**Population scope (hybrid):** `dim_school` and `fct_attendance_weekly` keep **all phases** (preserves the dashboard's region × phase contrast and a conformed-dimension-with-different-coverage teaching point). `fct_ks4_results` is **secondary-only by nature** (KS4 = end of Year 11; primaries have no GCSE results). The **cross-fact insight (absence × attainment) is scoped to secondary**, where "secondary" = `phase in ('Secondary', 'All-through')` (all-through schools sit KS4 too).

**Out of scope (non-goals — document, don't build):**
- Production hardening, orchestration/scheduling, CI/CD.
- Incremental models (discuss full-refresh vs incremental in README, don't build).
- Source freshness wiring (CSVs are static snapshots — explain the concept only).
- School-level attendance via the EES API (attendance stays LA-grain; see §2).

## 2. Schema sketch (grain stated for every table — non-negotiable)

**Sources (raw, landed by COPY INTO):** `gias`, `attendance`, `ks4`.

| Model | Layer | Grain | Key | Notes |
|---|---|---|---|---|
| `stg_gias` | staging (view) | school | `urn` | rename/recast GIAS; filter to open schools |
| `stg_attendance` | staging (view) | LA × week × phase | `la_code` + `week_ending_date` + `school_type` | rename/recast DfE weekly attendance (kept per `school_type`/phase) |
| `stg_ks4` | staging (view) | school × academic year | `urn` + `academic_year` | rename/recast KS4 performance |
| `dim_school` | mart (table) | school | `urn` (natural PK) | carries `la_code`, `la_name`, `region`, `phase` as attributes |
| `fct_attendance_weekly` | mart (table) | LA × week × phase | surrogate `md5(la_code‖year‖week‖phase)` | absence measures (attendance keeps phase, so grain includes it) |
| `fct_ks4_results` | mart (table) | school × academic year | surrogate `md5(urn‖academic_year)` | attainment measures |

**Representative measures (exact columns confirmed at ingest):**
- `fct_attendance_weekly`: `sessions_possible`, `sessions_absent`, `pct_overall_absence`, `pct_authorised_absence`, `pct_unauthorised_absence`.
- `fct_ks4_results`: `attainment_8_score`, `pct_grade_5_or_above_eng_maths`, `ebacc_average_point_score`. (Progress 8 dropped — not published for 2024/25; see §7.)

**The grain story (first-class design discussion):**
- GCSE/KS4 is published at **school grain (by URN)** → `fct_ks4_results` joins `dim_school` 1:1 on `urn`: a **textbook FK-to-PK** `relationships` test. `dim_school` does real dimensional work here.
- Attendance is published only at **LA × week** grain → it does **not** attribute to individual schools. `dim_school.la_code` is non-unique (many schools per LA), so `fct_attendance_weekly` → `dim_school` is a **referential check** ("does every LA with attendance data have schools in GIAS?"), not a true FK. This is the accepted weakness of the single-`dim_school` model; analysis by school characteristics requires rolling schools up to LA first.
- **Cross-dataset key risk:** the two DfE datasets may not use identical LA codes (code revisions, name-vs-code joins). The attendance `relationships` test may legitimately fail and reveal a key-alignment issue — we expect this rather than be surprised by it.
- **Different population coverage (sparse fact):** every school has attendance, but only secondaries/all-through have KS4. So `fct_ks4_results` covers a subset of `dim_school` members — correct and expected, not a data gap. Naive "schools with results" counts must not be compared against the full school count without noting this.

## 3. Naming conventions

- **Layering:** `source` (raw) → `stg_<source>` (1:1 with source, **views**, rename/recast/light-clean) → `dim_`/`fct_` (**tables**). The "proper" dbt staging form is `stg_<source>__<entity>` (double underscore); we use the simpler `stg_<source>` since each source has one entity.
- **Columns:** `snake_case`, lowercase. Natural keys keep domain names (`urn`, `la_code`). Dates suffixed `_date`. Booleans prefixed `is_`. Measures named explicitly (`sessions_possible`, `pct_overall_absence`).
- **Surrogate keys:** `md5()` of the concatenated grain columns; tested `unique` + `not_null`. (Avoids a `dbt_utils` dependency; `dbt_utils.generate_surrogate_key` / `unique_combination_of_columns` is the standard alternative.)

## 4. Test expectations

| Model | Column(s) | Test | Why |
|---|---|---|---|
| `stg_gias`, `dim_school` | `urn` | `unique`, `not_null` | the dimension's primary key |
| `dim_school` | `phase` | `accepted_values` | catch bad/unexpected phase values |
| `dim_school` | `la_code` | `not_null` | needed for the attendance join |
| `fct_attendance_weekly` | surrogate key | `unique`, `not_null` | enforce LA × week grain |
| `fct_attendance_weekly` | `la_code` | `relationships` → `dim_school.la_code` | referential check (the weaker one; documented) |
| `fct_ks4_results` | surrogate key | `unique`, `not_null` | enforce school × year grain |
| `fct_ks4_results` | `urn` | `relationships` → `dim_school.urn` | **clean FK-to-PK** |
| `fct_ks4_results` | `attainment_8_score` | `not_null` / range (if practical) | sanity-bound the headline metric |

- **Source freshness:** discussed in README, **not built** (static CSV snapshots).

## 5. Dashboard (Block 6) & optional AI layer (Block 6b)

**Dashboard — Streamlit over the marts only (never the raw schema), local + screenshots:**
- **Headline stat:** one big number — latest-week national overall absence rate.
- **Primary chart:** weekly overall-absence trend, split by **region × phase** (a line/series per region or phase), from `fct_attendance_weekly` joined to `dim_school` attributes (region via LA). All-phase here — this is why we kept attendance broad.
- **Filters (2–3 max):** region, phase, academic year / date range.
- **Optional stretch chart (cut-first if overrunning):** secondary-only, LA-level scatter of overall absence vs Attainment 8 — the cross-fact insight made visual (`fct_attendance_weekly` aggregated to LA × `fct_ks4_results` aggregated to LA).
- Connects with a **read-only** role; no access to the raw schema. Screenshots committed to README **before the Snowflake trial expires**.

**Optional AI layer (Block 6b) — build only after 0–6 are done and reviewed:**
- An "ask a question about attendance" box: natural language → SQL against the **marts** via an LLM call, and/or an auto-generated plain-English summary of the week's trend. Mirrors natural-language data access for non-technical staff.
- **Guardrails (non-negotiable for this block):** validate generated SQL is **read-only** (SELECT only — reject DDL/DML) and **mart-scoped** (only `dim_`/`fct_` tables); **show the generated SQL to the user** alongside results; in the retro, note how you'd review/QA agent-generated queries in a team setting.

## 6. Definition of done (checkable)

- [ ] `dbt build` clean — all tests green (or any failure understood + documented, e.g. the LA-code relationship).
- [ ] Both facts + `dim_school` materialised; grain enforced by surrogate-key uniqueness tests.
- [ ] 2–3 insight query results in README, incl. one cross-fact (absence × attainment), with the one-paragraph pitch at the top.
- [ ] Streamlit dashboard runs locally over the marts; screenshots in README.
- [ ] No credentials, account identifiers, `profiles.yml`, or raw data files in git history.

## 7. Source verification (RESOLVED at ingest — Block 2, Sat 2026-06-06)

All three sources confirmed free, no login. Verified facts the loader depends on:

**GIAS (schools — the dimension):**
- URL is **date-stamped, regenerated daily, old dates 404** → build from today's date, fall back one day on 404:
  `https://ea-edubase-api-prod.azurewebsites.net/edubase/downloads/public/edubasealldata{YYYYMMDD}.csv`
- Encoding **Latin-1 / Windows-1252** (not UTF-8). ~65k rows, 250+ cols, single CSV.
- Columns we use (verbatim): `URN`, `EstablishmentName`, `PhaseOfEducation (name)`, `LA (code)`, `LA (name)`, `EstablishmentStatus (name)`, `GOR (name)` (← region axis, **CONFIRMED present**).
- Grain: one row per establishment; includes closed/proposed → filter `EstablishmentStatus (name) = 'Open'`.

**Attendance (LA-grain fact) — phase split CONFIRMED:**
- EES dataset id `0bad0493-cb82-4312-a21f-5c7570f6eb5e` ("Pupil attendance … weekly").
- API CSV (preferred): `https://api.education.gov.uk/statistics/v1/data-sets/0bad0493-cb82-4312-a21f-5c7570f6eb5e/csv`
- Grain: **LA × week × school_type** (`school_type` = primary / secondary / special, plus a Total row). National/Regional rows also present → filter `geographic_level = 'Local authority'`.
- Columns (verbatim): `time_period`, `time_identifier`, `old_la_code`, `new_la_code`, `la_name`, `school_type`, `possible_sessions`, `overall_absence_perc`, `authorised_absence_perc`, `unauthorised_absence_perc`, `attendance_perc`.

**KS4 (school-grain fact):**
- EES dataset id `5b3d308c-da72-467f-b2ef-ab77d576a455` ("Performance tables schools data", 2024/25).
- API CSV: `https://api.education.gov.uk/statistics/v1/data-sets/5b3d308c-da72-467f-b2ef-ab77d576a455/csv`
- Columns (verbatim): `school_urn`, `school_name`, `time_period`, `attainment8_average`, `gcse_five_engmath_percent`, `ebacc_aps_average`. **`progress8_average` is NOT published for 2024/25** (no KS2 prior attainment for the COVID cohort) → dropped (see §2; future work, last available 2018/19).
- Grain: school × year × demographic breakdown → **must filter to the all-pupils/Total rows or each URN multi-counts** (exact breakdown column names to confirm against the downloaded header).

**Join key (resolved):** GIAS `LA (code)` (3-digit DfE) ↔ attendance `old_la_code` (same 3-digit DfE). EES `new_la_code` is the ONS GSS code (`E09…`) and will NOT join. Cast both to a zero-padded 3-char STRING (leading zeros matter).

**Ingest gotchas (handle in loader/staging):** Latin-1 decode (GIAS); EES suppression markers `c`/`x`/`z`/`low` appear in numeric columns → load as STRING, coerce to NULL in staging; LA-code leading zeros; drop the attendance Total `school_type` row and non-LA `geographic_level` rows; KS4 all-pupils filter; GIAS date-stamped URL.

## 8. Future work (document, don't build)

- **School-level attainment view (earmarked next):** named secondary schools + Attainment 8 / EBacc / %grade-5 in the dashboard. Data already in `dim_school`; KS4 is school-grain. Attainment side only — attendance stays LA-grain.
- **URN crosswalk (predecessor↔successor):** load GIAS linked-URN fields so KS4 results filed under a school's pre-conversion URN follow it to its current open URN — would recover the ~119 "closed-school" KS4 orphans (e.g. St Andrew's Catholic School, Surrey: results under closed URN 125275, current open URN 151611).
- School-level attendance via the EES API (would remove the attendance grain mismatch).
- **Refresh attendance to the latest year:** loaded attendance is 2022/23–2023/24 while KS4 is 2024/25; re-run the loader against the current DfE weekly-attendance dataset so the two facts align (and remove the year-mismatch caveat).
- Incremental materialisation of the facts; source freshness checks.
- An LA-grain conformed dimension (`dim_local_authority`) to give attendance a clean FK too.
