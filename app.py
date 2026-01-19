import streamlit as st
import pandas as pd
import duckdb
import os
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- 1. DATA ENGINE (Robust DuckDB Foundation) ---
@st.cache_resource
def load_and_configure_db():
    conn = duckdb.connect(database=':memory:')
    
    # Load P&L Data
    if os.path.exists("pnl_data.xlsx"):
        pnl = pd.read_excel("pnl_data.xlsx")
        pnl['Month'] = pd.to_datetime(pnl['Month'])
        conn.register("pnl_data", pnl)
        
    # Load Utilization Data
    if os.path.exists("ut_data.xlsx"):
        ut = pd.read_excel("ut_data.xlsx")
        ut['Date'] = pd.to_datetime(ut['Date'])
        conn.register("ut_data", ut)

    # Load Directories for AI Context
    field_dir = pd.read_excel("field_directory.xlsx").to_string()
    kpi_dir = pd.read_excel("kpi_directory.xlsx").to_string()
    
    return conn, field_dir, kpi_dir

conn, FIELD_CONTEXT, KPI_CONTEXT = load_and_configure_db()

# --- 2. THE MULTI-AGENT FACTORY ---
def execute_complex_analyst(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # STAGE 1: INTENT & MAPPING
    # This ensures the AI knows which columns to use based on your Field Directory
    mapping_prompt = f"""
    Reference these directories:
    FIELDS: {FIELD_CONTEXT}
    KPIs: {KPI_CONTEXT}
    
    User Query: {user_query}
    
    Task: Identify if this requires a Ratio (Margin, C&B%, UT%) or a Sum. 
    If Ratio, identify the Numerator Group and Denominator Group.
    """
    
    # STAGE 2: THE SQL ARCHITECT (Multi-Pass CTE Generation)
    # This is the "Comprehensive Fix" - it forces the AI to use the CTE pattern
    architect_prompt = """
    You are a Senior Financial SQL Architect for DuckDB.
    
    CRITICAL RULE: To calculate ratios (Margin %, C&B %, UT %), you MUST use the following CTE pattern:
    
    WITH 
    Numerator AS (
        SELECT {Dimension}, SUM("Amount in USD") as num_val 
        FROM pnl_data WHERE {Numerator_Filters} GROUP BY 1
    ),
    Denominator AS (
        SELECT {Dimension}, SUM("Amount in USD") as den_val 
        FROM pnl_data WHERE {Denominator_Filters} GROUP BY 1
    )
    SELECT 
        n.{Dimension}, 
        n.num_val as Component_1, 
        d.den_val as Component_2, 
        ((n.num_val - d.den_val)/NULLIF(n.num_val, 0))*100 as Final_Result
    FROM Numerator n
    JOIN Denominator d ON n.{Dimension} = d.{Dimension}
    
    MAPPINGS FROM DIRECTORY:
    - Revenue: Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE')
    - Total Cost: Type = 'Cost'
    - C&B Cost: Group3 IN ('C&B - Onsite Total', 'C&B Cost - Offshore')
    - Utilization: Use ut_data table (TotalBillableHours / NetAvailableHours)
    """

    full_prompt = f"{architect_prompt}\n\nContext:\n{mapping_prompt}\n\nGenerate ONLY the SQL."
    response = llm.invoke(full_prompt)
    sql = response.content.strip().replace("```sql", "").replace("```", "")

    try:
        df = conn.execute(sql).df()
        return "SUCCESS", sql, df
    except Exception as e:
        return "ERROR", sql, str(e)

# --- 3. UI LAYOUT (High-Density Dashboard) ---
st.set_page_config(layout="wide", page_title="L&T Financial Analyst")

st.title("🏛️ L&T Executive Analyst v21.0")
st.markdown("---")

# Question Sidebar (Handling your list of questions)
with st.sidebar:
    st.header("Suggested Queries")
    sample_queries = [
        "Margin % by Account for June 2025",
        "C&B cost as % of revenue by Segment",
        "Utilization % by Exec DG for June",
        "Top 10 Customers by Revenue",
        "FTE Count by Segment"
    ]
    for q in sample_queries:
        if st.button(q):
            st.session_state.current_query = q

query_input = st.text_input("Analyze your data:", key="current_query")

if query_input:
    status, sql, result = execute_complex_analyst(query_input)
    
    if status == "SUCCESS":
        # Metric Row
        res_col = result.columns[-1]
        m1, m2, m3 = st.columns(3)
        m1.metric("Average", f"{result[res_col].mean():,.2f}")
        m2.metric("Maximum", f"{result[res_col].max():,.2f}")
        m3.metric("Minimum", f"{result[res_col].min():,.2f}")

        # Data & Viz Tabs
        tab1, tab2, tab3 = st.tabs(["📊 Performance Chart", "🧾 Data Table", "🛠️ SQL Architect Log"])
        
        with tab1:
            if len(result) > 1:
                fig, ax = plt.subplots(figsize=(10, 4))
                result.plot(kind='bar', x=result.columns[0], y=res_col, ax=ax, color='#00529B')
                plt.xticks(rotation=45)
                st.pyplot(fig)
            else:
                st.info("Single data point returned. Bar chart disabled.")
        
        with tab2:
            st.dataframe(result, use_container_width=True)
            
        with tab3:
            st.info("The Architect used the following logic to solve this:")
            st.code(sql, language="sql")
            
    else:
        st.error(f"Architect Error: {result}")
