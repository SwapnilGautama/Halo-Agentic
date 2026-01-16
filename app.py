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
        # Ensure date format and remove whitespace
        df_pnl['Month'] = pd.to_datetime(df_pnl['Month'], errors='coerce')
        conn.register("pnl_data", df_pnl)

    if os.path.exists("ut_data.xlsx"):
        df_ut = pd.read_excel("ut_data.xlsx")
        df_ut['Date'] = pd.to_datetime(df_ut['Date'], errors='coerce')
        conn.register("ut_data", df_ut)

    return conn

conn = load_data()

# --- 2. THE ANALYST ENGINE (v15.0) ---
def execute_ai_query(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # STEP 1: Intent Classification
    intent_prompt = f"Classify the user input as 'DATA' or 'CHAT'. Input: {user_query}. Output only the word."
    intent = llm.invoke(intent_prompt).content.strip().upper()

    if 'CHAT' in intent:
        chat_prompt = f"You are the L&T Executive Assistant. Briefly explain that you can calculate Revenue, Costs, C&B %, and Utilization across Segments and Customers. User: {user_query}"
        return "CHAT", None, llm.invoke(chat_prompt).content

    # STEP 2: DATA PATH (Precise Logic)
    system_prompt = """
    You are an expert SQL generator for DuckDB.
    
    TABLE SCHEMA:
    - pnl_data: [Month, FinalCustomerName, "Amount in USD", Type, Group1, Group3, Segment]
    - ut_data: [Date, FinalCustomerName, PSNo, TotalBillableHours, NetAvailableHours, Segment]

    DATA VALUE MAPPING (STRICT):
    - C&B Cost: SUM("Amount in USD") WHERE Group3 IN ('C&B - Onsite Total', 'C&B Cost - Offshore') AND Type = 'Cost'
    - Revenue: SUM("Amount in USD") WHERE Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE')
    - Utilization %: (SUM(TotalBillableHours) / NULLIF(SUM(NetAvailableHours), 0)) * 100
    - FTE / Headcount: COUNT(DISTINCT PSNo)

    RULES:
    1. If a query needs BOTH tables, join on FinalCustomerName AND Month (STRFTIME '%Y-%m').
    2. Column Aliasing: Use descriptive names like CB_Cost, Revenue, Billable_Hours instead of generic 'Numerator'.
    3. Always select columns in this order: [Dimension, Component_1, Component_2, Final_Result].
    4. For dates like 'June 2025', use '2025-06-01'.

    Return ONLY the SQL block.
    """
    
    response = llm.invoke(system_prompt + f"\nUser Query: {user_query}")
    sql = response.content.strip().replace("```sql", "").replace("```", "")
    
    try:
        df = conn.execute(sql).df()
        return "DATA", sql, df
    except Exception as e:
        return "ERROR", sql, str(e)

# --- 3. UI LAYOUT ---
st.set_page_config(layout="wide")
st.title("🏛️ L&T Executive Analyst v15.0")

user_input = st.text_input("Enter your query (e.g., 'C&B cost as % of revenue by segment for June 2025')")

if user_input:
    mode, sql, result = execute_ai_query(user_input)
    
    if mode == "CHAT":
        st.write(result)
        
    elif mode == "DATA":
        if isinstance(result, pd.DataFrame) and not result.empty:
            # 2-Point Insights
            avg_val = result.iloc[:, -1].mean()
            max_val = result.iloc[:, -1].max()
            st.info(f"💡 **Insights:** Period Average: **{avg_val:,.2f}** | Period Peak: **{max_val:,.2f}**")

            tab1, tab2 = st.tabs(["📊 Dashboard", "🧾 Calculation Details"])
            
            with tab1:
                # Show key result column (last one) and dimension (first one)
                display_df = result.iloc[:, [0, -1]]
                st.dataframe(display_df, use_container_width=True)
                
                if len(result) > 1:
                    fig, ax = plt.subplots(figsize=(10, 4))
                    ax.plot(result.iloc[:, 0].astype(str), result.iloc[:, -1], marker='o', color='#00529B', linewidth=2)
                    plt.xticks(rotation=45)
                    st.pyplot(fig)

            with tab2:
                st.markdown("### 🔍 Calculation Audit")
                st.write("This table shows the exact components used for the calculation:")
                st.dataframe(result, use_container_width=True)
                st.write("**Generated SQL Query:**")
                st.code(sql, language="sql")
        else:
            st.warning("No data found for this specific query. Please check filters like dates or names.")
            
    elif mode == "ERROR":
        st.error(f"Execution Error: {result}")
        st.code(sql)
