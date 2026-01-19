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

# --- 2. THE ANALYST ENGINE (Surgical Margin Insertion) ---
def execute_ai_query(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # Preserve v15 Intent Classification
    intent_prompt = f"Classify as 'DATA' or 'CHAT'. Input: {user_query}. Output only the word."
    intent = llm.invoke(intent_prompt).content.strip().upper()

    if "CHAT" in intent:
        return "CHAT", None, llm.invoke(user_query).content

    # CHECK: Is this a Margin question?
    is_margin = any(word in user_query.lower() for word in ["margin", "profit %", "cm%", "cm %"])

    if is_margin:
        # SURGICAL ADDITION: Use LLM only to extract filters, then plug into a hard-coded safe template
        extract_prompt = f"""
        Extract from query: "{user_query}"
        1. Dimension: 'Segment' or 'FinalCustomerName' or 'Month'.
        2. DateFilter: SQL condition for 'Month' column (e.g., Month = '2025-06-01').
        3. Threshold: Number if user says "less than X", otherwise 'None'.
        Output: Dimension | DateFilter | Threshold
        """
        params = llm.invoke(extract_prompt).content.strip().split("|")
        dim = params[0].strip() if len(params) > 0 else "FinalCustomerName"
        date_clause = params[1].strip() if len(params) > 1 else "1=1"
        limit = params[2].strip() if "None" not in params[2] else ""

        # THE PROVEN MARGIN TEMPLATE
        sql = f"""
        WITH Rev AS (
            SELECT "{dim}", SUM("Amount in USD") as r FROM pnl_data 
            WHERE Type='Revenue' AND Group1 IN ('ONSITE','OFFSHORE','INDIRECT REVENUE') AND {date_clause} GROUP BY 1
        ),
        Cost AS (
            SELECT "{dim}", SUM("Amount in USD") as c FROM pnl_data 
            WHERE Type='Cost' AND {date_clause} GROUP BY 1
        )
        SELECT 
            Rev."{dim}", 
            Rev.r as Revenue, 
            COALESCE(Cost.c, 0) as Total_Cost, 
            ((Rev.r - COALESCE(Cost.c, 0)) / NULLIF(Rev.r, 0)) * 100 as Margin_Perc
        FROM Rev LEFT JOIN Cost ON Rev."{dim}" = Cost."{dim}"
        {f"WHERE ((Rev.r - COALESCE(Cost.c, 0)) / NULLIF(Rev.r, 0)) * 100 < {limit}" if limit else ""}
        ORDER BY Margin_Perc ASC;
        """
    else:
        # FALLBACK: Original v15 Logic for FTE, Revenue, etc.
        fallback_prompt = f"""
        Generate SQL for: {user_query}. 
        pnl_data (Month, Segment, FinalCustomerName, Amount in USD, Type, Group1)
        ut_data (Date, PSNo, Segment, TotalBillableHours)
        - For FTE use COUNT(DISTINCT PSNo). 
        - Output ONLY the SQL starting with SELECT.
        """
        sql_raw = llm.invoke(fallback_prompt).content
        # Clean 'Certainly' or 'To'
        sql = re.sub(r"```sql|```", "", sql_raw).strip()
        sql_match = re.search(r"\b(SELECT|WITH)\b", sql, re.IGNORECASE)
        if sql_match: sql = sql[sql_match.start():]

    try:
        df = conn.execute(sql).df()
        return "DATA", sql, df
    except Exception as e:
        return "ERROR", sql, str(e)

# --- 3. UI (v15 Original Layout) ---
st.set_page_config(layout="wide")
st.title("🏛️ L&T Analyst v15-SurgicallyFixed")

user_input = st.text_input("Ask a question (e.g., 'FTE by Segment' or 'Margin % by Account < 30'):")

if user_input:
    mode, sql, result = execute_ai_query(user_input)
    
    if mode == "DATA" and not result.empty:
        st.info(f"💡 **Insights:** Average: **{result.iloc[:,-1].mean():,.2f}**")
        t1, t2 = st.tabs(["📊 Dashboard", "🧾 Calculation Details"])
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
        st.error(f"Error or No Data. Query: {sql}")
