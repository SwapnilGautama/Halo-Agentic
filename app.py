import streamlit as st
import pandas as pd
import duckdb
import os
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- 1. DATA ENGINE (v15 Stable Foundation) ---
@st.cache_resource
def load_data():
    conn = duckdb.connect(database=':memory:')
    if os.path.exists("pnl_data.xlsx"):
        df_pnl = pd.read_excel("pnl_data.xlsx")
        df_pnl['Month'] = pd.to_datetime(df_pnl['Month'], errors='coerce')
        conn.register("pnl_data", df_pnl)
    if os.path.exists("ut_data.xlsx"):
        df_ut = pd.read_excel("ut_data.xlsx")
        df_ut['Date'] = pd.to_datetime(df_ut['Date'], errors='coerce')
        conn.register("ut_data", df_ut)
    return conn

conn = load_data()

# --- 2. THE ANALYST ENGINE (v17.0) ---
def execute_ai_query(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # 1. Intent Gatekeeper
    intent = llm.invoke(f"Classify as 'DATA' or 'CHAT'. User: {user_query}").content.strip().upper()
    if 'CHAT' in intent:
        return "CHAT", None, llm.invoke(f"Greet user as L&T Assistant: {user_query}").content

    # 2. SQL Path with Precise Formula Mapping
    system_prompt = """
    You are a Financial SQL expert for DuckDB. 
    
    METRIC DEFINITIONS:
    - Revenue: SUM("Amount in USD") FILTER (WHERE Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE'))
    - Total_Cost: SUM("Amount in USD") FILTER (WHERE Type = 'Cost')
    - Margin_Perc: ((Revenue - Total_Cost) / NULLIF(Revenue, 0)) * 100
    - C&B_Cost: SUM("Amount in USD") FILTER (WHERE Group3 IN ('C&B - Onsite Total', 'C&B Cost - Offshore') AND Type = 'Cost')
    - FTE: COUNT(DISTINCT PSNo)

    COLUMN NAMING RULE:
    Always name the columns exactly as [Dimension, Component_1, Component_2, Final_Result].
    For Margin questions, Component_1 must be 'Revenue' and Component_2 must be 'Total_Cost'.

    DATE RULE:
    June 2025 is '2025-06-01'. Use STRFTIME(Month, '%Y-%m') for comparisons.
    """
    
    response = llm.invoke(system_prompt + f"\nUser Query: {user_query}")
    sql = response.content.strip().replace("```sql", "").replace("```", "")
    
    try:
        df = conn.execute(sql).df()
        return "DATA", sql, df
    except Exception as e:
        return "ERROR", sql, str(e)

# --- 3. UI LAYOUT ---
st.set_page_config(layout="wide")
st.title("🏛️ L&T Executive Analyst v17.0")

user_input = st.text_input("Ask about Margin, C&B %, FTE, or Utilization:")

if user_input:
    mode, sql, result = execute_ai_query(user_input)
    
    if mode == "CHAT":
        st.write(result)
    elif mode == "DATA":
        if not result.empty:
            # Executive Insights
            last_col = result.columns[-1]
            avg_val = result[last_col].mean()
            st.info(f"💡 **Executive Summary:** Average {last_col} is **{avg_val:,.2f}**")

            tab1, tab2 = st.tabs(["📊 Dashboard", "🧾 Calculation Details"])
            with tab1:
                # Show main result
                st.dataframe(result.iloc[:, [0, -1]], use_container_width=True)
                if len(result) > 1:
                    fig, ax = plt.subplots(figsize=(10, 3))
                    ax.bar(result.iloc[:, 0].astype(str), result.iloc[:, -1], color='#00529B')
                    plt.xticks(rotation=45)
                    st.pyplot(fig)
            with tab2:
                st.markdown("### Audit Trail")
                st.write("Full breakdown of components used:")
                st.dataframe(result, use_container_width=True)
                st.code(sql, language="sql")
        else:
            st.warning("Query returned no results. Check if the Customer/Segment name is spelled correctly.")
    elif mode == "ERROR":
        st.error(f"SQL Error: {result}")
