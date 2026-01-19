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
# Conversation Memory Helpers
# -------------------------------------------------
def get_last_intent():
    return st.session_state.get("last_intent")


def save_intent(intent):
    st.session_state["last_intent"] = intent


def merge_with_memory(new_intent, last_intent):
    """
    Merge new intent with previous intent.
    Rules:
    - New values override old ones
    - Missing values inherit from memory
    """
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
# Sidebar: Current Context (Conversation Memory)
# -------------------------------------------------
with st.sidebar:
    st.markdown("### 🧠 Current Context")
    if get_last_intent():
        st.json(get_last_intent())
    else:
        st.write("No active context yet")

# -------------------------------------------------
# Main UI
# -------------------------------------------------
st.markdown("### Ask a business question")
user_query = st.text_input(
    "",
    placeholder="e.g. Why did margin drop MoM for Transportation?"
)

if user_query:

    # ---------------------------------------------
    # 1. ARCHITECT AGENT (NL → Partial Intent)
    # ---------------------------------------------
    with st.spinner("🧠 Understanding your question..."):
        raw_intent = architect.run(user_query)

    # ---------------------------------------------
    # 2. MERGE WITH CONVERSATION MEMORY
    # ---------------------------------------------
    last_intent = get_last_intent()
    intent = merge_with_memory(raw_intent, last_intent)
    save_intent(intent)

    if not intent or not intent.get("kpi_id"):
        st.warning("Could not determine KPI. Please rephrase.")
        st.stop()

    # ---------------------------------------------
    # 3. ANALYST AGENT (SQL GENERATION)
    # ---------------------------------------------
    with st.spinner("📊 Generating SQL..."):
        sql = analyst.generate_sql(
            kpi_id=intent["kpi_id"],
            filters=intent.get("filters", {}),
            comparison=intent.get("comparison")
        )

    # ---------------------------------------------
    # 4. SQL EXECUTION
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
    # 5. VALIDATION AGENT
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
    # 6. BI AGENT (VISUALS + INSIGHTS)
    # ---------------------------------------------
    with st.spinner("📈 Building visuals and insights..."):
        bi.render(
            kpi_id=intent["kpi_id"],
            df=df,
            comparison=intent.get("comparison")
        )

    # ---------------------------------------------
    # 7. SQL & DATA AUDIT
    # ---------------------------------------------
    with st.expander("🔍 SQL Audit & Raw Output"):
        st.code(sql, language="sql")
        st.dataframe(df, use_container_width=True)
