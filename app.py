import streamlit as st
import duckdb
import pandas as pd
import os
import json
import hashlib

from agents.architect import ArchitectAgent
from agents.analyst import AnalystAgent
from agents.bi import BIAgent
from agents.validator import ValidationAgent
from utils.logger import log_event
import config

# -------------------------------------------------
# Streamlit Config
# -------------------------------------------------
st.set_page_config(
    page_title="AI Analytics Engine",
    layout="wide"
)

st.title("🤖 Metadata-Driven AI Analytics Platform")

# -------------------------------------------------
# Conversation Memory Helpers
# -------------------------------------------------
def get_last_intent():
    return st.session_state.get("last_intent")


def save_intent(intent):
    st.session_state["last_intent"] = intent


def merge_with_memory(new_intent, last_intent):
    if not last_intent:
        return new_intent

    merged = {
        "kpi_id": new_intent.get("kpi_id") or last_intent.get("kpi_id"),
        "filters": last_intent.get("filters", {}).copy(),
        "comparison": new_intent.get("comparison") or last_intent.get("comparison"),
    }
    merged["filters"].update(new_intent.get("filters", {}))
    return merged


# -------------------------------------------------
# DuckDB Loader
# -------------------------------------------------
@st.cache_resource
def load_duckdb():
    conn = duckdb.connect(database=":memory:")

    pnl_df = pd.read_excel(config.DATA_PATHS["PNL"])
    pnl_df["Month"] = pd.to_datetime(pnl_df["Month"], errors="coerce")
    conn.register("pnl_data", pnl_df)

    ut_df = pd.read_excel(config.DATA_PATHS["UT"])
    ut_df["Date"] = pd.to_datetime(ut_df["Date"], errors="coerce")
    ut_df["Month"] = ut_df["Date"].dt.to_period("M").dt.to_timestamp()
    conn.register("ut_data", ut_df)

    return conn


conn = load_duckdb()

# -------------------------------------------------
# Cached SQL Execution
# -------------------------------------------------
@st.cache_data(show_spinner=False, ttl=config.CACHE_TTL)
def cached_query(sql):
    return conn.execute(sql).df()


# -------------------------------------------------
# Initialize Agents
# -------------------------------------------------
architect = ArchitectAgent(
    kpi_directory_path="metadata/kpi_directory.xlsx",
    prompt_path="prompts/architect_prompt.txt",
    model=config.MODEL_NAME
)

analyst = AnalystAgent()
bi = BIAgent()
validator = ValidationAgent()

# -------------------------------------------------
# Sidebar Context
# -------------------------------------------------
with st.sidebar:
    st.markdown("### 🧠 Current Context")
    if get_last_intent():
        st.json(get_last_intent())
    else:
        st.write("No active context")

# -------------------------------------------------
# UI
# -------------------------------------------------
st.markdown("### Ask a business question")
user_query = st.text_input(
    "",
    placeholder="e.g. Why did margin drop MoM for Transportation?"
)

if user_query:
    try:
        # -----------------------------
        # Architect Agent
        # -----------------------------
        raw_intent = architect.run(user_query)
        intent = merge_with_memory(raw_intent, get_last_intent())
        save_intent(intent)

        log_event("ARCHITECT_INTENT", intent)

        if not intent.get("kpi_id"):
            st.warning("Could not determine KPI.")
            st.stop()

        # -----------------------------
        # Analyst Agent
        # -----------------------------
        sql = analyst.generate_sql(
            kpi_id=intent["kpi_id"],
            filters=intent.get("filters", {}),
            comparison=intent.get("comparison")
        )

        log_event("SQL_GENERATED", {"kpi": intent["kpi_id"], "sql": sql})

        # -----------------------------
        # Execute SQL
        # -----------------------------
        df = cached_query(sql)

        if df.empty:
            st.warning("No data returned.")
            st.stop()

        # -----------------------------
        # Validation
        # -----------------------------
        warnings, errors = validator.validate(
            intent["kpi_id"],
            df,
            intent.get("comparison")
        )

        log_event("VALIDATION", {"warnings": warnings, "errors": errors})

        if errors:
            st.error("❌ Data validation failed")
            for e in errors:
                st.error(e)
            st.stop()

        for w in warnings:
            st.warning(w)

        # -----------------------------
        # Row Safety
        # -----------------------------
        if config.MAX_ROWS and len(df) > config.MAX_ROWS:
            st.warning(
                f"Result truncated to first {config.MAX_ROWS} rows for display."
            )
            df = df.head(config.MAX_ROWS)

        # -----------------------------
        # BI Agent
        # -----------------------------
        bi.render(
            kpi_id=intent["kpi_id"],
            df=df,
            comparison=intent.get("comparison")
        )

        # -----------------------------
        # Audit
        # -----------------------------
        with st.expander("🔍 SQL & Data Audit"):
            st.code(sql, language="sql")
            st.dataframe(df, use_container_width=True)

    except Exception as e:
        log_event("UNHANDLED_ERROR", str(e))
        st.error("⚠️ Something went wrong while processing your request.")
        st.info("The issue has been logged. Please try rephrasing.")
