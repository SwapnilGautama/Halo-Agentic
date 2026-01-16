import streamlit as st
import pandas as pd
import duckdb
import plotly.express as px
import os
from langchain_openai import ChatOpenAI

# --- PAGE CONFIG ---
st.set_page_config(page_title="L&T Financial AI", layout="wide")
st.title("🏛️ L&T AI Financial Analyst")

# 1. DATABASE & KNOWLEDGE INITIALIZATION
@st.cache_resource
def init_system():
    # Use in-memory to prevent file-locking ConnectionErrors
    conn = duckdb.connect(database=':memory:')
    
    # LOAD DIRECTORIES
    field_rules = ""
    if os.path.exists("field_directory.xlsx"):
        df_fields = pd.read_excel("field_directory.xlsx")
        field_rules = df_fields.to_string(index=False)
    
    kpi_map = {}
    if os.path.exists("kpi_directory.xlsx"):
        df_kpi = pd.read_excel("kpi_directory.xlsx")
        # Direct KPI Mapping for FTE (Using the exact logic from your file)
        fte_row = df_kpi[df_kpi.iloc[:, 0].str.contains("FTE|Head Count", na=False, case=False)]
        if not fte_row.empty:
            kpi_map["fte"] = 'COUNT(DISTINCT "PSNo")'
            
        # Utilization Logic
        ut_row = df_kpi[df_kpi.iloc[:, 0].str.contains("Utilization", na=False, case=False)]
        if not ut_row.empty:
            kpi_map["utilization"] = 'SUM("TotalBillableHours") / NULLIF(SUM("NetAvailableHours"), 0)'

    # --- THE ROBUST DATA LOAD (The Fix) ---
    if os.path.exists("ut_data.xlsx"):
        df_ut = pd.read_excel("ut_data.xlsx")
        # RENAME TO AVOID AMBIGUITY:
        # We transform 'Month' (numbers) to 'Month_Num' 
        # and 'Date_a' (the label) to 'Month_Label'
        df_ut.rename(columns={
            "Month": "Month_Num",
            "Date_a": "Month_Label"
        }, inplace=True)
        conn.register("ut_tmp", df_ut)
        conn.execute("CREATE TABLE ut_data AS SELECT * FROM ut_tmp")

    if os.path.exists("pnl_data.xlsx"):
        df_pnl = pd.read_excel("pnl_data.xlsx")
        # Standardize P&L to match UT Table names
        df_pnl.rename(columns={"Month": "Month_Label"}, inplace=True)
        # Create a helper sorting column for P&L
        m_map = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}
        if "Month_Label" in df_pnl.columns:
            df_pnl['Month_Num'] = df_pnl['Month_Label'].map(m_map)
        conn.register("pnl_tmp", df_pnl)
        conn.execute("CREATE TABLE pnl_data AS SELECT * FROM pnl_tmp")
            
    return conn, kpi_map, field_rules

conn, kpi_rules, field_definitions = init_system()

# 2. CHAT UI
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "df" in msg: st.dataframe(msg["df"])

# 3. ARCHITECT EXECUTION
if prompt := st.chat_input("Ask: What is the FTE trend by FinalCustomerName?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        llm = ChatOpenAI(model="gpt-4o", temperature=0)
        
        # Decide KPI Math
        formula = next((v for k, v in kpi_rules.items() if k in prompt.lower()), "SUM(\"Amount in USD\")")
        
        # 
        architect_msg = f"""
        You are the L&T Financial Architect. 
        
        MANDATORY FORMULA: {formula}
        
        SEMANTIC FIELD MAPPINGS:
        {field_definitions}
        
        CRITICAL INSTRUCTION:
        1. The database columns have been renamed for clarity.
        2. Use 'Month_Label' for all display and trend labels (Jan, Feb, etc.).
        3. Use 'Month_Num' ONLY for sorting: 'ORDER BY Month_Num ASC'.
        4. Use 'FinalCustomerName' for all Client or Customer requests.
        5. Use double quotes for column names: e.g., "FinalCustomerName".
        
        Return ONLY the DuckDB SQL.
        """
        
        sql_raw = llm.invoke(architect_msg + f"\nQuestion: {prompt}").content
        sql = sql_raw.replace("```sql", "").replace("```", "").strip()
        
        try:
            df = conn.execute(sql).df()
            
            # Show formula for transparency
            st.caption(f"Applied Logic: `{formula}`")
            
            # CFO Narrator
            narrative = llm.invoke(f"Briefly summarize this for a CFO: {df.to_string()}").content
            st.markdown(narrative)
            st.dataframe(df)
            
            # Visualizer
            if not df.empty and len(df.columns) >= 2:
                chart_type = px.line if "Month" in str(df.columns) else px.bar
                fig = chart_type(df, x=df.columns[0], y=df.columns[1], markers=True, title=prompt)
                st.plotly_chart(fig)
                st.session_state.messages.append({"role": "assistant", "content": narrative, "df": df})
            else:
                st.session_state.messages.append({"role": "assistant", "content": narrative})
                
        except Exception as e:
            st.error(f"Execution Error: {e}")
            st.code(sql)
