import streamlit as st
import pandas as pd
import duckdb
import os
import re
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- 1. DATA ENGINE (v15 Original - Untouched) ---
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

# --- 2. THE ANALYST ENGINE (v15 + Surgical Margin Logic) ---
def execute_ai_query(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # Classification (v15 Original)
    intent_prompt = f"Classify as 'DATA' or 'CHAT'. Input: {user_query}. Output only the word."
    intent = llm.invoke(intent_prompt).content.strip().upper()

    if "CHAT" in intent:
        return "CHAT", None, llm.invoke(user_query).content

    # DETECT MARGIN QUESTIONS
    is_margin = any(word in user_query.lower() for word in ["margin", "profit %", "cm%", "cm %"])

    if is_margin:
        # Step A: Use AI to extract filters only (Not the SQL)
        extract_prompt = f"""
        Extract from: "{user_query}"
        1. Dimension: 'Segment' or 'FinalCustomerName'.
        2. Date: Month filter (e.g., Month = '2025-06-01').
        3. Filter: Any threshold (e.g., 30 for < 30%).
        Output format: Dim | Date | Threshold
        """
        params = llm.invoke(extract_prompt).content.strip().split("|")
        dim = params[0].strip() if len(params) > 0 else "FinalCustomerName"
        date_clause = params[1].strip() if len(params) > 1 else "1=1"
        limit = params[2].strip() if "None" not in params[2] else ""

        # Step B: The "Colleague Logic" Template
        # We bucket Revenue and Cost separately then Join them.
        sql = f"""
        WITH RevBucket AS (
            SELECT "{dim}", SUM("Amount in USD") as rev_val 
            FROM pnl_data 
            WHERE Type = 'Revenue' AND Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE') AND {date_clause}
            GROUP BY 1
        ),
        CostBucket AS (
            SELECT "{dim}", SUM("Amount in USD") as cost_val 
            FROM pnl_data 
            WHERE Type = 'Cost' AND {date_clause}
            GROUP BY 1
        )
        SELECT 
            r."{dim}", 
            r.rev_val as Revenue, 
            COALESCE(c.cost_val, 0) as Total_Cost, 
            ((r.rev_val - COALESCE(c.cost_val, 0)) / NULLIF(r.rev_val, 0)) * 100 as Margin_Perc
        FROM RevBucket r
        LEFT JOIN CostBucket c ON r."{dim}" = c."{dim}"
        {f"WHERE ((r.rev_val - COALESCE(c.cost_val, 0)) / NULLIF(r.rev_val, 0)) * 100 < {limit}" if limit else ""}
        ORDER BY Margin_Perc ASC;
        """
    else:
        # FALLBACK: Original v15 Logic for FTE/Revenue/Utilization
        fallback_prompt = f"Generate DuckDB SQL for: {user_query}. Tables: pnl_data, ut_data. Output ONLY SQL."
        sql_raw = llm.invoke(fallback_prompt).content
        # SQL Shield: Strip away 'To', 'Certainly', or Markdown
        sql = re.sub(r"```sql|```", "", sql_raw).strip()
        sql_match = re.search(r"\b(SELECT|WITH)\b", sql, re.IGNORECASE)
        if sql_match:
            sql = sql[sql_match.start():]

    try:
        df = conn.execute(sql).df()
        return "DATA", sql, df
    except Exception as e:
        return "ERROR", sql, str(e)

# --- 3. UI (v15 Original Layout) ---
st.set_page_config(layout="wide")
st.title("🏛️ L&T Executive Analyst v15.5")

q = st.text_input("Analyze your data (FTE, Revenue, or Margin %):")

if q:
    mode, sql, result = execute_ai_query(q)
    
    if mode == "DATA" and not result.empty:
        st.info(f"💡 Period Average: **{result.iloc[:,-1].mean():,.2f}**")
        t1, t2 = st.tabs(["📊 Dashboard", "🧾 Calculation Audit"])
        with t1:
            st.dataframe(result, use_container_width=True)
            if len(result) > 1:
                fig, ax = plt.subplots(figsize=(10, 4))
                ax.bar(result.iloc[:, 0].astype(str), result.iloc[:, -1], color='#00529B')
                plt.xticks(rotation=45)
                st.pyplot(fig)
        with t2:
            st.code(sql, language="sql")
            st.dataframe(result)
    elif mode == "CHAT":
        st.write(result)
    else:
        st.error(f"Execution Error. Query attempted: {sql}")
