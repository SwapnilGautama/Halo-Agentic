import streamlit as st
import pandas as pd
import duckdb
import os
import re
from langchain_openai import ChatOpenAI

# --- 1. DATA ENGINE ---
@st.cache_resource
def load_and_init():
    conn = duckdb.connect(database=':memory:')
    # Load and force standard naming/types
    pnl = pd.read_excel("pnl_data.xlsx")
    pnl['Month'] = pd.to_datetime(pnl['Month'])
    conn.register("pnl_data", pnl)
    
    ut = pd.read_excel("ut_data.xlsx")
    ut['Date'] = pd.to_datetime(ut['Date'])
    conn.register("ut_data", ut)
    
    # Load Directories
    f_dir = pd.read_excel("field_directory.xlsx")
    k_dir = pd.read_excel("kpi_directory.xlsx")
    return conn, f_dir, k_dir

conn, df_fields, df_kpis = load_and_init()

# --- 2. THE CONTRACTOR PIPELINE ---

def run_contractor_query(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    
    # STEP 1: THE ARCHITECT (Validates Fields & Formulas)
    # Explicitly telling the AI to look for 'Segment'
    architect_task = f"""
    You are a Data Architect. Use these directories:
    KPIs: {df_kpis.to_string()}
    FIELDS: {df_fields.to_string()}
    
    Identify the following for the query: "{user_query}"
    1. Table Name(s)
    2. Column for Grouping (Check for 'Segment', 'FinalCustomerName', etc.)
    3. Formula Logic: If Margin %, use ((Revenue - Cost)/Revenue)*100.
    4. Filters: Identify 'Type' and 'Group1' requirements.
    """
    logic_plan = llm.invoke(architect_task).content

    # STEP 2: THE ANALYST (SQL Generation with Mandatory CTE)
    analyst_task = f"""
    Based on this Logic: {logic_plan}
    
    Generate DuckDB SQL. You MUST follow these rules:
    - Use the 'Month' column for dates in pnl_data.
    - Use the 'Segment' column if the user mentions Industry, Vertical, or Segment.
    - FOR RATIOS (Margin, C&B): You MUST use two CTEs (RevCTE and CostCTE) and JOIN them.
    - FILTERING: If the user asks for "less than 30%", put the filter in the FINAL SELECT.
    
    MANDATORY STRUCTURE:
    WITH Rev AS (SELECT {{Dim}}, SUM("Amount in USD") as r FROM pnl_data WHERE Type='Revenue' AND {{Filters}} GROUP BY 1),
         Cost AS (SELECT {{Dim}}, SUM("Amount in USD") as c FROM pnl_data WHERE Type='Cost' GROUP BY 1)
    SELECT Rev.{{Dim}}, ((Rev.r - Cost.c)/NULLIF(Rev.r, 0))*100 as Margin_Perc
    FROM Rev LEFT JOIN Cost ON Rev.{{Dim}} = Cost.{{Dim}}
    WHERE Margin_Perc < 30;
    """
    
    sql_raw = llm.invoke(analyst_task).content
    sql = re.sub(r"```sql|```", "", sql_raw).strip()
    sql = re.sub(r"^.*?(WITH|SELECT)", r"\1", sql, flags=re.DOTALL | re.IGNORECASE)

    try:
        df = conn.execute(sql).df()
        return "SUCCESS", logic_plan, sql, df
    except Exception as e:
        return "ERROR", logic_plan, sql, str(e)

# --- 3. UI DASHBOARD ---
st.set_page_config(layout="wide")
st.title("🏛️ L&T Executive Analyst v25.0")

q = st.text_input("Query:", placeholder="e.g., Accounts with Margin % < 30 in June 2025")

if q:
    status, logic, sql, result = run_contractor_query(q)
    
    if status == "SUCCESS":
        st.subheader("Results")
        st.dataframe(result, use_container_width=True)
        
        # AUDIT TAB
        with st.expander("🔍 Auditor & Calculation Details"):
            t1, t2 = st.tabs(["Logic Plan", "SQL Generated"])
            with t1:
                st.write(logic)
            with t2:
                st.code(sql, language="sql")
    else:
        st.error(f"Error: {result}")
        st.code(sql)
