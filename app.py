import streamlit as st
import pandas as pd
import duckdb
import os
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- 1. THE DATA SANITIZER (Fixes discrepancies before AI starts) ---
@st.cache_resource
def load_and_sync_data():
    conn = duckdb.connect(database=':memory:')
    
    # 1. Load PNL Data
    if os.path.exists("pnl_data.xlsx"):
        df_pnl = pd.read_excel("pnl_data.xlsx")
        # Standardize: Force column name to 'Month' and ensure it's a date
        df_pnl['Month'] = pd.to_datetime(df_pnl['Month'], errors='coerce')
        conn.register("pnl_data", df_pnl)

    # 2. Load UT Data
    if os.path.exists("ut_data.xlsx"):
        df_ut = pd.read_excel("ut_data.xlsx")
        # Standardize: Your file has 'Date', AI expects 'Date'. Force it.
        df_ut['Date'] = pd.to_datetime(df_ut['Date'], errors='coerce')
        conn.register("ut_data", df_ut)

    # 3. Load Knowledge Base
    kpi_lib = pd.read_excel("kpi_directory.xlsx").to_string()
    field_lib = pd.read_excel("field_directory.xlsx").to_string()
    
    return conn, kpi_lib, field_lib

conn, kpi_ctx, field_ctx = load_and_sync_data()

# --- 2. THE MULTI-AGENT ANALYST ---
def execute_ai_analysis(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # ARCHITECT: Strictly maps the natural language to SQL using Directories
    architect_prompt = f"""
    You are a Lead Financial Analyst. You MUST use these directories:
    FIELD DIRECTORY: {field_ctx}
    KPI DIRECTORY: {kpi_ctx}

    TABLE SCHEMAS:
    - pnl_data: [Month, FinalCustomerName, USD, Type, Group1, Group Description]
    - ut_data: [Date, FinalCustomerName, PSNo, Status, TotalBillableHours, NetAvailableHours]

    STRICT CALCULATION RULES:
    1. JOINS: Always join on pnl_data.FinalCustomerName = ut_data.FinalCustomerName AND pnl_data.Month = ut_data.Date.
    2. MARGIN %: 
       - Numerator = (SUM(USD) FILTER (WHERE Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE'))) - (SUM(USD) FILTER (WHERE Type = 'Cost'))
       - Denominator = SUM(USD) FILTER (WHERE Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE'))
       - Final_Result = (Numerator / NULLIF(Denominator, 0)) * 100
    3. FTE: COUNT(DISTINCT PSNo)
    4. TRENDS: If 'trend' or 'month' is mentioned, GROUP BY Month (or Date) and ORDER BY Month.

    The SQL MUST return 4 columns: Dimension, Numerator, Denominator, Final_Result.
    """
    
    sql = llm.invoke(architect_prompt + f"\nUser Query: {user_query}").content.strip().replace("```sql", "").replace("```", "")
    
    try:
        df = conn.execute(sql).df()
        return sql, df
    except Exception as e:
        return sql, str(e)

# --- 3. THE UI ---
st.title("🏛️ L&T Executive Intelligence")

user_input = st.text_input("Analyze your data:", placeholder="e.g. What is the Margin % trend for A1?")

if user_input:
    sql, result = execute_ai_analysis(user_input)
    
    if isinstance(result, pd.DataFrame):
        tab1, tab2 = st.tabs(["📊 Executive Dashboard", "🔍 Audit & Logic"])
        
        with tab1:
            # 1. AI Summary
            summary = ChatOpenAI(model="gpt-4o").invoke(f"In 1 sentence, what is the main takeaway? {result.head().to_string()}").content
            st.info(f"**Insight:** {summary}")

            # 2. Visuals
            fig, ax = plt.subplots(figsize=(10, 4))
            x_label = result.columns[0]
            y_label = 'Final_Result'
            
            # Auto-detect Chart Type
            if "Month" in x_label or "Date" in x_label:
                ax.plot(result[x_label].astype(str), result[y_label], marker='o', color='#00529B', linewidth=2)
            else:
                ax.bar(result[x_label].astype(str), result[y_label], color='#00529B')
            
            plt.xticks(rotation=45)
            ax.set_title(user_input, fontweight='bold')
            st.pyplot(fig)
            st.dataframe(result[[x_label, 'Final_Result']])

        with tab2:
            st.subheader("Calculation Audit")
            st.write("**Step 1: SQL Logic Used**")
            st.code(sql, language='sql')
            
            st.write("**Step 2: Component Breakdown**")
            st.markdown("This table shows the raw Numerator (Revenue - Cost) and Denominator (Total Revenue) for every row.")
            st.dataframe(result)
            
            st.write("**Step 3: KPI Definition**")
            st.markdown(f"Applied definitions from your `kpi_directory.xlsx` using `pnl_data` and `ut_data`.")
    else:
        st.error(f"Logic Mismatch: {result}")
        st.code(sql)
