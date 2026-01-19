import streamlit as st
import pandas as pd
import duckdb
import os
from langchain_openai import ChatOpenAI

# --- 1. DATA ENGINE (The Foundation) ---
@st.cache_resource
def load_data():
    conn = duckdb.connect(database=':memory:')
    # Load files and clean column names to prevent mapping errors
    for file, table in [("pnl_data.xlsx", "pnl_data"), ("ut_data.xlsx", "ut_data")]:
        if os.path.exists(file):
            df = pd.read_excel(file)
            if 'Month' in df.columns: df['Month'] = pd.to_datetime(df['Month'])
            if 'Date' in df.columns: df['Date'] = pd.to_datetime(df['Date'])
            conn.register(table, df)
    return conn

conn = load_data()

# --- 2. THE SQL ARCHITECT (v20.0) ---
def sql_architect(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    
    # This prompt acts as the "Architect" ensuring Multi-Pass SQL
    architect_prompt = """
    You are a Senior SQL Architect. Your goal is to generate error-proof DuckDB SQL.
    
    CORE RULES FOR COMPLEX QUERIES:
    1. For Ratios (Margin %, C&B %): You MUST use a CTE (WITH clause). 
       - Pass 1: Aggregate Numerator (e.g., C&B_Cost)
       - Pass 2: Aggregate Denominator (e.g., Revenue)
       - Pass 3: Join them and calculate the %
    
    2. DATA MAPPING:
       - Revenue: Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE')
       - C&B Cost: Group3 IN ('C&B - Onsite Total', 'C&B Cost - Offshore') AND Type = 'Cost'
       - Total Cost: Type = 'Cost'
    
    3. NAMING: Output 4 columns: [Dimension, Component_1_Name, Component_2_Name, Result_Percentage].
    
    4. DATE: June 2025 is '2025-06-01'.
    """
    
    try:
        response = llm.invoke(architect_prompt + f"\nUser Request: {user_query}")
        sql = response.content.strip().replace("```sql", "").replace("```", "")
        df = conn.execute(sql).df()
        return "SUCCESS", sql, df
    except Exception as e:
        return "ERROR", None, str(e)

# --- 3. UI ---
st.title("🏛️ L&T Analyst v20.0 (Multi-Agent Architect)")
st.caption("Structured for Complex SQL & CTE execution")

query = st.text_input("Enter your complex financial query:")

if query:
    status, sql, result = sql_architect(query)
    
    if status == "SUCCESS":
        st.success("Calculation Complete")
        
        # Insights & Breakdown
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Result (Avg)", f"{result.iloc[:,-1].mean():,.2f}%")
        
        tab1, tab2 = st.tabs(["📊 Dashboard", "🧾 Architect Logs"])
        with tab1:
            st.dataframe(result, use_container_width=True)
        with tab2:
            st.write("**Architect's SQL Strategy:**")
            st.code(sql, language="sql")
    else:
        st.error(f"Architect encountered an error: {result}")
        st.info("This usually happens if a field name is missing or the date format is unrecognized.")
