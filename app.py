import streamlit as st
import pandas as pd
import duckdb
import plotly.express as px
import os
from langchain_openai import ChatOpenAI

st.set_page_config(page_title="L&T Financial AI", layout="wide")
st.title("🏛️ L&T AI Financial System")

# 1. DATABASE & DIRECTORY INITIALIZATION
@st.cache_resource
def init_system():
    # Connection to memory to avoid "File Locked" errors
    conn = duckdb.connect(database=':memory:')
    
    # --- LOAD FIELD DIRECTORY ---
    field_rules = ""
    if os.path.exists("field_directory.xlsx"):
        df_fields = pd.read_excel("field_directory.xlsx")
        field_rules = df_fields.to_string(index=False)
    
    # --- LOAD KPI DIRECTORY ---
    kpi_map = {}
    if os.path.exists("kpi_directory.xlsx"):
        df_kpi = pd.read_excel("kpi_directory.xlsx")
        # Extract FTE logic specifically
        fte_row = df_kpi[df_kpi.iloc[:, 0].str.contains("FTE|Head Count", na=False, case=False)]
        if not fte_row.empty:
            kpi_map["fte"] = 'COUNT(DISTINCT "PSNo")'
        # Extract Utilization logic
        ut_row = df_kpi[df_kpi.iloc[:, 0].str.contains("Utilization", na=False, case=False)]
        if not ut_row.empty:
            kpi_map["utilization"] = 'SUM("TotalBillableHours") / NULLIF(SUM("NetAvailableHours"), 0)'

    # --- LOAD & RENAME UT_DATA (The "Double Month" Fix) ---
    if os.path.exists("ut_data.xlsx"):
        df_ut = pd.read_excel("ut_data.xlsx")
        cols = list(df_ut.columns)
        # Based on your file: Index 1 is Month (Num), Last Index is Month (Label)
        cols[1] = "Month_Num" 
        cols[-1] = "Month_Label"
        df_ut.columns = cols
        conn.register("ut_tmp", df_ut)
        conn.execute("CREATE TABLE ut_data AS SELECT * FROM ut_tmp")

    # --- LOAD PNL_DATA ---
    if os.path.exists("pnl_data.xlsx"):
        df_pnl = pd.read_excel("pnl_data.xlsx")
        df_pnl.rename(columns={"Month": "Month_Label"}, inplace=True)
        m_map = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}
        df_pnl['Month_Num'] = df_pnl['Month_Label'].map(m_map)
        conn.register("pnl_tmp", df_pnl)
        conn.execute("CREATE TABLE pnl_data AS SELECT * FROM pnl_tmp")
            
    return conn, kpi_map, field_rules

conn, kpi_rules, field_definitions = init_system()

# 2. UI CHAT HISTORY
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "df" in msg: st.dataframe(msg["df"])

# 3. THE ARCHITECT EXECUTION
if prompt := st.chat_input("Ask: What is the FTE trend by Client Name?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        llm = ChatOpenAI(model="gpt-4o", temperature=0)
        
        # Determine the KPI formula from the directory
        formula = next((v for k, v in kpi_rules.items() if k in prompt.lower()), "SUM(\"Amount in USD\")")
        
        # 
        architect_msg = f"""
        You are the L&T Financial Architect. 
        MANDATORY FORMULA: {formula}
        
        FIELD TRANSLATION DIRECTORY (Mapping user words to column names):
        {field_definitions}
        
        STRICT RULES:
        1. For Trends: Use 'Month_Label' as the label and 'Month_Num' for sorting.
        2. Always add 'ORDER BY Month_Num ASC'.
        3. Use double quotes for columns: "FinalCustomerName", "PSNo", etc.
        4. Use 'ut_data' for fte/utilization. Use 'pnl_data' for costs/revenue.
        
        Write ONLY the SQL code.
        """
        
        sql_raw = llm.invoke(architect_msg + f"\nQuestion: {prompt}").content
        sql = sql_raw.replace("```sql", "").replace("```", "").strip()
        
        try:
            df = conn.execute(sql).df()
            
            # Show formula used for verification
            st.caption(f"Using KPI Rule: `{formula}`")
            
            # Narrative & Visuals
            narrative = llm.invoke(f"As CFO, analyze this: {df.to_string()}").content
            st.markdown(narrative)
            st.dataframe(df)
            
            if not df.empty and len(df.columns) >= 2:
                chart_type = px.line if "Month" in str(df.columns) else px.bar
                fig = chart_type(df, x=df.columns[0], y=df.columns[1], markers=True, title=prompt)
                st.plotly_chart(fig)
                st.session_state.messages.append({"role": "assistant", "content": narrative, "df": df})
            else:
                st.session_state.messages.append({"role": "assistant", "content": narrative})
                
        except Exception as e:
            st.error(f"Logic Error: {e}")
            st.code(sql)
