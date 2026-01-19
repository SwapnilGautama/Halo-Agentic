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

# --- 2. THE ANALYST ENGINE (Surgical Template Insertion) ---
def execute_ai_query(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # Intent Classification (Original v15)
    intent_prompt = f"Classify the user input as 'DATA' or 'CHAT'. Input: {user_query}. Output only the word."
    intent = llm.invoke(intent_prompt).content.strip().upper()

    if "CHAT" in intent:
        return "CHAT", None, llm.invoke(user_query).content

    # Logic Path
    is_margin = any(w in user_query.lower() for w in ["margin", "profit", "cm%", "cm %"])

    if is_margin:
        # Step 1: Just extract the filters using AI
        filter_prompt = f"From the query '{user_query}', extract only the Dimension (Segment or FinalCustomerName) and the Month filter (e.g. Month = '2025-06-01'). Output: Dim | Date"
        extraction = llm.invoke(filter_prompt).content.strip().split("|")
        dim = extraction[0].strip() if len(extraction) > 0 else "Segment"
        date_f = extraction[1].strip() if len(extraction) > 1 else "1=1"
        
        # Step 2: Use your specific working query
        sql = f"""
        WITH RevenueBucket AS (
            SELECT "{dim}", SUM("Amount in USD") as total_rev 
            FROM pnl_data 
            WHERE Type = 'Revenue' AND Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE') AND {date_f}
            GROUP BY 1
        ),
        CostBucket AS (
            SELECT "{dim}", SUM("Amount in USD") as total_cost 
            FROM pnl_data 
            WHERE Type = 'Cost' AND {date_f}
            GROUP BY 1
        )
        SELECT 
            r."{dim}", r.total_rev as Revenue, c.total_cost as Cost,
            ((r.total_rev - COALESCE(c.total_cost, 0)) / NULLIF(r.total_rev, 0)) * 100 as Margin_Perc
        FROM RevenueBucket r
        LEFT JOIN CostBucket c ON r."{dim}" = c."{dim}"
        ORDER BY Margin_Perc ASC;
        """
    else:
        # ORIGINAL V15 PROMPT - UNTOUCHED
        fallback_prompt = f"Generate a DuckDB SQL query for: {user_query}. Tables: pnl_data, ut_data. Output ONLY the SQL."
        sql_raw = llm.invoke(fallback_prompt).content
        # Simple cleanup to remove conversational text
        sql = re.sub(r"```sql|```", "", sql_raw).strip()
        # Find where SELECT or WITH starts
        match = re.search(r"\b(SELECT|WITH)\b", sql, re.IGNORECASE)
        if match: sql = sql[match.start():]

    try:
        df = conn.execute(sql).df()
        return "DATA", sql, df
    except Exception as e:
        return "ERROR", sql, str(e)

# --- 3. UI (v15 Original) ---
st.set_page_config(layout="wide")
st.title("🏛️ L&T Analyst v15.7 (Reset)")

user_input = st.text_input("Analyze Data:")

if user_input:
    mode, sql, result = execute_ai_query(user_input)
    
    if mode == "DATA" and not result.empty:
        st.info(f"💡 Results Summary")
        t1, t2 = st.tabs(["📊 Dashboard", "🧾 Calculation Audit"])
        with t1:
            st.dataframe(result, use_container_width=True)
            if len(result) > 1:
                fig, ax = plt.subplots(figsize=(10, 4))
                ax.bar(result.iloc[:, 0].astype(str), result.iloc[:, -1], color='#00529B')
                st.pyplot(fig)
        with t2:
            st.code(sql, language="sql")
            st.dataframe(result)
    elif mode == "CHAT":
        st.write(result)
    else:
        st.error(f"Error: {result}")
        st.code(sql)
