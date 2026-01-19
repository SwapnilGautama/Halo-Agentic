import streamlit as st
import pandas as pd
import duckdb
import os
import re
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- 1. DATA ENGINE (Exact v15) ---
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

# --- 2. THE ANALYST ENGINE (Surgical Fix) ---
def execute_ai_query(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # Intent Classification (v15)
    intent_prompt = f"Classify as 'DATA' or 'CHAT'. Input: {user_query}. Output only the word."
    intent = llm.invoke(intent_prompt).content.strip().upper()

    if "CHAT" in intent:
        return "CHAT", None, llm.invoke(user_query).content

    # Check for Margin Question
    is_margin = any(w in user_query.lower() for w in ["margin", "profit %", "cm%", "cm %"])

    if is_margin:
        # Colleague's Logic: Bucket Revenue and Cost separately
        prompt = f"""
        Generate a DuckDB SQL query for: {user_query}
        Use this EXACT structure for Margin:
        WITH Rev AS (SELECT FinalCustomerName, SUM("Amount in USD") as r FROM pnl_data WHERE Type='Revenue' AND Group1 IN ('ONSITE','OFFSHORE','INDIRECT REVENUE') GROUP BY 1),
             Cost AS (SELECT FinalCustomerName, SUM("Amount in USD") as c FROM pnl_data WHERE Type='Cost' GROUP BY 1)
        SELECT Rev.FinalCustomerName, Rev.r as Revenue, Cost.c as Cost, ((Rev.r - Cost.c)/NULLIF(Rev.r, 0))*100 as Margin_Perc
        FROM Rev LEFT JOIN Cost ON Rev.FinalCustomerName = Cost.FinalCustomerName
        """
    else:
        # Standard v15 Logic for FTE, Revenue, etc.
        prompt = f"Generate DuckDB SQL for: {user_query}. pnl_data (Month, Type, Group1, Amount in USD), ut_data (Date, PSNo, Segment). Output ONLY SQL."

    response = llm.invoke(prompt).content
    
    # THE SHIELD: Remove "Certainly", "To", or markdown
    sql = re.sub(r"```sql|```", "", response).strip()
    sql_match = re.search(r"\b(SELECT|WITH)\b", sql, re.IGNORECASE)
    if sql_match:
        sql = sql[sql_match.start():]

    try:
        result = conn.execute(sql).df()
        return "DATA", sql, result
    except Exception as e:
        return "ERROR", sql, str(e)

# --- 3. UI (v15 Original) ---
st.set_page_config(layout="wide")
st.title("🏛️ L&T Analyst v15-Final-Fix")

user_input = st.text_input("Ask a question:")

if user_input:
    mode, sql, result = execute_ai_query(user_input)
    
    if mode == "DATA" and not result.empty:
        st.info(f"💡 Average: **{result.iloc[:,-1].mean():,.2f}**")
        tab1, tab2 = st.tabs(["📊 Dashboard", "🧾 Details"])
        with tab1:
            st.dataframe(result, use_container_width=True)
            if len(result) > 1:
                fig, ax = plt.subplots(figsize=(10, 4))
                ax.bar(result.iloc[:, 0].astype(str), result.iloc[:, -1], color='#00529B')
                st.pyplot(fig)
        with tab2:
            st.code(sql, language="sql")
            st.dataframe(result)
    elif mode == "CHAT":
        st.write(result)
    else:
        st.error(f"Error or No Data. Query: {sql}")
