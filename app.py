import streamlit as st
import pandas as pd
import duckdb
import plotly.express as px
import os
from langchain_openai import ChatOpenAI

st.set_page_config(page_title="L&T Financial Multi-Agent", layout="wide")
st.title("🤖 L&T AI Financial Analyst")

# 1. DATABASE & KPI LOADING (Targeted at your specific CSV structure)
@st.cache_resource
def init_system():
    conn = duckdb.connect(database=':memory:')
    
    # Load Tables
    for f in ["pnl_data.xlsx", "ut_data.xlsx"]:
        if os.path.exists(f):
            df = pd.read_excel(f, engine="openpyxl")
            conn.register("tmp", df)
            conn.execute(f"CREATE TABLE {f.replace('.xlsx', '')} AS SELECT * FROM tmp")

    # Load KPI Rules - We look for the "Head Count / FTE" row
    kpi_map = {}
    if os.path.exists("kpi_directory.xlsx"):
        df_kpi = pd.read_excel("kpi_directory.xlsx", engine="openpyxl")
        # Search for the row containing "FTE"
        fte_row = df_kpi[df_kpi.iloc[:, 0].str.contains("FTE", na=False, case=False)]
        if not fte_row.empty:
            # We explicitly map FTE to the formula in your file: Distinct Count of PSNo
            kpi_map["fte"] = 'COUNT(DISTINCT "PSNo")'
            kpi_map["headcount"] = 'COUNT(DISTINCT "PSNo")'
            
    return conn, kpi_map

conn, kpi_rules = init_system()

# 2. UI & HISTORY
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 3. EXECUTION
if prompt := st.chat_input("What is the FTE trend over months?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        llm = ChatOpenAI(model="gpt-4o", temperature=0)
        
        # ARCHITECT: Forcing the formula from YOUR file
        selected_formula = kpi_rules.get("fte", 'COUNT(DISTINCT "PSNo")')
        
        sql_prompt = f"""
        You are an L&T Financial Analyst. Use table 'ut_data'.
        
        BUSINESS RULE:
        - The formula for FTE or Head Count is MANDATORY: {selected_formula}
        
        SQL RULES:
        1. Group by "Month".
        2. Column "PSNo" must be in double quotes.
        3. Return ONLY the SQL.
        """
        
        sql = llm.invoke(sql_prompt + f"\nQuestion: {prompt}").content.strip()
        sql = sql.replace("```sql", "").replace("```", "").strip()
        
        try:
            df = conn.execute(sql).df()
            
            # CFO Narrative
            narrative = llm.invoke(f"Analyze this trend: {df.to_string()}").content
            st.markdown(narrative)
            st.dataframe(df)
            
            # Show the math used for transparency
            st.info(f"Calculated using Business Rule: `{selected_formula}`")
            
            if not df.empty:
                fig = px.line(df, x=df.columns[0], y=df.columns[1], markers=True, title="FTE Trend")
                st.plotly_chart(fig)
            
            st.session_state.messages.append({"role": "assistant", "content": narrative})
            
        except Exception as e:
            st.error(f"SQL Error: {e}")
            st.code(sql)
