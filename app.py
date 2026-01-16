import streamlit as st
import pandas as pd
import duckdb
import os
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- 1. DATA PRE-PROCESSOR (The "Truth" Layer) ---
@st.cache_resource
def load_and_standardize_data():
    conn = duckdb.connect(database=':memory:')
    
    # Load UT Data
    if os.path.exists("ut_data.xlsx"):
        df_ut = pd.read_excel("ut_data.xlsx")
        # Standardize Date_a to a real SQL Date
        df_ut['Standard_Date'] = pd.to_datetime(df_ut['Date_a'])
        # Rename to match Directory terminology
        df_ut = df_ut.rename(columns={"FinalCustomerName": "Customer_Name", "PSNo": "Employee_ID"})
        conn.register("ut_data", df_ut)

    # Load PNL Data
    if os.path.exists("pnl_data.xlsx"):
        df_pnl = pd.read_excel("pnl_data.xlsx")
        # Standardize Month (e.g. "Sunday, June 1...") to a real SQL Date
        df_pnl['Standard_Date'] = pd.to_datetime(df_pnl['Month'])
        df_pnl = df_pnl.rename(columns={"FinalCustomerName": "Customer_Name", "Amount in USD": "USD_Value"})
        conn.register("pnl_data", df_pnl)

    # Load Knowledge Assets
    kpi_lib = pd.read_excel("kpi_directory.xlsx").to_string() if os.path.exists("kpi_directory.xlsx") else ""
    field_lib = pd.read_excel("field_directory.xlsx").to_string() if os.path.exists("field_directory.xlsx") else ""
    
    return conn, kpi_lib, field_lib

conn, kpi_context, field_context = load_and_standardize_data()

# --- 2. MULTI-AGENT EXECUTION ---
def run_ai_analyst(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # ARCHITECT AGENT: SQL Generation
    architect_instruction = f"""
    You are a Lead Financial Architect. You MUST use these two directories as your ONLY source of truth:
    1. FIELD DIRECTORY: {field_context}
    2. KPI DIRECTORY: {kpi_context}

    DATABASE SCHEMA (Use these exact names):
    - Table 'ut_data': [Standard_Date, Customer_Name, Employee_ID, TotalBillableHours, NetAvailableHours]
    - Table 'pnl_data': [Standard_Date, Customer_Name, USD_Value, Type, Group1]

    CRITICAL MATH RULES:
    - Contribution Margin %: 
        Numerator = (SUM(USD_Value) WHERE Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE')) - (SUM(USD_Value) WHERE Type = 'Cost')
        Denominator = (SUM(USD_Value) WHERE Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE'))
        Result = (Numerator / Denominator) * 100
    - Trend: Always group by 'Standard_Date' and ORDER BY 'Standard_Date' ASC.

    Your SQL must return a 'Numerator', 'Denominator', and 'Final_Result' column.
    """
    
    sql = llm.invoke(architect_instruction + f"\nQuery: {user_query}").content.strip().replace("```sql", "").replace("```", "")
    
    try:
        df = conn.execute(sql).df()
        return sql, df
    except Exception as e:
        return sql, str(e)

# --- 3. THE UI ---
st.title("🏛️ L&T Executive Intelligence")
query = st.text_input("Ask a question (e.g., 'Margin % trend by customer'):")

if query:
    sql, result = run_ai_analyst(query)
    
    if isinstance(result, pd.DataFrame):
        tab1, tab2 = st.tabs(["📊 CFO Dashboard", "🔍 Calculation Audit"])
        
        with tab1:
            # Concise Analyst Summary
            llm = ChatOpenAI(model="gpt-4o", temperature=0)
            summary = llm.invoke(f"Summarize this in 2 bullets: {result.head().to_string()}").content
            st.info(summary)
            
            # Dynamic Matplotlib Chart
            fig, ax = plt.subplots(figsize=(10, 4))
            x_col = result.columns[0]
            y_col = 'Final_Result' if 'Final_Result' in result.columns else result.columns[-1]
            
            # Logic to pick Bar or Line
            if "Date" in str(x_col) or len(result) > 10:
                ax.plot(result[x_col].astype(str), result[y_col], marker='o', color='#00529B')
            else:
                ax.bar(result[x_col].astype(str), result[y_col], color='#00529B')
            
            plt.xticks(rotation=45)
            st.pyplot(fig)
            st.dataframe(result)

        with tab2:
            st.subheader("Data Lineage")
            st.write("**Fields Used:** Standard_Date, Customer_Name, USD_Value")
            st.write("**Generated SQL:**")
            st.code(sql)
    else:
        st.error(f"Logic Error: {result}")
        st.code(sql)
