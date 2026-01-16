import streamlit as st
import pandas as pd
import duckdb
import plotly.express as px
import os
from langchain_openai import ChatOpenAI

# --- PAGE CONFIG ---
st.set_page_config(page_title="L&T Financial Multi-Agent", layout="wide")
st.title("🏛️ L&T AI Financial System")

# 1. DATABASE & DIRECTORY INITIALIZATION
@st.cache_resource
def init_system():
    # FIX: Use ':memory:' to avoid "Connection Error: Can't open connection to same database"
    conn = duckdb.connect(database=':memory:')
    
    # LOAD FIELD DIRECTORY (Semantic Bridge)
    field_rules = ""
    if os.path.exists("field_directory.xlsx"):
        df_fields = pd.read_excel("field_directory.xlsx")
        field_rules = df_fields.to_string(index=False)
    
    # LOAD KPI DIRECTORY (Formula Logic)
    kpi_map = {}
    if os.path.exists("kpi_directory.xlsx"):
        df_kpi = pd.read_excel("kpi_directory.xlsx")
        # Extract FTE/Headcount Rule (Count of PSNo)
        fte_row = df_kpi[df_kpi.iloc[:, 0].str.contains("FTE|Head Count", na=False, case=False)]
        if not fte_row.empty:
            kpi_map["fte"] = 'COUNT(DISTINCT "PSNo")'
            kpi_map["headcount"] = 'COUNT(DISTINCT "PSNo")'
        # Extract Utilization Rule
        ut_row = df_kpi[df_kpi.iloc[:, 0].str.contains("Utilization", na=False, case=False)]
        if not ut_row.empty:
            kpi_map["utilization"] = 'SUM("TotalBillableHours") / NULLIF(SUM("NetAvailableHours"), 0)'

    # LOAD & STANDARDIZE TABLES (Handling Month Ambiguity)
    # 
    if os.path.exists("ut_data.xlsx"):
        df_ut = pd.read_excel("ut_data.xlsx")
        cols = list(df_ut.columns)
        # Rename duplicate month columns: Col 2 is Num, Last Col is Label
        cols[1] = "Month_Num" 
        cols[-1] = "Month_Label"
        df_ut.columns = cols
        conn.register("ut_tmp", df_ut)
        conn.execute("CREATE TABLE ut_data AS SELECT * FROM ut_tmp")

    if os.path.exists("pnl_data.xlsx"):
        df_pnl = pd.read_excel("pnl_data.xlsx")
        df_pnl.rename(columns={"Month": "Month_Label"}, inplace=True)
        # Add sorting logic for P&L months
        m_map = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}
        if "Month_Label" in df_pnl.columns:
            df_pnl['Month_Num'] = df_pnl['Month_Label'].map(m_map)
        conn.register("pnl_tmp", df_pnl)
        conn.execute("CREATE TABLE pnl_data AS SELECT * FROM pnl_tmp")
            
    return conn, kpi_map, field_rules

conn, kpi_rules, field_definitions = init_system()

# 2. CHAT HISTORY UI
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "df" in msg: st.dataframe(msg["df"])
        if "fig" in msg: st.plotly_chart(msg["fig"])

# 3. ARCHITECT AGENT EXECUTION
if prompt := st.chat_input("Ask: What is the FTE trend by Client Name?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        llm = ChatOpenAI(model="gpt-4o", temperature=0)
        
        # Determine KPI Formula
        formula = next((v for k, v in kpi_rules.items() if k in prompt.lower()), "SUM(\"Amount in USD\")")
        
        # 
        architect_msg = f"""
        You are the L&T Financial Architect. 
        
        MANDATORY KPI MATH: {formula}
        
        FIELD DEFINITIONS (Translate user jargon like 'Client' to these technical columns):
        {field_definitions}
        
        TIME RULES:
        - Labels: Use 'Month_Label'. 
        - Sorting: Use 'Month_Num'. Always add 'ORDER BY Month_Num ASC'.
        
        TABLE RULES:
        - Use 'ut_data' for utilization/fte. Use 'pnl_data' for financials.
        
        Write ONLY the DuckDB SQL. Use double quotes for all column names.
        """
        
        sql = llm.invoke(architect_prompt + f"\nQuestion: {prompt}").content.strip().replace("```sql", "").replace("```", "")
        
        try:
            df = conn.execute(sql).df()
            
            # Narrator Agent
            narrative = llm.invoke(f"As a CFO, summarize this trend: {df.to_string()}").content
            st.markdown(narrative)
            st.dataframe(df)
            
            # Visualizer Agent
            if not df.empty and len(df.columns) >= 2:
                chart_type = px.line if "Month" in str(df.columns) else px.bar
                fig = chart_type(df, x=df.columns[0], y=df.columns[1], markers=True, title=prompt)
                if "utilization" in prompt.lower():
                    fig.update_layout(yaxis_tickformat='.1%')
                st.plotly_chart(fig)
                
                st.session_state.messages.append({"role": "assistant", "content": narrative, "df": df, "fig": fig})
            else:
                st.session_state.messages.append({"role": "assistant", "content": narrative})
                
        except Exception as e:
            st.error(f"Logic Conflict: {e}")
            st.code(sql)
