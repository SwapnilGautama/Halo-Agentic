import streamlit as st
import pandas as pd
import duckdb
import os
import re
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- 1. THE BIBLE (Context Loading) ---
@st.cache_resource
def setup_system():
    conn = duckdb.connect(database=':memory:')
    # Load Tables
    for f, t in [("pnl_data.xlsx", "pnl_data"), ("ut_data.xlsx", "ut_data")]:
        df = pd.read_excel(f)
        if 'Month' in df.columns: df['Month'] = pd.to_datetime(df['Month'])
        if 'Date' in df.columns: df['Date'] = pd.to_datetime(df['Date'])
        conn.register(t, df)
    
    # Load Directories
    f_dir = pd.read_excel("field_directory.xlsx").to_string()
    k_dir = pd.read_excel("kpi_directory.xlsx").to_string()
    return conn, f_dir, k_dir

conn, FIELD_BIBLE, KPI_BIBLE = setup_system()

# --- 2. THE MULTI-AGENT ANALYST ---
def solve_query(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    
    # AGENT 1: ARCHITECT (Mapping Formula & Fields)
    architect_prompt = f"""
    You are a Financial Architect. Use the following Bibles to define the logic.
    FIELD BIBLE: {FIELD_BIBLE}
    KPI BIBLE: {KPI_BIBLE}
    
    USER QUERY: {user_query}
    
    TASK: Output the Formula, the Numerator filter, and the Denominator filter.
    Example: Margin % = ((Rev - Cost)/Rev)*100. Rev: Group1 in (ONSITE, OFFSHORE). Cost: Type='Cost'.
    """
    logic_plan = llm.invoke(architect_prompt).content

    # AGENT 2: ANALYST (Writing Clean SQL)
    analyst_prompt = f"""
    Logic Plan: {logic_plan}
    
    Write a DuckDB SQL query using CTEs. 
    1. Only output the SQL code. NO INTRO, NO EXPLANATION, NO "Certainly".
    2. P&L date column is 'Month'. UT date column is 'Date'.
    3. For June 2025, use: Month = '2025-06-01'
    
    STRICT TEMPLATE FOR RATIOS:
    WITH 
    Numerator AS (SELECT {{Dimension}}, SUM("Amount in USD") as n_val FROM pnl_data WHERE {{Filters}} GROUP BY 1),
    Denominator AS (SELECT {{Dimension}}, SUM("Amount in USD") as d_val FROM pnl_data WHERE {{Filters}} GROUP BY 1)
    SELECT n.{{Dimension}}, n.n_val as Numerator, d.d_val as Denominator, 
    ((n.n_val - d.d_val)/NULLIF(n.n_val, 0))*100 as Result_Perc
    FROM Numerator n JOIN Denominator d ON n.{{Dimension}} = d.{{Dimension}}
    """
    sql_raw = llm.invoke(analyst_prompt).content
    # Clean SQL: Remove markdown and conversational noise
    sql = re.sub(r"```sql|```", "", sql_raw).strip()
    # Remove any text before the first 'WITH' or 'SELECT'
    sql = re.sub(r"^.*?(WITH|SELECT)", r"\1", sql, flags=re.DOTALL | re.IGNORECASE)

    try:
        df = conn.execute(sql).df()
        return "SUCCESS", logic_plan, sql, df
    except Exception as e:
        return "ERROR", logic_plan, sql, str(e)

# --- 3. THE INTERFACE ---
st.set_page_config(layout="wide")
st.title("🏛️ L&T Executive Analyst v24.0")

q = st.text_input("Run a complex query (e.g., Margin % by Account for June 2025):")

if q:
    status, logic, sql, df = solve_query(q)
    
    if status == "SUCCESS":
        st.subheader("📊 Results & Insights")
        metric_col = df.columns[-1]
        
        c1, c2 = st.columns([1, 2])
        with c1:
            st.metric("Group Average", f"{df[metric_col].mean():,.2f}%")
            st.dataframe(df, use_container_width=True)
        with c2:
            fig, ax = plt.subplots(figsize=(10, 5))
            df.plot(kind='bar', x=df.columns[0], y=metric_col, ax=ax, color='#00529B')
            st.pyplot(fig)
            
        # THE AUDIT TAB (Your Requirement)
        st.markdown("---")
        with st.expander("🧾 Auditor Log (Formula, SQL, & Components)"):
            tab_f, tab_s, tab_c = st.tabs(["Formula Details", "Generated SQL", "Calculation Components"])
            with tab_f:
                st.write("**Architect Logic:**")
                st.info(logic)
            with tab_s:
                st.code(sql, language="sql")
            with tab_c:
                st.write("Raw data used for Numerator and Denominator:")
                st.dataframe(df)
    else:
        st.error(f"Execution Error: {df}")
        st.code(sql)
