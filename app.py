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

# --- 2. THE ANALYST ENGINE (v15 + HARD-CODED MARGIN LOGIC) ---

def clean_sql(raw_sql):
    """Protects against 'Certainly', 'To', and conversational leaks"""
    clean = re.sub(r"```sql|```", "", raw_sql).strip()
    match = re.search(r"\b(WITH|SELECT)\b", clean, re.IGNORECASE)
    if match:
        return clean[match.start():]
    return clean

def execute_ai_query(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # Classification
    intent_prompt = f"Classify as 'DATA' or 'CHAT'. Input: {user_query}. Output one word."
    intent = llm.invoke(intent_prompt).content.strip().upper()

    if "CHAT" in intent:
        return "CHAT", None, llm.invoke(user_query).content

    # --- SPECIAL MARGIN LOGIC BLOCK ---
    is_margin_query = any(x in user_query.lower() for x in ["margin", "cm%", "profit", "cm %"])
    
    if is_margin_query:
        # We use the LLM ONLY to extract parameters, not to write the structure
        param_prompt = f"""
        User Query: {user_query}
        Identify:
        1. Dimension: 'Segment' (for Industry/Vertical) or 'FinalCustomerName' (for Accounts). Default: 'FinalCustomerName'.
        2. Date Filter: DuckDB SQL where clause for 'Month' column (e.g., Month = '2025-06-01').
        3. Threshold: Numeric value for filtering (e.g., 30 for < 30%). Default: None.
        Output format: Dimension | DateFilter | Threshold
        """
        params = llm.invoke(param_prompt).content.strip().split("|")
        dim = params[0].strip() if len(params) > 0 else "FinalCustomerName"
        date_filt = params[1].strip() if len(params) > 1 else "1=1"
        threshold = params[2].strip() if len(params) > 2 and "None" not in params[2] else ""

        # Use the PROVEN SQL Template
        sql = f"""
        WITH Rev AS (
            SELECT "{dim}", SUM("Amount in USD") as r_val 
            FROM pnl_data 
            WHERE Type = 'Revenue' AND Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE') AND {date_filt}
            GROUP BY 1
        ),
        Cost AS (
            SELECT "{dim}", SUM("Amount in USD") as c_val 
            FROM pnl_data 
            WHERE Type = 'Cost' AND {date_filt}
            GROUP BY 1
        )
        SELECT 
            Rev."{dim}", 
            Rev.r_val as Revenue, 
            COALESCE(Cost.c_val, 0) as Total_Cost, 
            ((Rev.r_val - COALESCE(Cost.c_val, 0)) / NULLIF(Rev.r_val, 0)) * 100 as Margin_Perc
        FROM Rev 
        LEFT JOIN Cost ON Rev."{dim}" = Cost."{dim}"
        {f"WHERE ((Rev.r_val - COALESCE(Cost.c_val, 0)) / NULLIF(Rev.r_val, 0)) * 100 < {threshold}" if threshold else ""}
        ORDER BY Margin_Perc ASC;
        """
    else:
        # Standard v15 Logic for FTE, Revenue alone, etc.
        system_rules = """
        Use pnl_data (Month, Segment, FinalCustomerName, Amount in USD, Type, Group1) 
        or ut_data (Date, PSNo, Segment, TotalBillableHours).
        If FTE, use COUNT(DISTINCT PSNo).
        Output ONLY SQL.
        """
        response = llm.invoke(f"{system_rules}\n\nQuestion: {user_query}")
        sql = clean_sql(response.content)

    try:
        df = conn.execute(sql).df()
        return "DATA", sql, df
    except Exception as e:
        return "ERROR", sql, str(e)

# --- 3. UI (v15 Preserved) ---
st.set_page_config(layout="wide")
st.title("🏛️ L&T Analyst v15.2 (Surgical Fix)")

user_input = st.text_input("Ask about Margin %, FTE, or Revenue:")

if user_input:
    mode, sql, result = execute_ai_query(user_input)
    
    if mode == "CHAT":
        st.write(result)
    elif mode == "DATA":
        if not result.empty:
            avg_val = result.iloc[:, -1].mean()
            st.info(f"💡 **Analysis Result:** Average: **{avg_val:,.2f}**")

            tab1, tab2 = st.tabs(["📊 Dashboard", "🧾 Calculation Audit"])
            with tab1:
                st.dataframe(result, use_container_width=True)
                if len(result) > 1:
                    fig, ax = plt.subplots(figsize=(10, 4))
                    ax.bar(result.iloc[:, 0].astype(str), result.iloc[:, -1], color='#00529B')
                    plt.xticks(rotation=45)
                    st.pyplot(fig)
            with tab2:
                st.markdown("### 🔍 Calculation Audit")
                st.write("**Formula Used:** ((Revenue - Total_Cost) / Revenue) * 100")
                st.write("**Generated SQL:**")
                st.code(sql, language="sql")
                st.write("**Raw Component Data:**")
                st.dataframe(result)
        else:
            st.warning("No data found for this specific query.")
    else:
        st.error(f"Execution Error: {result}")
        st.code(sql)
