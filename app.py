import streamlit as st
import pandas as pd
import duckdb
import os
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- 1. DATA ENGINE (The "Standardizer") ---
@st.cache_resource
def load_and_clean_data():
    conn = duckdb.connect(database=':memory:')
    
    # Process PNL Data
    if os.path.exists("pnl_data.xlsx"):
        df_pnl = pd.read_excel("pnl_data.xlsx")
        df_pnl.columns = [c.strip() for c in df_pnl.columns]
        
        # KEY FIX: Standardizing the names the AI expects
        df_pnl = df_pnl.rename(columns={
            'Amount in USD': 'USD_Amount', 
            'FinalCustomerName': 'Customer',
            'Month': 'Period'
        })
        df_pnl['Period'] = pd.to_datetime(df_pnl['Period'], errors='coerce')
        conn.register("pnl_data", df_pnl)

    # Process UT Data
    if os.path.exists("ut_data.xlsx"):
        df_ut = pd.read_excel("ut_data.xlsx")
        df_ut.columns = [c.strip() for c in df_ut.columns]
        
        # KEY FIX: Standardizing for UT table
        df_ut = df_ut.rename(columns={
            'Date': 'Period', 
            'Date_a': 'Period', # Catches both variations
            'FinalCustomerName': 'Customer'
        })
        df_ut['Period'] = pd.to_datetime(df_ut['Period'], errors='coerce')
        conn.register("ut_data", df_ut)

    return conn

conn = load_and_clean_data()

# --- 2. AI ARCHITECT (With Forced Logic) ---
def execute_query(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    system_prompt = f"""
    You are a Financial Data Analyst. 
    TABLES AVAILABLE:
    - pnl_data: [Period, Customer, USD_Amount, Type, Group1, Group2, Group3]
    - ut_data: [Period, Customer, PSNo, Status, TotalBillableHours, NetAvailableHours]

    KPI RULES:
    - Revenue: SUM(USD_Amount) FILTER (WHERE Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE'))
    - Total Cost: SUM(USD_Amount) FILTER (WHERE Type = 'Cost')
    - C&B Cost: SUM(USD_Amount) FILTER (WHERE Type = 'Cost' AND Group3 LIKE '%C&B%')
    - Margin %: ((Revenue - Total_Cost) / NULLIF(Revenue, 0)) * 100

    SQL RULES:
    - Always JOIN on Customer AND Month: 
      pnl_data.Customer = ut_data.Customer AND STRFTIME(pnl_data.Period, '%Y-%m') = STRFTIME(ut_data.Period, '%Y-%m')
    - Output ONLY the DuckDB SQL query.
    """
    
    response = llm.invoke(system_prompt + f"\nUser Query: {user_query}")
    sql = response.content.strip().replace("```sql", "").replace("```", "")
    
    try:
        df = conn.execute(sql).df()
        return sql, df
    except Exception as e:
        return sql, f"SQL Error: {str(e)}"

# --- 3. THE INTERFACE ---
st.set_page_config(layout="wide")
st.title("🏛️ L&T Executive Analyst v7.0")

user_input = st.text_input("Ask a question (e.g., 'What is the C&B cost as % of revenue trend?')")

if user_input:
    sql, result = execute_query(user_input)
    
    if isinstance(result, pd.DataFrame):
        if result.empty:
            st.warning("Query returned no data. Check if names/dates match in both files.")
        else:
            st.write("### Analysis Result")
            st.dataframe(result)
            
            # Auto-charting logic
            if len(result.columns) >= 2:
                fig, ax = plt.subplots(figsize=(10, 4))
                ax.plot(result.iloc[:, 0].astype(str), result.iloc[:, -1], marker='o')
                plt.xticks(rotation=45)
                st.pyplot(fig)
    else:
        st.error(result)
        st.info("Technical SQL generated:")
        st.code(sql)
