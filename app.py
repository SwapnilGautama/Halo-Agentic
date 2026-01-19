import streamlit as st
import pandas as pd
import duckdb
import os
import re
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- 1. DATA ENGINE (v15 Original) ---
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

# --- 2. THE ANALYST ENGINE (v15 + Ratio Logic Fix) ---
def execute_ai_query(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # Classification (Preserving v15 Intent)
    intent_prompt = f"Classify as 'DATA' or 'CHAT'. User: {user_query}. Output one word."
    intent = llm.invoke(intent_prompt).content.strip().upper()

    if "CHAT" in intent:
        return "CHAT", None, llm.invoke(user_query).content

    # The Bible Context for the AI
    system_rules = """
    You are a Financial SQL expert. 
    TABLE: pnl_data (Columns: Month, Segment, FinalCustomerName, Amount in USD, Type, Group1)
    TABLE: ut_data (Columns: Date, PSNo, Segment, TotalBillableHours, NetAvailableHours)

    CRITICAL RATIO RULES:
    1. For 'Margin %' or 'Contribution Margin', you MUST use this bucket logic:
       WITH Rev AS (SELECT {Dim}, SUM("Amount in USD") as r FROM pnl_data WHERE Type='Revenue' AND Group1 IN ('ONSITE','OFFSHORE','INDIRECT REVENUE') GROUP BY 1),
            Cost AS (SELECT {Dim}, SUM("Amount in USD") as c FROM pnl_data WHERE Type='Cost' GROUP BY 1)
       SELECT Rev.{Dim}, Rev.r as Revenue, Cost.c as Cost, ((Rev.r - Cost.c)/NULLIF(Rev.r, 0))*100 as Margin_Perc
       FROM Rev LEFT JOIN Cost ON Rev.{Dim} = Cost.{Dim}
    
    2. If the user asks for 'Segment', use the [Segment] column.
    3. Output ONLY the SQL code. Start with 'WITH' or 'SELECT'.
    """

    response = llm.invoke(f"{system_rules}\n\nQuestion: {user_query}")
    sql_raw = response.content.replace("```sql", "").replace("```", "").strip()
    
    # SHIELD: Remove "Certainly", "To", or any text before the SQL starts
    sql_match = re.search(r"\b(WITH|SELECT)\b", sql_raw, re.IGNORECASE)
    if sql_match:
        sql = sql_raw[sql_match.start():]
    else:
        sql = sql_raw

    try:
        df = conn.execute(sql).df()
        return "DATA", sql, df
    except Exception as e:
        return "ERROR", sql, str(e)

# --- 3. UI (v15 Preserved Layout) ---
st.set_page_config(layout="wide")
st.title("🏛️ L&T Analyst v15.1 (Fixed)")

user_input = st.text_input("Analyze P&L (Margin, Revenue, Cost) or UT (FTE, Utilization):")

if user_input:
    mode, sql, result = execute_ai_query(user_input)
    
    if mode == "CHAT":
        st.write(result)
    elif mode == "DATA":
        if not result.empty:
            # Insights
            avg_val = result.iloc[:, -1].mean()
            st.info(f"💡 **Analysis Result:** Average across selected items: **{avg_val:,.2f}**")

            tab1, tab2 = st.tabs(["📊 Dashboard", "🧾 Calculation Audit"])
            
            with tab1:
                # Show Segment/Account and the final metric
                st.dataframe(result, use_container_width=True)
                if len(result) > 1:
                    fig, ax = plt.subplots(figsize=(10, 4))
                    ax.bar(result.iloc[:, 0].astype(str), result.iloc[:, -1], color='#00529B')
                    plt.xticks(rotation=45)
                    st.pyplot(fig)

            with tab2:
                st.code(sql, language="sql")
                st.write("Full Component Data:")
                st.dataframe(result)
        else:
            st.warning("No records matched your criteria.")
    else:
        st.error(f"SQL Error: {result}")
        st.code(sql)
