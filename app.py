import streamlit as st
import pandas as pd
import duckdb
import plotly.express as px
import os
from langchain_openai import ChatOpenAI

st.set_page_config(page_title="L&T Financial AI", layout="wide")
st.title("🏛️ L&T AI Financial Analyst")

# 1. DATABASE & KPI LOADING
@st.cache_resource
def init_system():
    conn = duckdb.connect(database=':memory:')
    kpi_map = {}
    if os.path.exists("kpi_directory.xlsx"):
        df_kpi = pd.read_excel("kpi_directory.xlsx", engine="openpyxl")
        # Creating a strict mapping: { "fte": "SUM(\"Allocation%\")/100.0" }
        for _, row in df_kpi.iterrows():
            kpi_map[str(row[0]).lower().strip()] = str(row[1])
    
    # Load Tables
    for f in ["pnl_data.xlsx", "ut_data.xlsx"]:
        if os.path.exists(f):
            t_name = f.replace(".xlsx", "")
            df = pd.read_excel(f, engine="openpyxl")
            conn.register("tmp", df)
            conn.execute(f"CREATE TABLE {t_name} AS SELECT * FROM tmp")
    return conn, kpi_map

conn, kpi_rules = init_system()

# 2. CHAT HISTORY UI
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "df" in msg: st.dataframe(msg["df"])

# 3. EXECUTION WITH HARD-CODED INJECTION
if prompt := st.chat_input("Ask: What is the FTE trend?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        llm = ChatOpenAI(model="gpt-4o", temperature=0)
        
        # --- PRE-PROCESSOR: KPI ENFORCEMENT ---
        enforced_logic = ""
        for kpi, formula in kpi_rules.items():
            if kpi in prompt.lower():
                enforced_logic += f"\n- MANDATORY: For '{kpi}', you MUST use this math: {formula}"

        # THE ARCHITECT PROMPT 
        architect_prompt = f"""
        You are the Architect. Use DuckDB SQL.
        TABLES: ut_data (utilization), pnl_data (financials).
        {enforced_logic}
        
        STRICT RULES:
        1. Use double quotes for columns with spaces.
        2. Group by "Month" and sort correctly.
        3. Return ONLY the SQL code.
        """
        
        sql = llm.invoke(architect_prompt + f"\nQuestion: {prompt}").content.strip().replace("```sql", "").replace("```", "")
        
        try:
            # Step 2: Reviewer & Execution
            df = conn.execute(sql).df()
            
            # Step 3: Visualizer Narrative
            res = llm.invoke(f"Summarize this: {df.to_string()}").content
            st.markdown(res)
            st.dataframe(df)
            
            if not df.empty and len(df.columns) >= 2:
                st.plotly_chart(px.line(df, x=df.columns[0], y=df.columns[1], markers=True))
            
            st.session_state.messages.append({"role": "assistant", "content": res, "df": df})
            
        except Exception as e:
            st.error(f"SQL Error: {e}")
            st.code(sql) # Show the bad SQL so we can see the formula it tried
