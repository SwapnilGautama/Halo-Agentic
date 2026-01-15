import streamlit as st
import pandas as pd
import duckdb
import plotly.express as px
import os
from langchain_openai import ChatOpenAI

st.set_page_config(page_title="L&T Financial Multi-Agent", layout="wide")
st.title("🤖 L&T AI Financial Analyst")

# 1. DATABASE & KPI DIRECTORY INITIALIZATION
@st.cache_resource
def init_system():
    conn = duckdb.connect(database=':memory:')
    
    # Load Data Tables
    files = {"pnl_data": "pnl_data.xlsx", "ut_data": "ut_data.xlsx"}
    for table, path in files.items():
        if os.path.exists(path):
            df = pd.read_excel(path, engine="openpyxl")
            conn.register("tmp", df)
            conn.execute(f"CREATE TABLE {table} AS SELECT * FROM tmp")
    
    # Load KPI Directory as a "Knowledge Base" string
    kpi_context = "No KPI directory found."
    if os.path.exists("kpi_directory.xlsx"):
        df_kpi = pd.read_excel("kpi_directory.xlsx", engine="openpyxl")
        kpi_context = df_kpi.to_string()
        
    return conn, kpi_context

conn, kpi_rules = init_system()

# --- SIDEBAR: DATA DICTIONARY & KPI RULES ---
with st.sidebar:
    st.header("📖 System Knowledge")
    with st.expander("View KPI Rulebook"):
        st.text(kpi_rules)
    st.info("The Architect Agent references these rules for every calculation.")

# --- CHAT HISTORY UI ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# Show history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "df" in message: st.dataframe(message["df"])
        if "fig" in message: st.plotly_chart(message["fig"])

# --- EXECUTION ---
if prompt := st.chat_input("Ask: What is the FTE trend over months?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        llm = ChatOpenAI(model="gpt-4o", temperature=0)
        
        # THE ARCHITECT'S PROMPT (Using the KPI Directory)
        architect_instruction = f"""
        You are the Architect Agent. You must use the following KPI definitions to answer the user.
        
        KPI DEFINITIONS FROM DIRECTORY:
        {kpi_rules}
        
        USER QUESTION: {prompt}
        
        TASK: Write a DuckDB SQL query. 
        - If the question involves FTE, use the formula: SUM("Allocation%")/100.
        - Ensure month names are sorted chronologically.
        - Use double quotes for column names with spaces.
        Return ONLY the SQL code.
        """
        
        sql = llm.invoke(architect_instruction).content.replace("```sql", "").replace("```", "").strip()
        
        try:
            # Execute Analyst & Reviewer Task
            df = conn.execute(sql).df()
            
            # Visualizer Task
            narrative = llm.invoke(f"Based on these results: {df.to_string()}, provide a CFO-level analysis.").content
            st.markdown(narrative)
            st.dataframe(df)
            
            fig = px.line(df, x=df.columns[0], y=df.columns[1], title="KPI Analysis Trend", markers=True)
            st.plotly_chart(fig)
            
            # Save for memory
            st.session_state.messages.append({"role": "assistant", "content": narrative, "df": df, "fig": fig})
            
        except Exception as e:
            st.error(f"Calculation Error: {e}")
            st.code(sql)
