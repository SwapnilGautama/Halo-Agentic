import streamlit as st
import duckdb
import pandas as pd
import os

from agents.architect import ArchitectAgent
from agents.analyst import AnalystAgent
from agents.bi import BIAgent
from agents.validator import ValidationAgent

# -------------------------------------------------
# Streamlit Config
# -------------------------------------------------
st.set_page_config(
    page_title="AI Analytics Engine",
    layout="wide"
)

st.title("🤖 Metadata-Driven AI Analytics Platform")

# -------------------------------------------------
# Load Data into DuckDB
# -------------------------------------------------
@st.cache_resource
def load_duckdb():
    conn = duckdb.connect(database=":memory:")

    pnl_path = "data/pnl_data.xlsx"
    ut_path = "data/ut_data.xlsx"

    if os.path.exists(pnl_path):
        pnl_df = pd.read_excel(pnl_path)
        pnl_df["Month"] = pd.to_datetime(pnl_df["Month"], errors="coerce")
        conn.register("pnl_data", pnl_df)

    if os.path.exists(ut_path):
        ut_df = pd.read_excel(ut_path)
        ut_df["Date"] = pd.to_datetime(ut_df["Date"], errors="coerce")
        ut_df["Month"] = ut_df["Date"].dt.to_period("M").dt.to_timestamp()
        conn.register("ut_data", ut_df)

    return conn


conn = load_duckdb()

# -------------------------------------------------
# Initialize Agents
# -------------------------------------------------
architect = ArchitectAgent(
    kpi_directory_path="metadata/kpi_directory.xlsx",
    prompt_path="prompts/architect_prompt.txt",
    model="gpt-4o"
)

analyst = AnalystAgent()
bi = BIAgent()
validator = ValidationAgent()

# -------------------------------------------------
# UI
# -------------------------------------------------
st.markdown("### Ask a business question")
user_query = st.text_input(
    "",
    placeholder="e.g. Why did margin drop MoM for Transportation?"
)

if user_query:

    # ---------------------------------------------
    # 1. ARCHITECT AGENT
    # ---------------------------------------------
    with st.spinner("🧠 Understanding your question..."):
        intent = architect.run(user_query)

    if not intent or not intent.get("kpi_id"):
        st.warning("Could not determine KPI. Please rephrase your question.")
        st.stop()

    # ---------------------------------------------
    # 2. ANALYST AGENT (SQL GENERATION)
    # ---------------------------------------------
    with st.spinner("📊 Generating SQL..."):
        sql = analyst.generate_sql(
            kpi_id=intent["kpi_id"],
            filters=intent.get("filters", {}),
            comparison=intent.get("comparison")
        )

    # ---------------------------------------------
    # 3. SQL EXECUTION
    # ---------------------------------------------
    try:
        df = conn.execute(sql).df()
    except Exception as e:
        st.error("❌ SQL execution failed")
        st.code(sql, language="sql")
        st.exception(e)
        st.stop()

    if df.empty:
        st.warning("No data returned for this query.")
        st.code(sql, language="sql")
        st.stop()

    # ---------------------------------------------
    # 4. VALIDATION AGENT
    # ---------------------------------------------
    warnings, errors = validator.validate(
        kpi_id=intent["kpi_id"],
        df=df,
        comparison=intent.get("comparison")
    )

    if errors:
        st.error("❌ Data validation failed")
        for err in errors:
            st.error(err)

        with st.expander("🔍 SQL Audit"):
            st.code(sql, language="sql")
            st.dataframe(df, use_container_width=True)

        st.stop()

    if warnings:
        st.warning("⚠️ Data quality warnings detected")
        for warn in warnings:
            st.warning(warn)

    # ---------------------------------------------
    # 5. BI AGENT (VISUALS + INSIGHTS)
    # ---------------------------------------------
    with st.spinner("📈 Building visuals and insights..."):
        bi.render(
            kpi_id=intent["kpi_id"],
            df=df,
            comparison=intent.get("comparison")
        )

    # ---------------------------------------------
    # DEBUG / AUDIT SECTION
    # ---------------------------------------------
    with st.expander("🔍 SQL Audit & Raw Output"):
        st.code(sql, language="sql")
        st.dataframe(df, use_container_width=True)
