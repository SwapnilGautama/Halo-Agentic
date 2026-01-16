import streamlit as st
import pandas as pd
import duckdb
import os
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

st.set_page_config(page_title="L&T AI Finance", layout="wide")

# 1. DATA ENGINE (CLEAN ROOM)
@st.cache_resource
def init_finance_engine():
    conn = duckdb.connect(database=':memory:')
    
    # Load UT Data - Standardize Headers
    if os.path.exists("ut_data.xlsx"):
        df = pd.read_excel("ut_data.xlsx")
        df['Date_a'] = pd.to_datetime(df['Date_a'])
        df = df.rename(columns={"Date_a": "EntryDate", "FinalCustomerName": "Customer", "PSNo": "EmpID"})
        conn.register("ut_data", df)

    # Load PNL Data - Standardize Headers
    if os.path.exists("pnl_data.xlsx"):
        df = pd.read_excel("pnl_data.xlsx")
        df['Month'] = pd.to_datetime(df['Month'])
        df = df.rename(columns={"Month": "EntryDate", "FinalCustomerName": "Customer", "Amount in USD": "USD"})
        conn.register("pnl_data", df)

    # Load Knowledge Assets
    kpi_lib = pd.read_excel("kpi_directory.xlsx").to_string() if os.path.exists("kpi_directory.xlsx") else ""
    return conn, kpi_lib

conn, kpi_library = init_finance_engine()

# 2. THE MULTI-AGENT PIPELINE
def run_financial_query(user_input):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # PHASE 1: Architect (Formula & SQL)
    # We force the AI to look at the KPI library first
    architect_prompt = f"""
    You are a Senior Financial Data Architect. 
    REFERENCE KPI LIBRARY: {kpi_library}
    
    CLEAN SCHEMA:
    - ut_data: EntryDate, Customer, EmpID, TotalBillableHours, NetAvailableHours
    - pnl_data: EntryDate, Customer, USD, Type (Revenue/Cost), Group1 (ONSITE/OFFSHORE)
    
    STRICT RULES:
    1. For Margin %: (Sum(USD) where Type='Revenue' - Sum(USD) where Type='Cost') / Sum(USD) where Type='Revenue'
    2. Dates: Always use EntryDate. Filter by MONTH(EntryDate) or YEAR(EntryDate).
    3. Output ONLY the SQL query. Use double quotes for column names.
    """
    
    sql = llm.invoke(architect_prompt + f"\nUser Question: {user_input}").content.strip().replace("```sql", "").replace("```", "")
    
    try:
        df = conn.execute(sql).df()
        
        # PHASE 2: Visualization Choice
        # We ask the AI to pick the best chart type
        viz_prompt = f"Based on this data: {df.head(2).to_string()}, pick the best chart type: 'line', 'bar', or 'pie'. Return 1 word only."
        chart_type = llm.invoke(viz_prompt).content.strip().lower()
        
        return sql, df, chart_type
    except Exception as e:
        return sql, None, str(e)

# 3. UI EXECUTION
query = st.text_input("Ask a Financial Question (e.g., 'What is the Margin % by Customer?')")

if query:
    sql, df, chart_type = run_financial_query(query)
    
    if df is not None:
        # Concise Summary (Agent 3: Analyst)
        st.subheader("💡 Financial Insight")
        llm = ChatOpenAI(model="gpt-4o", temperature=0)
        summary = llm.invoke(f"In 2 sentences max, summarize this for a CFO: {df.to_string()}").content
        st.info(summary)

        col1, col2 = st.columns([1, 1])
        with col1:
            st.dataframe(df, use_container_width=True)
        
        with col2:
            if not df.empty and len(df.columns) >= 2:
                fig, ax = plt.subplots(figsize=(8, 4))
                x, y = df.iloc[:, 0].astype(str), df.iloc[:, 1]
                
                if 'bar' in chart_type:
                    ax.bar(x, y, color='#1f77b4')
                elif 'pie' in chart_type:
                    ax.pie(y, labels=x, autopct='%1.1f%%')
                else:
                    ax.plot(x, y, marker='o', linewidth=2)
                
                plt.xticks(rotation=45)
                st.pyplot(fig)
    else:
        st.error(f"Logic Error: {chart_type}") # contains error msg here
        st.code(sql)
