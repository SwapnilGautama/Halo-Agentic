import streamlit as st
import pandas as pd
import duckdb
import os
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- 1. DATA ENGINE ---
@st.cache_resource
def load_and_register_data():
    conn = duckdb.connect(database=':memory:')
    
    # Load P&L (Strict Column Alignment)
    if os.path.exists("pnl_data.xlsx"):
        df_pnl = pd.read_excel("pnl_data.xlsx")
        df_pnl['Month'] = pd.to_datetime(df_pnl['Month'], errors='coerce')
        conn.register("pnl_data", df_pnl)

    # Load UT (Strict Column Alignment)
    if os.path.exists("ut_data.xlsx"):
        df_ut = pd.read_excel("ut_data.xlsx")
        df_ut['Date'] = pd.to_datetime(df_ut['Date'], errors='coerce')
        conn.register("ut_data", df_ut)

    return conn

conn = load_and_register_data()

# --- 2. THE ANALYST (Aligned to KPI Directory) ---
def run_analyst(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    system_prompt = """
    You are a Financial Data Analyst.
    TABLES:
    - pnl_data: Columns [Month, FinalCustomerName, "Amount in USD", Type, Group1, Group3]
    - ut_data: Columns [Date, FinalCustomerName, PSNo, TotalBillableHours, NetAvailableHours]

    JOIN MANDATE:
    For any KPI involving BOTH tables (RPP, Billed Rate, Realized Rate), you MUST JOIN on:
    pnl_data.FinalCustomerName = ut_data.FinalCustomerName 
    AND STRFTIME(pnl_data.Month, '%Y-%m') = STRFTIME(ut_data.Date, '%Y-%m')

    KPI REFRESHER:
    - Revenue: SUM("Amount in USD") WHERE Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE')
    - C&B Cost: SUM("Amount in USD") WHERE Type = 'Cost' AND Group3 LIKE '%C&B%'
    - Headcount: COUNT(DISTINCT PSNo)

    OUTPUT FORMAT:
    Select the Dimension, then the Numerator, then the Denominator, then the Final_Result.
    Return ONLY the SQL.
    """
    
    sql = llm.invoke(system_prompt + f"\nUser Query: {user_query}").content.strip().replace("```sql", "").replace("```", "")
    
    try:
        df = conn.execute(sql).df()
        return sql, df
    except Exception as e:
        return sql, f"SQL Error: {str(e)}"

# --- 3. UI ---
st.set_page_config(layout="wide")
st.title("🏛️ L&T Executive Analyst v10.0")

user_input = st.text_input("Query (e.g., 'What is the Billed Rate trend for A1?')")

if user_input:
    sql, result = run_analyst(user_input)
    
    if isinstance(result, pd.DataFrame):
        tab1, tab2 = st.tabs(["📊 Dashboard", "🧾 Calculation Details"])
        
        with tab1:
            st.dataframe(result.iloc[:, [0, -1]]) # Shows Date/Customer and the KPI result
            if len(result) > 1:
                fig, ax = plt.subplots(figsize=(10, 4))
                ax.plot(result.iloc[:, 0].astype(str), result.iloc[:, -1], marker='o')
                st.pyplot(fig)

        with tab2:
            st.markdown("### 🔍 Calculation Audit")
            st.write("Full breakdown including Numerator and Denominator:")
            st.dataframe(result)
            st.write("**Generated SQL:**")
            st.code(sql, language='sql')
    else:
        st.error(result)
