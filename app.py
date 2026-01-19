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

# --- 2. THE ANALYST ENGINE (v19.0 - v15 + CTE Logic) ---
def execute_ai_query(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # 1. Intent Classification (Preserved from v15)
    intent_prompt = f"Classify as 'DATA' or 'CHAT'. User: {user_query}. Output one word."
    intent = llm.invoke(intent_prompt).content.strip().upper()

    if 'CHAT' in intent:
        return "CHAT", None, llm.invoke(f"Greet as L&T Assistant: {user_query}").content

    # 2. SQL Path with CTE (Common Table Expression) Logic
    system_prompt = """
    You are a Financial SQL Generator for DuckDB. 
    
    CTE LOGIC INSTRUCTIONS:
    For any query calculating a percentage (Margin % or C&B %), use a WITH clause to create separate tables for the Numerator and Denominator.
    
    Example Structure:
    WITH RevTable AS (SELECT Segment, SUM("Amount in USD") as Revenue FROM pnl_data WHERE Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE') GROUP BY 1),
         CostTable AS (SELECT Segment, SUM("Amount in USD") as Total_Cost FROM pnl_data WHERE Type = 'Cost' GROUP BY 1)
    SELECT r.Segment, r.Revenue, c.Total_Cost, ((r.Revenue - c.Total_Cost)/NULLIF(r.Revenue,0))*100 as Margin_Perc
    FROM RevTable r LEFT JOIN CostTable c ON r.Segment = c.Segment;

    MAPPING:
    - C&B Cost: Use Group3 IN ('C&B - Onsite Total', 'C&B Cost - Offshore')
    - Revenue: Use Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE')
    
    OUTPUT: Always return 4 columns: [Dimension, Actual_Numerator_Name, Actual_Denominator_Name, Final_Result].
    """
    
    response = llm.invoke(system_prompt + f"\nUser Query: {user_query}")
    sql = response.content.strip().replace("```sql", "").replace("```", "")
    
    try:
        df = conn.execute(sql).df()
        return "DATA", sql, df
    except Exception as e:
        return "ERROR", sql, str(e)

# --- 3. UI (v15 Base) ---
st.title("🏛️ L&T Executive Analyst v19.0")
user_input = st.text_input("Ask about P&L or UT metrics (e.g. C&B % by Segment):")

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
                st.dataframe(result.iloc[:, [0, -1]], use_container_width=True)
                if len(result) > 1:
                    fig, ax = plt.subplots(figsize=(10, 3))
                    ax.bar(result.iloc[:, 0].astype(str), result.iloc[:, -1], color='#00529B')
                    plt.xticks(rotation=45)
                    st.pyplot(fig)
            with tab2:
                st.markdown("### 🔍 Calculation Audit")
                st.write("**Fields used as components:**")
                st.dataframe(result, use_container_width=True)
                st.code(sql, language="sql")
        else:
            st.warning("No data found for this query.")
    elif mode == "ERROR":
        st.error(f"SQL Error: {result}")
