import streamlit as st
import pandas as pd
import duckdb
import os
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

# --- 2. THE ANALYST ENGINE (v15 + Surgical Margin Fix) ---
def execute_ai_query(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # STEP 1: Intent (v15 Original)
    intent_prompt = f"Classify as 'DATA' or 'CHAT'. Input: {user_query}. Output only the word."
    intent = llm.invoke(intent_prompt).content.strip().upper()

    if "CHAT" in intent:
        return "CHAT", None, llm.invoke(user_query).content

    # STEP 2: The Logic Bible (Sourced from your directories)
    # We force the AI to respect the 'Segment' field and the 'Type' field separation
    analyst_system_prompt = """
    You are a Senior SQL Developer. 
    TABLES: 
    - pnl_data (Columns: Month, Segment, FinalCustomerName, Amount in USD, Type, Group1, Group3)
    - ut_data (Columns: Date, Segment, FinalCustomerName, PSNo, TotalBillableHours, NetAvailableHours)

    CRITICAL RULES:
    1. If the user asks for 'Margin %', 'Contribution Margin', or 'CM%', you MUST use this structure:
       WITH Rev AS (SELECT {Dimension}, SUM("Amount in USD") as r FROM pnl_data WHERE Type='Revenue' AND Group1 IN ('ONSITE','OFFSHORE','INDIRECT REVENUE') GROUP BY 1),
            Cost AS (SELECT {Dimension}, SUM("Amount in USD") as c FROM pnl_data WHERE Type='Cost' GROUP BY 1)
       SELECT Rev.{Dimension}, Rev.r as Revenue, Cost.c as Cost, ((Rev.r - Cost.c)/NULLIF(Rev.r, 0))*100 as Margin_Perc
       FROM Rev LEFT JOIN Cost ON Rev.{Dimension} = Cost.{Dimension}
    2. If the user mentions 'Segment', 'Industry', or 'Vertical', use the [Segment] column.
    3. If the user mentions 'FTE' or 'Headcount', use: COUNT(DISTINCT PSNo) FROM ut_data.
    4. Output ONLY the SQL. No intro text.
    """

    response = llm.invoke(f"{analyst_system_prompt}\n\nUser Question: {user_query}")
    sql = response.content.replace("```sql", "").replace("```", "").strip()
    
    # Surgical Cleanup: Removes any leading conversational words like "To" or "Certainly"
    if "WITH" in sql.upper():
        sql = "WITH" + sql.split("WITH", 1)[1]
    elif "SELECT" in sql.upper():
        sql = "SELECT" + sql.split("SELECT", 1)[1]

    try:
        result = conn.execute(sql).df()
        return "DATA", sql, result
    except Exception as e:
        return "ERROR", sql, str(e)

# --- 3. UI (v15 Original) ---
st.set_page_config(layout="wide")
st.title("🏛️ L&T Executive Analyst v15-Fixed")

user_input = st.text_input("How can I assist you with P&L or UT data?")

if user_input:
    mode, sql, result = execute_ai_query(user_input)
    
    if mode == "CHAT":
        st.write(result)
    elif mode == "DATA":
        if isinstance(result, pd.DataFrame) and not result.empty:
            # v15 Insights
            avg_val = result.iloc[:, -1].mean()
            max_val = result.iloc[:, -1].max()
            st.info(f"💡 **Insights:** Average: **{avg_val:,.2f}** | Peak: **{max_val:,.2f}**")

            tab1, tab2 = st.tabs(["📊 Dashboard", "🧾 Calculation Details"])
            
            with tab1:
                st.dataframe(result, use_container_width=True)
                if len(result) > 1:
                    fig, ax = plt.subplots(figsize=(10, 4))
                    # Use first column for X, last for Y
                    ax.bar(result.iloc[:, 0].astype(str), result.iloc[:, -1], color='#00529B')
                    plt.xticks(rotation=45)
                    st.pyplot(fig)

            with tab2:
                st.markdown("### 🔍 Calculation Audit")
                st.write("Generated SQL Query:")
                st.code(sql, language="sql")
                st.write("Full Underlying Data:")
                st.dataframe(result)
        else:
            st.warning("No data found for this query.")
    else:
        st.error(f"SQL Error: {result}")
        st.code(sql)
