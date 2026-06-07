"""Streamlit dashboard over the school-data marts.

Run:
    .venv/bin/streamlit run app/dashboard.py   # config/keys auto-loaded from .env

Reads via app/db.py — DuckDB (bundled, deployed) or live Snowflake (local dev). Tabbed,
mobile-friendly layout (no sidebar).
"""
import os

import altair as alt
import pandas as pd
import streamlit as st

import ai
import db

st.set_page_config(page_title="England school attendance", layout="wide")

if db.backend() == "duckdb" and not os.path.exists(db.DUCKDB_PATH):
    st.error("No data: set SNOWFLAKE_ACCOUNT in `.env`, or run `python ingest/export_marts.py` "
             "to build app/marts.duckdb.")
    st.stop()


@st.cache_data(ttl=900)
def load_attendance():
    q = """
    with la_region as (
        select la_code, max(region) as region from dim_school group by 1
    )
    select f.academic_year, f.week_label,
           coalesce(r.region, '(unmapped)') as region,
           f.phase, f.pct_overall_absence
    from fct_attendance_weekly f
    left join la_region r on r.la_code = f.la_code
    """
    df = db.query(q)
    df.columns = [c.lower() for c in df.columns]
    df["academic_year"] = df["academic_year"].astype(int)
    df["week_num"] = pd.to_numeric(df["week_label"].str.extract(r"(\d+)")[0], errors="coerce")
    df["year_label"] = df["academic_year"].map(lambda y: f"{y}/{str(y + 1)[2:]}")
    df["period_idx"] = df["academic_year"] * 100 + df["week_num"].fillna(0).astype(int)
    df["period_label"] = df["year_label"] + " W" + df["week_num"].fillna(0).astype(int).map("{:02d}".format)
    return df


@st.cache_data(ttl=900)
def load_la_cross():
    """LA-level secondary absence vs GCSE Attainment 8 (the cross-fact question)."""
    q = """
    with la_absence as (
        select la_code, avg(pct_overall_absence) as avg_absence
        from fct_attendance_weekly where phase = 'Secondary' group by 1
    ),
    la_attain as (
        select d.la_code, max(d.la_name) as la_name, avg(f.attainment8_score) as avg_attainment8
        from fct_ks4_results f
        join dim_school d on d.urn = f.urn
        where d.is_secondary group by 1
    )
    select a.la_code, t.la_name, a.avg_absence, t.avg_attainment8
    from la_absence a join la_attain t on a.la_code = t.la_code
    """
    df = db.query(q)
    df.columns = [c.lower() for c in df.columns]
    return df


@st.cache_data(ttl=900)
def load_schools():
    """School-level KS4 attainment, named from the results data — every school with 2024/25 KS4 results."""
    q = """
    with la_region as (
        select la_name, max(region) as region
        from dim_school where region is not null group by la_name
    )
    select f.urn, f.school_name, f.la_name, lr.region,
           f.attainment8_score, f.pct_grade5_eng_maths, f.ebacc_aps
    from fct_ks4_results f
    left join la_region lr on lr.la_name = f.la_name
    """
    df = db.query(q)
    df.columns = [c.lower() for c in df.columns]
    return df


@st.cache_data(ttl=600, show_spinner=False)
def ai_answer(question):
    sql = ai.generate_sql(question)
    ok, msg = ai.validate_sql(sql)
    rows = db.query(ai.with_limit(sql)) if ok else None
    return sql, ok, msg, rows


df = load_attendance()

st.title("🏫 England school attendance & attainment")
st.caption("Weekly pupil-absence rates and GCSE results, from a Snowflake + dbt star schema. See the repo README.")

tab_ai, tab_att, tab_attain, tab_compare = st.tabs(["💬 Ask", "Attendance", "Attainment", "Compare"])

# ── Ask (AI) ───────────────────────────────────────────────────────────────────
with tab_ai:
    st.subheader("Ask a question")
    if not any(os.environ.get(k) for k in ("GROQ_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")):
        st.info("AI box disabled — set an API key (e.g. `GROQ_API_KEY`) in your `.env` to enable it. See the README.")
    else:
        with st.form("ai_form"):
            q = st.text_input("Ask about attendance or GCSE results",
                              placeholder="e.g. top 5 schools in Surrey by attainment")
            go = st.form_submit_button("Ask")
        if go and q:  # only calls the API on an explicit Ask (and caches by question)
            with st.spinner("Thinking…"):
                try:
                    sql, ok, msg, rows = ai_answer(q)
                    st.code(sql, language="sql")  # always show the generated SQL (transparency)
                    if not ok:
                        st.error(f"Blocked by guardrail: {msg}")
                    else:
                        st.dataframe(rows, use_container_width=True, hide_index=True)
                except Exception as e:
                    emsg = str(e)[:300]
                    for k in ("GROQ_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
                        if os.environ.get(k):
                            emsg = emsg.replace(os.environ[k], "***")
                    st.error(f"Couldn't answer that one: {emsg}")
        st.caption("Natural language → SQL over the marts. The query is validated (SELECT-only, mart-scoped) "
                   "and always shown. Best for ad-hoc exploration; use the other tabs for the curated views.")

# ── Attendance ─────────────────────────────────────────────────────────────────
with tab_att:
    all_regions = sorted(r for r in df["region"].unique() if r != "(unmapped)")
    all_years = sorted(df["year_label"].unique())
    phases = sorted(df["phase"].unique())

    fc1, fc2, fc3 = st.columns(3)  # stack on mobile
    phase = fc1.selectbox("Phase", phases, index=phases.index("Secondary"))
    regions = fc2.multiselect("Regions", all_regions, default=all_regions)
    years = fc3.multiselect("Academic years", all_years, default=all_years)
    regions = regions or all_regions  # empty = all (avoids NaN headline)
    years = years or all_years

    view = df[(df["phase"] == phase) & (df["region"].isin(regions)) & (df["year_label"].isin(years))]

    mean_abs = view["pct_overall_absence"].mean()
    m1, m2, m3 = st.columns(3)
    m1.metric(f"Mean {phase.lower()} absence", f"{mean_abs:.2f}%" if pd.notna(mean_abs) else "—")
    m2.metric("Regions shown", int(view["region"].nunique()))
    m3.metric("Weeks of data", int(view["period_idx"].nunique()))

    st.subheader(f"{phase} absence trend by region")
    trend = (view.groupby(["period_idx", "period_label", "region"], as_index=False)["pct_overall_absence"]
             .mean().rename(columns={"pct_overall_absence": "mean_absence"}))
    st.altair_chart(
        alt.Chart(trend).mark_line(point=True).encode(
            x=alt.X("period_label:N", sort=alt.SortField("period_idx"), title="Week"),
            y=alt.Y("mean_absence:Q", title="Mean overall absence %"),
            color=alt.Color("region:N", title="Region"),
            tooltip=["region", "period_label", alt.Tooltip("mean_absence:Q", format=".2f")],
        ).properties(height=400),
        use_container_width=True,
    )

    st.subheader(f"Mean {phase.lower()} absence by region")
    rank = (view.groupby("region", as_index=False)["pct_overall_absence"].mean()
            .rename(columns={"pct_overall_absence": "mean_absence"}))
    st.altair_chart(
        alt.Chart(rank).mark_bar().encode(
            x=alt.X("mean_absence:Q", title="Mean overall absence %"),
            y=alt.Y("region:N", sort="-x", title=None),
            tooltip=["region", alt.Tooltip("mean_absence:Q", format=".2f")],
        ).properties(height=300),
        use_container_width=True,
    )

# ── Attainment (cross-fact scatter + school table) ─────────────────────────────
with tab_attain:
    st.subheader("Does higher absence mean lower GCSE results? (secondary, by LA)")
    cross = load_la_cross()
    corr = cross["avg_absence"].corr(cross["avg_attainment8"])
    st.metric("Correlation: secondary absence vs Attainment 8", f"{corr:.2f}")
    scatter = alt.Chart(cross).mark_circle(size=70, opacity=0.55).encode(
        x=alt.X("avg_absence:Q", title="Mean secondary absence %", scale=alt.Scale(zero=False)),
        y=alt.Y("avg_attainment8:Q", title="Mean Attainment 8", scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip("la_name:N", title="LA"),
                 alt.Tooltip("avg_absence:Q", format=".2f"),
                 alt.Tooltip("avg_attainment8:Q", format=".1f")],
    )
    trendline = scatter.transform_regression("avg_absence", "avg_attainment8").mark_line(color="red")
    st.altair_chart((scatter + trendline).properties(height=420), use_container_width=True)
    st.caption("Each point = one local authority. Downward red line → more absence, lower attainment. Points well "
               "above the line are selective (grammar-school) boroughs — Sutton, Kingston, Torbay — where academic "
               "selection, not attendance, drives attainment.")

    st.subheader("School-level GCSE attainment (secondary)")
    schools = load_schools()
    query = st.text_input("Search school name", "")
    sv = schools[schools["school_name"].str.contains(query, case=False, na=False)] if query else schools
    sm1, sm2 = st.columns(2)
    sm1.metric("Schools shown", len(sv))
    sm2.metric("Mean Attainment 8", f"{sv['attainment8_score'].mean():.1f}" if len(sv) else "—")
    st.dataframe(
        sv.sort_values("attainment8_score", ascending=False).rename(columns={
            "school_name": "School", "la_name": "LA", "region": "Region",
            "attainment8_score": "Attainment 8", "pct_grade5_eng_maths": "% grade 5+ E&M", "ebacc_aps": "EBacc APS",
        })[["School", "LA", "Region", "Attainment 8", "% grade 5+ E&M", "EBacc APS"]],
        hide_index=True, use_container_width=True, height=420,
    )
    st.caption("Every school with 2024/25 KS4 results, named from the results data; region derived from the LA. "
               "Attainment-only — per-school absence isn't available (LA-grain).")

# ── Compare two schools ────────────────────────────────────────────────────────
with tab_compare:
    st.subheader("Compare two schools")
    comp = load_schools().copy()
    comp["label"] = comp["school_name"].fillna("?") + " — " + comp["la_name"].fillna("?")
    labels = sorted(comp["label"].unique())

    metrics = [("Attainment 8", "attainment8_score", 1),
               ("% grade 5+ E&M", "pct_grade5_eng_maths", 1),
               ("EBacc APS", "ebacc_aps", 2)]

    def fmt(v, dec):
        return "—" if pd.isna(v) else f"{v:.{dec}f}"

    def card(col, row, ref=None):
        region = row["region"] if pd.notna(row["region"]) else "—"
        col.markdown(f"**{row['school_name']}**  \n{row['la_name']} · {region}")
        for label, key, dec in metrics:
            delta = None
            if ref is not None and pd.notna(row[key]) and pd.notna(ref[key]):
                delta = f"{row[key] - ref[key]:+.{dec}f} vs A"
            col.metric(label, fmt(row[key], dec), delta=delta)

    cc1, cc2 = st.columns(2)
    label_a = cc1.selectbox("School A", labels, index=None, placeholder="Search for a school…")
    label_b = cc2.selectbox("School B", labels, index=None, placeholder="Search for a school…")
    if label_a and label_b:
        card(cc1, comp[comp["label"] == label_a].iloc[0])
        card(cc2, comp[comp["label"] == label_b].iloc[0], ref=comp[comp["label"] == label_a].iloc[0])
        st.caption("School B shows the gap vs School A.")
    else:
        st.caption("Pick two schools to compare their 2024/25 GCSE results side by side.")

st.caption(f"Source: DfE marts ({db.backend()} backend). Reads marts only, never raw.")
