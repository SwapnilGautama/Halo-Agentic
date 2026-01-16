import streamlit as st
import pandas as pd
import duckdb
import os
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- 1. DATA ENGINE (Load exact headers) ---
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

# --- 2. THE ANALYST ENGINE (v11.0) ---
def execute_ai_query(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # System prompt updated with Segment logic and Greeting handling
    system_prompt = """
    You are an Executive Financial Assistant for L&T. 
    
    CAPABILITIES:
    1. Answer greetings and explain your purpose (analyzing P&L and Utilization data).
    2. Generate SQL queries for financial KPIs.
    
    TABLES:
    - pnl_data: [Month, FinalCustomerName, "Amount in USD", Type, Group1, Group3, Segment]
    - ut_data: [Date, FinalCustomerName, PSNo, TotalBillableHours, NetAvailableHours, Segment]

    FIELD MAPPING RULES:
    - If user asks for 'Segment' with 'Utilization' or 'FTE', use ut_data.Segment.
    - If user asks for 'Segment' with 'Revenue' or 'Cost', use pnl_data.Segment.
    - If a query needs BOTH tables (RPP, Billed Rate, etc.), JOIN on:
      pnl_data.FinalCustomerName = ut_data.FinalCustomerName 
      AND STRFTIME(pnl_data.Month, '%Y-%m') = STRFTIME(ut_data.Date, '%Y-%m')

    OUTPUT FORMAT:
    - For GREETINGS: Return a friendly text response.
    - For DATA QUERIES: Return ONLY the SQL query. Always select: [Dimension, Numerator, Denominator, Final_Result].
    """
    
    response = llm.invoke(system_prompt + f"\nUser Input: {user_query}")
    content = response.content.strip()
    
    # Check if the response is a SQL query or a conversational response
    if "SELECT" in content.upper() and "FROM" in content.upper():
        sql = content.replace("```sql", "").replace("```", "")
        try:
            df = conn.execute(sql).df()
            return "DATA", sql, df
        except Exception as e:
            return "ERROR", sql, f"SQL Error: {str(e)}"
    else:
        return "CHAT", None, content

# --- 3. UI LAYOUT ---
st.set_page_config(layout="wide", page_title="L&T Analyst v11")
st.title("🏛️ L&T Executive Analyst v11.0")

query = st.text_input("How can I help you today?")

if query:
    mode, sql, result = execute_ai_query(query)
    
    if mode == "CHAT":
        st.write(result)
        
    elif mode == "DATA" and isinstance(result, pd.DataFrame):
        # --- Point 4: RESTORED 2-POINT INSIGHTS ---
        if not result.empty:
            avg_val = result.iloc[:, -1].mean()
            max_row = result.loc[result.iloc[:, -1].idxmax()]
            
            st.info(f"💡 **Executive Insights:**\n"
                    f"1. The average result for this period is **{avg_val:,.2f}**.\n"
                    f"2. Peak performance was observed in **{max_row.iloc[0]}** with a value of **{max_row.iloc[-1]:,.2f}**.")

        tab1, tab2 = st.tabs(["📊 Dashboard", "🧾 Calculation Details"])
        
        with tab1:
            st.dataframe(result.iloc[:, [0, -1]])
            if len(result) > 1:
                fig, ax = plt.subplots(figsize=(10, 4))
                ax.plot(result.iloc[:, 0].astype(str), result.iloc[:, -1], marker='o', color='#00529B')
                plt.xticks(rotation=45)
                st.pyplot(fig)

        with tab2:
            st.markdown("### 🔍 Calculation Audit")
            st.code(sql, language="sql")
            st.write("**Full Raw Data Table:**")
            st.dataframe(result)
            
    elif mode == "ERROR":
        st.error(result)
        st.code(sql)
