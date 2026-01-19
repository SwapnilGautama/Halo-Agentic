import streamlit as st
import pandas as pd
import os
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI
# Using pandas as the engine if duckdb is unavailable in your environment
import sqlite3 

# --- 1. DATA ENGINE (Load and Clean) ---
@st.cache_resource
def load_data():
    # Use SQLite as a reliable fallback for local/Streamlit environments
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    
    if os.path.exists("pnl_data.xlsx"):
        df_pnl = pd.read_excel("pnl_data.xlsx")
        df_pnl['Month'] = pd.to_datetime(df_pnl['Month']).dt.strftime('%Y-%m-%d')
        df_pnl.to_sql("pnl_data", conn, index=False, if_exists='replace')

    if os.path.exists("ut_data.xlsx"):
        df_ut = pd.read_excel("ut_data.xlsx")
        df_ut['Date'] = pd.to_datetime(df_ut['Date']).dt.strftime('%Y-%m-%d')
        df_ut.to_sql("ut_data", conn, index=False, if_exists='replace')

    return conn

conn = load_data()

# --- 2. THE ANALYST ENGINE (v16.0) ---
def execute_ai_query(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # 1. Intent Classification
    intent = llm.invoke(f"Classify as 'DATA' or 'CHAT': {user_query}").content.strip().upper()
    if 'CHAT' in intent:
        return "CHAT", None, llm.invoke(f"Greet user and say you are ready for L&T data analysis: {user_query}").content

    # 2. SQL Path with CTE instructions for Margin
    system_prompt = """
    You are an expert SQL generator. Use the following logic for L&T KPIs:

    - REVENUE: SUM("Amount in USD") WHERE Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE')
    - TOTAL COST: SUM("Amount in USD") WHERE Type = 'Cost'
    - MARGIN %: ((Revenue - Total_Cost) / NULLIF(Revenue, 0)) * 100
    - C&B COST: SUM("Amount in USD") WHERE Group3 IN ('C&B - Onsite Total', 'C&B Cost - Offshore') AND Type = 'Cost'
    
    QUERY STRUCTURE RULE:
    For Margin % or complex ratios, use a CTE (WITH clause) to calculate Revenue and Cost separately before joining them. 
    This prevents 'blank' results when an account has missing data types.

    OUTPUT COLUMNS: [Dimension, Component_1, Component_2, Final_Result]
    """
    
    response = llm.invoke(system_prompt + f"\nUser Query: {user_query}")
    sql = response.content.strip().replace("```sql", "").replace("```", "")
    
    try:
        df = pd.read_sql_query(sql, conn)
        return "DATA", sql, df
    except Exception as e:
        return "ERROR", sql, str(e)

# --- 3. UI LAYOUT ---
st.title("🏛️ L&T Executive Analyst v16.0")
user_input = st.text_input("Ask about Margin %, C&B, or Utilization:")

if user_input:
    mode, sql, result = execute_ai_query(user_input)
    
    if mode == "CHAT":
        st.write(result)
    elif mode == "DATA":
        if not result.empty:
            # 2-Point Insights
            avg_val = result.iloc[:, -1].mean()
            max_row = result.loc[result.iloc[:, -1].idxmax()]
            st.info(f"💡 **Insights:** Average: **{avg_val:,.2f}%** | Highest: **{max_row.iloc[0]}** (**{max_row.iloc[-1]:,.2f}%**)")

            tab1, tab2 = st.tabs(["📊 Dashboard", "🧾 Calculation Details"])
            with tab1:
                st.dataframe(result.iloc[:, [0, -1]], use_container_width=True)
                if len(result) > 1:
                    fig, ax = plt.subplots(figsize=(10, 4))
                    result.plot(kind='bar', x=result.columns[0], y=result.columns[-1], ax=ax, color='#00529B')
                    st.pyplot(fig)
            with tab2:
                st.write("**Full Component Breakdown:**")
                st.dataframe(result)
                st.code(sql, language="sql")
        else:
            st.warning("No data found. Try adjusting the account name or date.")
