import streamlit as st
import pandas as pd
import duckdb
import os
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- 1. THE DATA REPAIR SHOP ---
@st.cache_resource
def load_and_clean_data():
    conn = duckdb.connect(database=':memory:')
    
    # Process PNL Data
    if os.path.exists("pnl_data.xlsx"):
        df_pnl = pd.read_excel("pnl_data.xlsx")
        # FORCE column names to match the KPI Directory perfectly
        df_pnl.columns = [c.strip() for c in df_pnl.columns]
        # Rename common variations to standard names
        df_pnl = df_pnl.rename(columns={'Amount in USD': 'USD', 'FinalCustomerName': 'Customer'})
        df_pnl['Month'] = pd.to_datetime(df_pnl['Month'], errors='coerce')
        conn.register("pnl_data", df_pnl)

    # Process UT Data
    if os.path.exists("ut_data.xlsx"):
        df_ut = pd.read_excel("ut_data.xlsx")
        df_ut.columns = [c.strip() for c in df_ut.columns]
        # Rename common variations to standard names
        df_ut = df_ut.rename(columns={'Date': 'Full_Date', 'FinalCustomerName': 'Customer'})
        df_ut['Full_Date'] = pd.to_datetime(df_ut['Full_Date'], errors='coerce')
        conn.register("ut_data", df_ut)

    # Load Knowledge
    kpi_lib = pd.read_excel("kpi_directory.xlsx").to_string()
    field_lib = pd.read_excel("field_directory.xlsx").to_string()
    
    return conn, kpi_lib, field_lib

conn, kpi_ctx, field_ctx = load_and_clean_data()

# --- 2. THE ARCHITECT AGENT ---
def execute_query(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # The secret sauce: We tell the AI exactly what the cleaned columns are
    system_prompt = f"""
    You are a Financial Data Expert. Use these EXACT table schemas:
    
    TABLE: pnl_data
    Columns: [Month, Customer, USD, Type, Group1]
    
    TABLE: ut_data
    Columns: [Full_Date, Customer, PSNo, Status, TotalBillableHours, NetAvailableHours]

    JOIN RULE: pnl_data.Customer = ut_data.Customer AND pnl_data.Month = ut_data.Full_Date

    KPI DEFINITIONS:
    {kpi_ctx}

    SQL INSTRUCTIONS:
    - For Margin %: 
      Numerator = (SUM(USD) FILTER (WHERE Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE'))) - (SUM(USD) FILTER (WHERE Type = 'Cost'))
      Denominator = SUM(USD) FILTER (WHERE Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE'))
      Final_Result = (Numerator / NULLIF(Denominator, 0)) * 100
    - Always select: [Dimension], [Numerator], [Denominator], [Final_Result]
    - Output ONLY DuckDB SQL.
    """
    
    sql = llm.invoke(system_prompt + f"\nUser Query: {user_query}").content.strip().replace("```sql", "").replace("```", "")
    
    try:
        df = conn.execute(sql).df()
        return sql, df
    except Exception as e:
        return sql, str(e)

# --- 3. THE UI ---
st.title("🏛️ L&T Executive Analyst v3.0")
user_input = st.text_input("Enter your request:", placeholder="e.g. Contribution Margin % by Customer for June 2025")

if user_input:
    sql, result = execute_query(user_input)
    
    if isinstance(result, pd.DataFrame):
        tab1, tab2 = st.tabs(["📊 Financial Dashboard", "🔍 Calculation Audit"])
        
        with tab1:
            # Summary Insight
            insight = ChatOpenAI(model="gpt-4o").invoke(f"Summarize these findings: {result.to_string()}").content
            st.info(f"**CFO Insight:** {insight}")

            # Professional Visualization
            fig, ax = plt.subplots(figsize=(10, 4))
            x_ax = result.columns[0]
            y_ax = 'Final_Result'
            
            if "Month" in str(x_ax) or "Date" in str(x_ax):
                ax.plot(result[x_ax].astype(str), result[y_ax], marker='o', color='#00529B')
            else:
                ax.bar(result[x_ax].astype(str), result[y_ax], color='#00529B')
            
            plt.xticks(rotation=45)
            st.pyplot(fig)
            st.dataframe(result[[x_ax, 'Final_Result']])

        with tab2:
            st.subheader("How was this calculated?")
            st.write("**Mathematical Breakdown:**")
            st.dataframe(result) # Shows Numerator and Denominator
            
            st.write("**Engine-Generated SQL:**")
            st.code(sql, language='sql')
    else:
        st.error(f"Execution Error: {result}")
        st.code(sql)
