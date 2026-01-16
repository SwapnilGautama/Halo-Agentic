import streamlit as st
import pandas as pd
import duckdb
import os
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- SETTINGS ---
st.set_page_config(page_title="L&T Financial AI 2.0", layout="wide")
st.title("🏛️ L&T Executive Financial Dashboard")

# 1. CLEAN ROOM DATA LOADING
@st.cache_resource
def load_and_clean_data():
    conn = duckdb.connect(database=':memory:')
    
    # Load UT Data & Standardize
    if os.path.exists("ut_data.xlsx"):
        df_ut = pd.read_excel("ut_data.xlsx")
        # Step 1: Force Date conversion
        df_ut['Date_a'] = pd.to_datetime(df_ut['Date_a'])
        # Step 2: Rename for the Architect (removing ambiguity)
        df_ut = df_ut.rename(columns={
            "Date_a": "EntryDate",
            "FinalCustomerName": "Customer",
            "PSNo": "EmployeeID",
            "Month": "Raw_Month_Num", # Hide the original
            "Year": "Raw_Year"         # Hide the original
        })
        conn.register("ut_data", df_ut)

    # Load P&L Data & Standardize
    if os.path.exists("pnl_data.xlsx"):
        df_pnl = pd.read_excel("pnl_data.xlsx")
        # Force the P&L 'Month' (which is a date string) into a real date
        df_pnl['Month'] = pd.to_datetime(df_pnl['Month'])
        df_pnl = df_pnl.rename(columns={
            "Month": "EntryDate",
            "FinalCustomerName": "Customer",
            "Amount in USD": "USD_Value"
        })
        conn.register("pnl_data", df_pnl)

    # Load Directories for Agent Context
    field_ctx = pd.read_excel("field_directory.xlsx").to_string() if os.path.exists("field_directory.xlsx") else ""
    kpi_ctx = pd.read_excel("kpi_directory.xlsx").to_string() if os.path.exists("kpi_directory.xlsx") else ""
    
    return conn, field_ctx, kpi_ctx

conn, field_context, kpi_context = load_and_clean_data()

# 2. THE MULTI-AGENT ARCHITECTURE
def run_ai_system(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # --- AGENT 1: THE ARCHITECT (SQL Generation) ---
    # We provide a "Clean Schema" to the architect so it doesn't get confused
    architect_prompt = f"""
    You are the Lead Data Architect. Use the following CLEAN SCHEMA to write DuckDB SQL.
    
    TABLE: ut_data
    - EntryDate (DATE): Use for all time filters.
    - Customer (VARCHAR): The Client/Customer name.
    - EmployeeID (VARCHAR): Use for FTE/Headcount (COUNT DISTINCT).
    - Status (VARCHAR): Billable/Non-Billable.

    TABLE: pnl_data
    - EntryDate (DATE): Use for all time filters.
    - Customer (VARCHAR): The Client/Customer name.
    - USD_Value (DOUBLE): All financial amounts (Revenue/Cost).
    - Type (VARCHAR): 'Revenue' or 'Cost'.

    DATE LOGIC:
    - Feb 2025: WHERE EntryDate = '2025-02-01' (or use MONTH()/YEAR() functions)
    - Trends: Group by EntryDate and ORDER BY EntryDate ASC.

    KPI LOGIC:
    {kpi_context}

    Return ONLY the SQL.
    """
    
    sql = llm.invoke(architect_prompt + f"\nUser: {user_query}").content.strip().replace("```sql", "").replace("```", "")
    
    try:
        results_df = conn.execute(sql).df()
        
        # --- AGENT 2: THE ANALYST (Narrative) ---
        analysis = llm.invoke(f"As a CFO, explain these results: {results_df.to_string()}").content
        
        return sql, results_df, analysis
    except Exception as e:
        return sql, None, str(e)

# 3. UI LAYOUT
with st.sidebar:
    st.header("🔍 System Health")
    if st.checkbox("Inspect Clean Schema"):
        st.write("UT Table:")
        st.write(conn.execute("DESCRIBE ut_data").df()[['column_name', 'column_type']])
        st.write("P&L Table:")
        st.write(conn.execute("DESCRIBE pnl_data").df()[['column_name', 'column_type']])

query = st.text_input("Ask your financial question:", placeholder="e.g., What is the FTE trend for Customer A36?")

if query:
    sql, df, analysis = run_ai_system(query)
    
    if df is not None:
        st.subheader("📊 Executive Analysis")
        st.markdown(analysis)
        
        col1, col2 = st.columns([1, 1])
        with col1:
            st.write("**Data Extract**")
            st.dataframe(df)
        
        with col2:
            st.write("**Visual Trend**")
            if not df.empty and len(df.columns) >= 2:
                # --- AGENT 3: VISUALIZATION (Matplotlib) ---
                fig, ax = plt.subplots()
                ax.plot(df.iloc[:,0].astype(str), df.iloc[:,1], marker='o', color='#00529B', linewidth=2)
                ax.set_title(query, fontsize=10)
                plt.xticks(rotation=45)
                ax.grid(True, alpha=0.3)
                st.pyplot(fig)
    else:
        st.error(f"The Architect generated an invalid query: {analysis}")
        st.code(sql)
