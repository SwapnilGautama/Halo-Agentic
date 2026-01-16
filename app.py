import streamlit as st
import pandas as pd
import duckdb
import os
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- 1. THE DATA REPAIR SHOP (Now with even stricter standardization) ---
@st.cache_resource
def load_and_clean_data():
    conn = duckdb.connect(database=':memory:')
    
    # Process PNL Data
    if os.path.exists("pnl_data.xlsx"):
        df_pnl = pd.read_excel("pnl_data.xlsx")
        df_pnl.columns = [c.strip() for c in df_pnl.columns]
        # Force the names to match our AI's "Internal Dictionary"
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
        # Force the names to match our AI's "Internal Dictionary"
        df_ut = df_ut.rename(columns={
            'Date': 'Period', 
            'FinalCustomerName': 'Customer'
        })
        # If your file still uses 'Date_a', this line catches it:
        if 'Date_a' in df_ut.columns: df_ut = df_ut.rename(columns={'Date_a': 'Period'})
        
        df_ut['Period'] = pd.to_datetime(df_ut['Period'], errors='coerce')
        conn.register("ut_data", df_ut)

    return conn

conn = load_and_clean_data()

# --- 2. THE ARCHITECT AGENT (With fixed nomenclature) ---
def execute_query(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # We tell the AI EXACTLY what we renamed the columns to above
    system_prompt = f"""
    You are a Financial Data Expert. Use these internal table schemas:
    
    TABLE: pnl_data
    Columns: [Period, Customer, USD_Amount, Type, Group1, Group2, Group3]
    
    TABLE: ut_data
    Columns: [Period, Customer, PSNo, Status, TotalBillableHours, NetAvailableHours]

    BUSINESS LOGIC RULES:
    1. Revenue: SUM(USD_Amount) FILTER (WHERE Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE'))
    2. C&B Cost: SUM(USD_Amount) FILTER (WHERE Type = 'Cost' AND Group3 IN ('C&B - Onsite Total', 'C&B - Offshore Total'))
    3. Margin %: ((Revenue - SUM(USD_Amount) FILTER (WHERE Type = 'Cost')) / NULLIF(Revenue, 0)) * 100
    
    JOIN RULE:
    Always join on pnl_data.Customer = ut_data.Customer 
    AND STRFTIME(pnl_data.Period, '%Y-%m') = STRFTIME(ut_data.Period, '%Y-%m')

    OUTPUT: 4 columns [Dimension, Numerator, Denominator, Final_Result].
    """
    
    sql = llm.invoke(system_prompt + f"\nUser Query: {user_query}").content.strip().replace("```sql", "").replace("```", "")
    
    try:
        df = conn.execute(sql).df()
        if df.empty: return sql, "EMPTY_RESULT"
        return sql, df
    except Exception as e:
        return sql, str(e)

# --- 3. THE UI ---
st.set_page_config(page_title="L&T Financial Intel", layout="wide")
st.title("🏛️ L&T Executive Analyst v6.0")

user_input = st.text_input("Ask a question:", placeholder="e.g. Contribution Margin % trend for A1")

if user_input:
    sql, result = execute_query(user_input)
    
    if isinstance(result, pd.DataFrame):
        tab1, tab2 = st.tabs(["📊 Analysis", "🔍 Audit Logic"])
        with tab1:
            st.info(f"Analysis complete for: {user_input}")
            fig, ax = plt.subplots(figsize=(10, 4))
            x_col = result.columns[0]
            ax.plot(result[x_col].astype(str), result['Final_Result'], marker='o', color='#00529B')
            plt.xticks(rotation=45)
            st.pyplot(fig)
            st.dataframe(result[[x_col, 'Final_Result']])
        with tab2:
            st.code(sql, language='sql')
            st.dataframe(result)
    elif result == "EMPTY_RESULT":
        st.warning("No data found for this request. Check if the customer name matches exactly.")
        st.code(sql)
    else:
        st.error(f"Error: {result}")
