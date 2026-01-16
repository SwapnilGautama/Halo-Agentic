import streamlit as st
import pandas as pd
import duckdb
import os
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- 1. DATA ENGINE (Preserved from v11) ---
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

# --- 2. THE ANALYST ENGINE (With Intent Gatekeeper) ---
def execute_ai_query(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # STEP 1: Identify Intent
    intent_prompt = f"""
    Classify the user input as 'DATA' or 'CHAT'.
    - DATA: Requests for KPIs, Revenue, UT, Segment analysis, or specific numbers.
    - CHAT: Greetings, 'What can you do?', 'Who are you?', or general talk.
    Input: "{user_query}"
    Output: Single word 'DATA' or 'CHAT'.
    """
    intent = llm.invoke(intent_prompt).content.strip().upper()

    if 'CHAT' in intent:
        chat_prompt = f"You are a helpful assistant for L&T Executives. Briefly explain you can analyze P&L and Utilization data. Input: {user_query}"
        return "CHAT", None, llm.invoke(chat_prompt).content

    # STEP 2: Data Path (Strictly preserved SQL logic)
    system_prompt = """
    Return ONLY a DuckDB SQL query. 
    TABLES: 
    - pnl_data: [Month, FinalCustomerName, "Amount in USD", Type, Group1, Group3, Segment]
    - ut_data: [Date, FinalCustomerName, PSNo, TotalBillableHours, NetAvailableHours, Segment]
    
    RULES:
    - Use ut_data.Segment for UT/FTE queries.
    - Use pnl_data.Segment for Revenue/Cost queries.
    - JOIN on FinalCustomerName AND Month/Date (STRFTIME %Y-%m).
    - Select: [Dimension, Numerator, Denominator, Final_Result].
    """
    
    response = llm.invoke(system_prompt + f"\nUser Query: {user_query}")
    sql = response.content.strip().replace("```sql", "").replace("```", "")
    
    try:
        df = conn.execute(sql).df()
        return "DATA", sql, df
    except Exception as e:
        return "ERROR", sql, str(e)

# --- 3. UI LAYOUT (Preserved v11 Features) ---
st.title("🏛️ L&T Executive Analyst v12.0")
user_input = st.text_input("Ask me anything:")

if user_input:
    mode, sql, result = execute_ai_query(user_input)
    
    if mode == "CHAT":
        st.write(result)
    elif mode == "DATA":
        # 2-Point Insights
        if not result.empty:
            st.info(f"💡 **Insights:** Avg: {result.iloc[:,-1].mean():,.2f} | Peak: {result.iloc[:,-1].max():,.2f}")
            
        tab1, tab2 = st.tabs(["📊 Dashboard", "🧾 Calculation Details"])
        with tab1:
            st.dataframe(result.iloc[:, [0, -1]])
            fig, ax = plt.subplots(figsize=(10, 3))
            ax.plot(result.iloc[:, 0].astype(str), result.iloc[:, -1], marker='o')
            st.pyplot(fig)
        with tab2:
            st.code(sql, language="sql")
            st.dataframe(result)
