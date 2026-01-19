import streamlit as st
import pandas as pd
import duckdb
import os
import re
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- 1. DATA ENGINE (With Pre-Processing) ---
@st.cache_resource
def initialize_engine():
    conn = duckdb.connect(database=':memory:')
    # Load P&L
    pnl = pd.read_excel("pnl_data.xlsx")
    pnl['Month'] = pd.to_datetime(pnl['Month'])
    # Ensure all column names are stripped of whitespace
    pnl.columns = [c.strip() for c in pnl.columns]
    conn.register("pnl_data", pnl)
    
    # Load UT
    ut = pd.read_excel("ut_data.xlsx")
    ut['Date'] = pd.to_datetime(ut['Date'])
    ut.columns = [c.strip() for c in ut.columns]
    conn.register("ut_data", ut)
    
    # Load Directories as reference "Bibles"
    field_dir = pd.read_excel("field_directory.xlsx").to_string()
    kpi_dir = pd.read_excel("kpi_directory.xlsx").to_string()
    return conn, field_dir, kpi_dir

conn, FIELD_BIBLE, KPI_BIBLE = initialize_engine()

# --- 2. THE IMPROVED ANALYST PIPELINE ---

def clean_sql_output(raw_text):
    """Removes 'Certainly', 'To...', and markdown backticks."""
    # Remove markdown blocks
    clean = re.sub(r"```sql|```", "", raw_text).strip()
    # Force start at the first SQL keyword
    start_match = re.search(r"\b(WITH|SELECT)\b", clean, re.IGNORECASE)
    if start_match:
        clean = clean[start_match.start():]
    return clean

def run_agent_v26(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # AGENT 1: THE ARCHITECT (Logic & Field Selection)
    architect_prompt = f"""
    Use these Bibles:
    FIELDS: {FIELD_BIBLE}
    KPIs: {KPI_BIBLE}
    
    TASK: Identify logic for: "{user_query}"
    RULES:
    1. If query is about Industry/Vertical/Business Unit, you MUST use the column 'Segment'.
    2. For Margin %, use logic: ((Revenue - Total_Cost) / Revenue) * 100.
    """
    logic_plan = llm.invoke(architect_prompt).content

    # AGENT 2: THE IMPROVED ANALYST (SQL Generation)
    analyst_prompt = f"""
    PLAN: {logic_plan}
    
    Write DuckDB SQL. RULES:
    1. NO CONVERSATION. Start immediately with 'WITH' or 'SELECT'.
    2. Do NOT say 'To' or 'Certainly'. 
    3. Use 'Month' for pnl_data dates (format: '2025-06-01').
    4. For Margin % < 30:
       - CTE 1 (Rev): SUM Amount WHERE Type='Revenue' AND Group1 IN ('ONSITE','OFFSHORE','INDIRECT REVENUE')
       - CTE 2 (Cost): SUM Amount WHERE Type='Cost'
       - Final SELECT: Join on Segment or FinalCustomerName and filter WHERE Margin_Perc < 30.
    """
    sql_response = llm.invoke(analyst_prompt).content
    final_sql = clean_sql_output(sql_response)

    try:
        df = conn.execute(final_sql).df()
        return "SUCCESS", logic_plan, final_sql, df
    except Exception as e:
        return "ERROR", logic_plan, final_sql, str(e)

# --- 3. UI DASHBOARD ---
st.set_page_config(layout="wide", page_title="L&T v26.0")
st.title("🏛️ L&T Executive Analyst v26.0")
st.caption("Improved Logic Isolation & Field Mapping")

user_q = st.text_input("Ask a question (e.g., Segments with Margin % < 30 in Q2 2025):")

if user_q:
    status, logic, sql, result = run_agent_v26(user_q)
    
    if status == "SUCCESS":
        st.subheader("📊 Results")
        col1, col2 = st.columns([1, 2])
        with col1:
            st.dataframe(result, use_container_width=True)
        with col2:
            if not result.empty:
                val_col = result.columns[-1]
                fig, ax = plt.subplots(figsize=(8, 4))
                result.plot(kind='barh', x=result.columns[0], y=val_col, ax=ax, color='#E63946')
                st.pyplot(fig)

        # TABBED AUDIT LOG (As requested)
        st.markdown("---")
        with st.expander("🧾 Open Calculation Audit Log"):
            t1, t2, t3 = st.tabs(["Formula Logic", "SQL Query", "Raw Components"])
            with t1:
                st.info(logic)
            with t2:
                st.code(sql, language="sql")
            with t3:
                st.write("Numerator/Denominator Table:")
                st.dataframe(result)
    else:
        st.error(f"Execution Error: {result}")
        st.code(sql)
