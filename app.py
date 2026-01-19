import streamlit as st
import pandas as pd
import duckdb
import os
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- 1. DATA ENGINE (v15 Base) ---
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

# --- 2. THE ANALYST ENGINE (v18.0) ---
def execute_ai_query(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # Intent Classification
    intent = llm.invoke(f"Return only 'DATA' or 'CHAT' for: {user_query}").content.strip().upper()
    if 'CHAT' in intent:
        return "CHAT", None, llm.invoke(f"Greet the user as their L&T Financial Assistant: {user_query}").content

    # SQL Generation Logic
    system_prompt = """
    You are a SQL expert for DuckDB.
    
    FORMULA RULES (STRICT):
    - Revenue = SUM(CASE WHEN Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE') THEN "Amount in USD" ELSE 0 END)
    - Total_Cost = SUM(CASE WHEN Type = 'Cost' THEN "Amount in USD" ELSE 0 END)
    - CB_Cost = SUM(CASE WHEN Group3 IN ('C&B - Onsite Total', 'C&B Cost - Offshore') AND Type = 'Cost' THEN "Amount in USD" ELSE 0 END)
    - Margin_Perc = ((Revenue - Total_Cost) / NULLIF(Revenue, 0)) * 100
    - CB_Perc = (CB_Cost / NULLIF(Revenue, 0)) * 100

    QUERY INSTRUCTIONS:
    - Use the pnl_data table.
    - Segment is 'Segment', Account is 'FinalCustomerName', Month is 'Month'.
    - For 'June 2025', filter using: Month = '2025-06-01'.
    - Always provide 4 columns: [Dimension (Segment/Account), Component_1, Component_2, Final_Result].
    - Use clear names: 'Revenue', 'Total_Cost', 'CB_Cost', 'Margin_Perc', 'CB_Ratio'.
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
st.title("🏛️ L&T Executive Analyst v18.0")

user_input = st.text_input("Query (e.g., 'Margin % by account for June 2025' or 'C&B cost as % of revenue by segment')")

if user_input:
    mode, sql, result = execute_ai_query(user_input)
    
    if mode == "CHAT":
        st.write(result)
    elif mode == "DATA":
        if not result.empty:
            # 2-Point Insights
            last_col = result.columns[-1]
            avg_val = result[last_col].mean()
            max_val = result[last_col].max()
            st.info(f"💡 **Executive Summary:** Average {last_col}: **{avg_val:,.2f}** | Peak {last_col}: **{max_val:,.2f}**")

            tab1, tab2 = st.tabs(["📊 Dashboard", "🧾 Calculation Details"])
            with tab1:
                # Main display: First and Last column
                st.dataframe(result.iloc[:, [0, -1]], use_container_width=True)
                if len(result) > 1:
                    fig, ax = plt.subplots(figsize=(10, 3))
                    ax.bar(result.iloc[:, 0].astype(str), result.iloc[:, -1], color='#00529B')
                    plt.xticks(rotation=45)
                    st.pyplot(fig)
            with tab2:
                st.markdown("### 🔍 Calculation Audit")
                st.write("Components used in this calculation:")
                st.dataframe(result, use_container_width=True) # Shows actual names like Revenue/Total_Cost
                st.code(sql, language="sql")
        else:
            st.warning("No data found. Please verify the month or account name.")
    elif mode == "ERROR":
        st.error(f"SQL Execution Error: {result}")
