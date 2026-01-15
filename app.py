import streamlit as st
import pandas as pd
import duckdb
import plotly.express as px
import os
from langchain_openai import ChatOpenAI

# --- PAGE CONFIG ---
st.set_page_config(page_title="L&T Financial Multi-Agent", layout="wide")
st.title("🏛️ L&T AI Financial Analyst")

# 1. DATABASE & KPI INITIALIZATION
@st.cache_resource
def init_system():
    conn = duckdb.connect(database=':memory:')
    kpi_map = {}
    
    # --- LOAD KPI DIRECTORY ---
    if os.path.exists("kpi_directory.xlsx"):
        df_kpi = pd.read_excel("kpi_directory.xlsx", engine="openpyxl")
        # Search for FTE/Headcount Row
        fte_row = df_kpi[df_kpi.iloc[:, 0].str.contains("FTE|Head Count", na=False, case=False)]
        if not fte_row.empty:
            kpi_map["fte"] = 'COUNT(DISTINCT "PSNo")'
            kpi_map["headcount"] = 'COUNT(DISTINCT "PSNo")'
            
        # Search for Utilization Row
        ut_row = df_kpi[df_kpi.iloc[:, 0].str.contains("Utilization", na=False, case=False)]
        if not ut_row.empty:
            kpi_map["utilization"] = 'SUM("TotalBillableHours") / NULLIF(SUM("NetAvailableHours"), 0)'

    # --- LOAD & STANDARDIZE TABLES (Handling Month Ambiguity) ---
    # 
    if os.path.exists("ut_data.xlsx"):
        df_ut = pd.read_excel("ut_data.xlsx", engine="openpyxl")
        # Standardizing UT Month columns: Column 2 (Index 1) is Number, Last Column is Name
        cols = list(df_ut.columns)
        cols[1] = "Month_Num" 
        cols[-1] = "Month_Label"
        df_ut.columns = cols
        conn.register("ut_tmp", df_ut)
        conn.execute("CREATE TABLE ut_data AS SELECT * FROM ut_tmp")

    if os.path.exists("pnl_data.xlsx"):
        df_pnl = pd.read_excel("pnl_data.xlsx", engine="openpyxl")
        # Standardize P&L Month column
        df_pnl.rename(columns={"Month": "Month_Label"}, inplace=True)
        # We synthesize a Month_Num for P&L if missing to ensure sorting works
        month_map = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}
        if "Month_Label" in df_pnl.columns:
            df_pnl['Month_Num'] = df_pnl['Month_Label'].map(month_map)
        conn.register("pnl_tmp", df_pnl)
        conn.execute("CREATE TABLE pnl_data AS SELECT * FROM pnl_tmp")
            
    return conn, kpi_map

conn, kpi_rules = init_system()

# 2. CHAT HISTORY UI
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "df" in msg: st.dataframe(msg["df"])
        if "fig" in msg: st.plotly_chart(msg["fig"])

# 3. EXECUTION ENGINE
if prompt := st.chat_input("Ask: What is the Utilization % trend?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        llm = ChatOpenAI(model="gpt-4o", temperature=0)
        
        # --- ARCHITECT: RULE & TIME INJECTION ---
        matched_rule = None
        for key in kpi_rules:
            if key in prompt.lower():
                matched_rule = kpi_rules[key]
                break
        
        # Default fallback if no KPI matched
        if not matched_rule:
            matched_rule = "SUM(\"Amount in USD\")" # Default for P&L queries
            
        architect_prompt = f"""
        You are an L&T Financial Architect. 
        MANDATORY BUSINESS RULE: Use this math: {matched_rule}
        
        TIME DIMENSION RULES:
        - For display/labels, use 'Month_Label'.
        - For chronological sorting, you MUST use 'Month_Num'.
        - Always end your query with 'ORDER BY Month_Num ASC'.
        
        TABLE RULES:
        - Use 'ut_data' for Utilization, FTE, and Headcount.
        - Use 'pnl_data' for Revenue, Cost, and Profit.
        
        Return ONLY the DuckDB SQL code.
        """
        
        sql = llm.invoke(architect_prompt + f"\nQuestion: {prompt}").content.strip()
        sql = sql.replace("```sql", "").replace("```", "").strip()
        
        try:
            # Execute
            df = conn.execute(sql).df()
            
            # Narrative & Visuals
            narrative = llm.invoke(f"As CFO, analyze this trend: {df.to_string()}").content
            st.markdown(narrative)
            st.dataframe(df)
            
            # Validation Message
            st.caption(f"Logic Applied: `{matched_rule}` | Sorted by `Month_Num`")
            
            # Dynamic Charting
            if not df.empty and len(df.columns) >= 2:
                # 
                fig = px.line(df, x=df.columns[0], y=df.columns[1], markers=True, title=f"Trend: {prompt}")
                if "utilization" in prompt.lower():
                    fig.update_layout(yaxis_tickformat='.1%')
                st.plotly_chart(fig)
                
                # Save to history
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": narrative, 
                    "df": df, 
                    "fig": fig
                })
            else:
                st.session_state.messages.append({"role": "assistant", "content": narrative})
                
        except Exception as e:
            st.error(f"Execution Error: {e}")
            st.code(sql)
