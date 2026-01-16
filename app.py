import streamlit as st
import pandas as pd
import duckdb
import os
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- 1. DATA ENGINE ---
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

# --- 2. THE ANALYST ENGINE (v14.0) ---
def execute_ai_query(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # 1. Intent Classification (Preserved)
    intent_prompt = f"Classify as 'DATA' or 'CHAT'. User: {user_query}. Output one word."
    intent = llm.invoke(intent_prompt).content.strip().upper()

    if 'CHAT' in intent:
        return "CHAT", None, llm.invoke(f"Greet as L&T Assistant: {user_query}").content

    # 2. SQL Path with Enhanced Mapping
    system_prompt = """
    You are a Financial SQL Generator for DuckDB. 
    
    DATA CORRECTIONS:
    - C&B Cost: Must check for BOTH 'C&B - Onsite Total' AND 'C&B Cost - Offshore' (or 'C&B - Offshore Total').
    - Revenue: Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE').
    
    DYNAMIC NAMING RULE:
    - Instead of 'Numerator', alias it as the specific metric (e.g., CB_Cost, Billable_Hours).
    - Instead of 'Denominator', alias it as the specific metric (e.g., Revenue, Available_Hours).
    
    KPI REFRESHER:
    - C&B % of Revenue: (SUM("Amount in USD") where Type='Cost' and Group3 like 'C&B%') / (SUM("Amount in USD") where Group1 in ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE'))
    - Segment: Use pnl_data.Segment for financial KPIs.
    
    OUTPUT: [Dimension, Metric_Numerator_Name, Metric_Denominator_Name, Final_Result]
    """
    
    response = llm.invoke(system_prompt + f"\nUser Query: {user_query}")
    sql = response.content.strip().replace("```sql", "").replace("```", "")
    
    try:
        df = conn.execute(sql).df()
        return "DATA", sql, df
    except Exception as e:
        return "ERROR", sql, str(e)

# --- 3. UI ---
st.title("🏛️ L&T Executive Analyst v14.0")
user_input = st.text_input("Ask about P&L or UT metrics:")

if user_input:
    mode, sql, result = execute_ai_query(user_input)
    
    if mode == "CHAT":
        st.write(result)
    elif mode == "DATA":
        if not result.empty:
            avg_val = result.iloc[:,-1].mean()
            st.info(f"💡 **Executive Insight:** Average {result.columns[-1]} is **{avg_val:,.2f}**.")
            
        tab1, tab2 = st.tabs(["📊 Dashboard", "🧾 Calculation Details"])
        with tab1:
            # Show Segment/Month and the Result
            st.dataframe(result.iloc[:, [0, -1]])
            if len(result) > 1:
                fig, ax = plt.subplots(figsize=(10, 3))
                ax.plot(result.iloc[:, 0].astype(str), result.iloc[:, -1], marker='o')
                plt.xticks(rotation=45)
                st.pyplot(fig)
        with tab2:
            st.markdown("### 🔍 Calculation Audit")
            st.write("**Actual Data Fields Used:**")
            # This table now shows columns like 'CB_Cost' and 'Revenue' instead of generic 'Numerator'
            st.dataframe(result)
            st.code(sql, language="sql")
