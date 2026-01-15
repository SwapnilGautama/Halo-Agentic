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
    
    # Load KPI Directory as a Dictionary for the Architect
    kpi_dict = {}
    if os.path.exists("kpi_directory.xlsx"):
        df_kpi = pd.read_excel("kpi_directory.xlsx", engine="openpyxl")
        # Assuming columns: 'KPI Name' and 'Formula/Logic'
        for _, row in df_kpi.iterrows():
            kpi_dict[str(row[0]).lower()] = str(row[1])
            
    return conn, kpi_dict

conn, kpi_rules_dict = init_system()

# --- SIDEBAR: SYSTEM KNOWLEDGE ---
with st.sidebar:
    st.header("📖 KPI Master Directory")
    if kpi_rules_dict:
        for kpi, logic in kpi_rules_dict.items():
            st.write(f"**{kpi.upper()}**: `{logic}`")
    else:
        st.warning("KPI Directory empty or not found.")

# --- CHAT HISTORY UI ---
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "df" in message: st.dataframe(message["df"])
        if "fig" in message: st.plotly_chart(message["fig"])

# --- EXECUTION ---
if prompt := st.chat_input("Ask: What is the FTE trend?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        llm = ChatOpenAI(model="gpt-4o", temperature=0)
        
        # THE ARCHITECT: Finding matching KPIs
        matched_kpis = [f"{k}: {v}" for k, v in kpi_rules_dict.items() if k in prompt.lower()]
        kpi_context_str = "\n".join(matched_kpis) if matched_kpis else "No specific KPI matched. Use standard financial logic."

        # THE ARCHITECT'S MANDATORY INSTRUCTIONS 
        architect_instruction = f"""
        You are the Architect Agent. You MUST follow these specific business rules found in our directory:
        
        MATCHED BUSINESS RULES:
        {kpi_context_str}
        
        USER QUESTION: {prompt}
        
        MANDATORY SQL RULES:
        1. If 'FTE' is mentioned, you MUST use SUM("Allocation%")/100.0.
        2. Use the 'ut_data' table for utilization/headcount.
        3. Use the 'pnl_data' table for revenue/cost.
        4. Return ONLY the SQL code.
        """
        
        sql = llm.invoke(architect_instruction).content.replace("```sql", "").replace("```", "").strip()
        
        try:
            df = conn.execute(sql).df()
            
            # Show the SQL so you can see it's using the KPI logic
            with st.expander("View Architect's SQL"):
                st.code(sql)
                
            narrative = llm.invoke(f"Analyze this: {df.to_string()}").content
            st.markdown(narrative)
            st.dataframe(df)
            
            if not df.empty and len(df.columns) >= 2:
                fig = px.line(df, x=df.columns[0], y=df.columns[1], title="L&T Financial Analysis", markers=True)
                st.plotly_chart(fig)
            
            st.session_state.messages.append({"role": "assistant", "content": narrative, "df": df})
            
        except Exception as e:
            st.error(f"Error: {e}")
            st.code(sql)
