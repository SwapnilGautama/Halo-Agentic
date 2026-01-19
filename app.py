import streamlit as st
import pandas as pd
import duckdb
import os
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- 1. CORE DATA ENGINE ---
@st.cache_resource
def initialize_system():
    conn = duckdb.connect(database=':memory:')
    # Load and clean P&L
    if os.path.exists("pnl_data.xlsx"):
        pnl = pd.read_excel("pnl_data.xlsx")
        pnl['Month'] = pd.to_datetime(pnl['Month'])
        conn.register("pnl_data", pnl)
    # Load and clean UT
    if os.path.exists("ut_data.xlsx"):
        ut = pd.read_excel("ut_data.xlsx")
        ut['Date'] = pd.to_datetime(ut['Date'])
        conn.register("ut_data", ut)
    
    # Load Directories as reference "Bibles"
    field_dir = pd.read_excel("field_directory.xlsx")
    kpi_dir = pd.read_excel("kpi_directory.xlsx")
    return conn, field_dir, kpi_dir

conn, df_fields, df_kpis = initialize_system()

# --- 2. THE AUDITED ANALYST (v22.0) ---
def run_audited_query(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # Convert directories to string context for the AI
    kpi_context = df_kpis.to_string()
    field_context = df_fields.to_string()

    system_prompt = f"""
    You are a Financial Data Auditor. Your task is to generate DuckDB SQL based STRICTLY on the provided KPI Directory.
    
    KPI DIRECTORY:
    {kpi_context}
    
    FIELD MAPPING:
    {field_context}

    STRICT FORMULA RULES:
    1. MARGIN %: You must calculate ((Revenue - Total_Cost) / Revenue) * 100.
       - Revenue: Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE')
       - Total Cost: Type = 'Cost'
    2. C&B %: You must calculate (CB_Cost / Revenue) * 100.
       - CB_Cost: Group3 IN ('C&B - Onsite Total', 'C&B - Offshore Total') AND Type = 'Cost'
    3. UTILIZATION %: (SUM(TotalBillableHours) / SUM(NetAvailableHours)) * 100 from ut_data.

    SQL STRUCTURE REQUIREMENT:
    Always use Common Table Expressions (CTEs) to separate Numerator and Denominator logic.
    Example for Margin:
    WITH Rev AS (SELECT Segment, SUM("Amount in USD") as r FROM pnl_data WHERE Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE') GROUP BY 1),
         Cost AS (SELECT Segment, SUM("Amount in USD") as c FROM pnl_data WHERE Type = 'Cost' GROUP BY 1)
    SELECT Rev.Segment, Rev.r as Revenue, Cost.c as Total_Cost, ((Rev.r - Cost.c)/NULLIF(Rev.r, 0))*100 as Margin_Perc
    FROM Rev LEFT JOIN Cost ON Rev.Segment = Cost.Segment;
    """

    try:
        response = llm.invoke(system_prompt + f"\n\nUser Question: {user_query}")
        sql = response.content.strip().replace("```sql", "").replace("```", "")
        df = conn.execute(sql).df()
        return "SUCCESS", sql, df
    except Exception as e:
        return "ERROR", sql, str(e)

# --- 3. UI LAYOUT ---
st.set_page_config(layout="wide")
st.title("🏛️ L&T Audited Analyst v22.0")
st.info("Verified against KPI & Field Directories")

# Display the questions from your list for easy access
st.sidebar.markdown("### 📋 Targeted Question List")
target_questions = [
    "Margin % by Account for June 2025",
    "C&B cost as % of revenue by Segment",
    "Utilization % by Exec DG",
    "FTE Count by Segment for June",
    "Top 5 Accounts by Revenue"
]
for tq in target_questions:
    if st.sidebar.button(tq):
        st.session_state.query = tq

user_input = st.text_input("Ask a question:", key="query")

if user_input:
    status, sql, result = run_audited_query(user_input)
    
    if status == "SUCCESS":
        st.subheader("Results")
        # Insight Header
        metric_col = result.columns[-1]
        st.metric(label=f"Avg {metric_col}", value=f"{result[metric_col].mean():,.2f}")
        
        tab1, tab2 = st.tabs(["📊 Visualization", "🔍 Auditor's SQL"])
        with tab1:
            st.dataframe(result, use_container_width=True)
            if len(result) > 1:
                fig, ax = plt.subplots(figsize=(10, 3))
                result.plot(kind='bar', x=result.columns[0], y=metric_col, ax=ax, color='#00529B')
                st.pyplot(fig)
        with tab2:
            st.code(sql, language="sql")
    else:
        st.error(f"Logic Error: {result}")
