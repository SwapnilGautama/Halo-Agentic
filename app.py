import streamlit as st
import pandas as pd
import duckdb
import os
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- 1. DATA INFRASTRUCTURE ---
@st.cache_resource
def setup_engine():
    conn = duckdb.connect(database=':memory:')
    # Load P&L & UT Data
    pnl = pd.read_excel("pnl_data.xlsx")
    pnl['Month'] = pd.to_datetime(pnl['Month'])
    conn.register("pnl_data", pnl)
    
    ut = pd.read_excel("ut_data.xlsx")
    ut['Date'] = pd.to_datetime(ut['Date'])
    conn.register("ut_data", ut)
    
    # Load the "Bible" Directories
    f_dir = pd.read_excel("field_directory.xlsx")
    k_dir = pd.read_excel("kpi_directory.xlsx")
    return conn, f_dir, k_dir

conn, df_fields, df_kpis = setup_engine()

# --- 2. THE THREE AGENTS ---

def run_pipeline(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    
    # AGENT 1: THE ARCHITECT (Logic Mapping)
    # Goal: Identify the exact formula from the Excel directory
    architect_task = f"""
    Reference these directories:
    KPI BIBLE: {df_kpis.to_string()}
    FIELD MAPPING: {df_fields.to_string()}
    
    Question: {user_query}
    
    Task: Identify the 'Formula (Logic)' and the columns needed. 
    If calculating Margin %, you MUST use: ((Revenue - Total_Cost) / Revenue) * 100.
    Output only the logic and fields.
    """
    logic_plan = llm.invoke(architect_task).content

    # AGENT 2: THE ANALYST (SQL Generation)
    # Goal: Convert logic into CTE-based SQL
    analyst_task = f"""
    Using this Logic Plan: {logic_plan}
    
    Write a DuckDB SQL query using CTEs. 
    Example for Margin:
    WITH 
    Rev AS (SELECT Segment, SUM("Amount in USD") as r_val FROM pnl_data WHERE Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE') GROUP BY 1),
    Cost AS (SELECT Segment, SUM("Amount in USD") as c_val FROM pnl_data WHERE Type = 'Cost' GROUP BY 1)
    SELECT Rev.Segment, Rev.r_val as Revenue, Cost.c_val as Total_Cost, ((Rev.r_val - Cost.c_val)/NULLIF(Rev.r_val, 0))*100 as Margin_Perc
    FROM Rev LEFT JOIN Cost ON Rev.Segment = Cost.Segment;
    """
    sql_response = llm.invoke(analyst_task).content
    sql = sql_response.strip().replace("```sql", "").replace("```", "")

    try:
        data = conn.execute(sql).df()
        return "SUCCESS", logic_plan, sql, data
    except Exception as e:
        return "ERROR", logic_plan, sql, str(e)

# --- 3. UI DASHBOARD ---
st.set_page_config(layout="wide", page_title="L&T Agentic Analyst")
st.title("🏛️ L&T Executive Analyst v23.0")
st.markdown("---")

query = st.text_input("What would you like to analyze today?", placeholder="e.g., Margin % by Account for June 2025")

if query:
    status, logic, sql, result = run_pipeline(query)
    
    if status == "SUCCESS":
        # TOP ROW: AGENT 3 (VISUALIZER) INSIGHTS
        metric_col = result.columns[-1]
        val = result[metric_col].mean()
        
        st.subheader("📊 Executive Summary")
        c1, c2 = st.columns([1, 2])
        with c1:
            st.metric(label=f"Average {metric_col}", value=f"{val:,.2f}%")
            st.dataframe(result.head(10))
        with c2:
            fig, ax = plt.subplots(figsize=(10, 5))
            result.plot(kind='bar', x=result.columns[0], y=metric_col, ax=ax, color='#00529B')
            plt.title(f"{metric_col} Analysis")
            st.pyplot(fig)

        # TAB 2: AUDIT & LOGS (Requirement: Formula, SQL, Components)
        st.markdown("---")
        with st.expander("🧾 View Auditor & Calculation Details"):
            t1, t2, t3 = st.tabs(["Formula Used", "SQL Query", "Component Data"])
            with t1:
                st.info(f"**Architect's Logic:**\n{logic}")
            with t2:
                st.code(sql, language="sql")
            with t3:
                st.write("Raw Numerators and Denominators used in calculation:")
                st.dataframe(result)
    else:
        st.error(f"Analysis failed. \n**SQL Error:** {result}")
        st.code(sql)
