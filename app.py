import streamlit as st
import pandas as pd
import duckdb
import os
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- 1. THE DATA REPAIR SHOP (Preserved with space-stripping) ---
@st.cache_resource
def load_and_clean_data():
    conn = duckdb.connect(database=':memory:')
    
    # Process PNL Data
    if os.path.exists("pnl_data.xlsx"):
        df_pnl = pd.read_excel("pnl_data.xlsx")
        df_pnl.columns = [c.strip() for c in df_pnl.columns]
        # Standardizing names for the AI Architect
        df_pnl = df_pnl.rename(columns={'Amount in USD': 'USD', 'FinalCustomerName': 'Customer'})
        df_pnl['Month'] = pd.to_datetime(df_pnl['Month'], errors='coerce')
        conn.register("pnl_data", df_pnl)

    # Process UT Data
    if os.path.exists("ut_data.xlsx"):
        df_ut = pd.read_excel("ut_data.xlsx")
        df_ut.columns = [c.strip() for c in df_ut.columns]
        # Standardizing names for the AI Architect
        df_ut = df_ut.rename(columns={'Date': 'Full_Date', 'FinalCustomerName': 'Customer'})
        df_ut['Full_Date'] = pd.to_datetime(df_ut['Full_Date'], errors='coerce')
        conn.register("ut_data", df_ut)

    # Load Knowledge
    kpi_lib = pd.read_excel("kpi_directory.xlsx").to_string()
    field_lib = pd.read_excel("field_directory.xlsx").to_string()
    
    return conn, kpi_lib, field_lib

conn, kpi_ctx, field_ctx = load_and_clean_data()

# --- 2. THE ARCHITECT AGENT (Updated with Broad Join Logic) ---
def execute_query(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    system_prompt = f"""
    You are a Financial Data Expert. Use these EXACT table schemas:
    
    TABLE: pnl_data
    Columns: [Month, Customer, USD, Type, Group1]
    
    TABLE: ut_data
    Columns: [Full_Date, Customer, PSNo, Status, TotalBillableHours, NetAvailableHours]

    STRICT JOIN RULE: 
    To avoid mismatches in exact day/time, ALWAYS join using:
    pnl_data.Customer = ut_data.Customer 
    AND STRFTIME(pnl_data.Month, '%Y-%m') = STRFTIME(ut_data.Full_Date, '%Y-%m')

    KPI DEFINITIONS:
    {kpi_ctx}

    SQL INSTRUCTIONS:
    - For Margin %: 
      Numerator = (SUM(USD) FILTER (WHERE Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE'))) - (SUM(USD) FILTER (WHERE Type = 'Cost'))
      Denominator = SUM(USD) FILTER (WHERE Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE'))
      Final_Result = (Numerator / NULLIF(Denominator, 0)) * 100
    - For FTE: COUNT(DISTINCT PSNo)
    - Always select: [Dimension (Customer or Month)], [Numerator], [Denominator], [Final_Result]
    - Output ONLY DuckDB SQL.
    """
    
    sql = llm.invoke(system_prompt + f"\nUser Query: {user_query}").content.strip().replace("```sql", "").replace("```", "")
    
    try:
        df = conn.execute(sql).df()
        
        # Check for empty results (The blank output fix)
        if df.empty:
            return sql, "EMPTY_RESULT"
            
        return sql, df
    except Exception as e:
        return sql, str(e)

# --- 3. THE UI ---
st.set_page_config(page_title="L&T Executive Analyst", layout="wide")
st.title("🏛️ L&T Executive Analyst v4.0")
user_input = st.text_input("Enter your request:", placeholder="e.g. Margin % for Customer A1 in June 2025")

if user_input:
    sql, result = execute_query(user_input)
    
    if isinstance(result, pd.DataFrame):
        tab1, tab2 = st.tabs(["📊 Financial Dashboard", "🔍 Calculation Audit"])
        
        with tab1:
            # Summary Insight
            insight = ChatOpenAI(model="gpt-4o").invoke(f"In 20 words or less, summarize: {result.to_string()}").content
            st.info(f"**CFO Insight:** {insight}")

            # Professional Visualization
            fig, ax = plt.subplots(figsize=(10, 4))
            x_ax = result.columns[0]
            y_ax = 'Final_Result'
            
            # Use string conversion for categorical X-axis to avoid plotting errors
            if "Month" in str(x_ax) or "Date" in str(x_ax):
                ax.plot(result[x_ax].astype(str), result[y_ax], marker='o', color='#00529B', linewidth=2)
            else:
                ax.bar(result[x_ax].astype(str), result[y_ax], color='#00529B')
            
            plt.xticks(rotation=45)
            st.pyplot(fig)
            st.dataframe(result[[x_ax, 'Final_Result']])

        with tab2:
            st.subheader("Calculation Audit")
            st.markdown("This view breaks down the raw math components (Numerator and Denominator).")
            st.dataframe(result)
            
            st.write("**Engine-Generated SQL:**")
            st.code(sql, language='sql')

    elif result == "EMPTY_RESULT":
        st.warning("⚠️ The query was successful, but no data was found. This usually means the Customer name or Date you requested does not exist in one of the files.")
        st.code(sql)
    else:
        st.error(f"Execution Error: {result}")
        st.code(sql)
