import streamlit as st
import pandas as pd
import duckdb
import plotly.express as px
import os
from langchain_openai import ChatOpenAI

st.set_page_config(page_title="L&T Financial AI", layout="wide")
st.title("🏛️ L&T AI Financial analyst")

@st.cache_resource
def init_system():
    # Use memory to avoid file locks
    conn = duckdb.connect(database=':memory:')
    
    # 1. LOAD KPI RULES
    kpi_rules = ""
    if os.path.exists("kpi_directory.xlsx"):
        df_kpi = pd.read_excel("kpi_directory.xlsx")
        kpi_rules = df_kpi.to_string(index=False)

    # 2. LOAD FIELD RULES
    field_rules = ""
    if os.path.exists("field_directory.xlsx"):
        df_fields = pd.read_excel("field_directory.xlsx")
        field_rules = df_fields.to_string(index=False)

    # 3. LOAD & FORCE-RENAME UT_DATA
    if os.path.exists("ut_data.xlsx"):
        df_ut = pd.read_excel("ut_data.xlsx")
        # FORCE RENAMING TO PREVENT AMBIGUITY
        # Date_a -> Month_Label (Standard for display)
        # Month -> Month_Num (Standard for sorting)
        mapping = {"Date_a": "Month_Label", "Month": "Month_Num"}
        df_ut.rename(columns=mapping, inplace=True)
        conn.register("ut_tmp", df_ut)
        conn.execute("CREATE TABLE ut_data AS SELECT * FROM ut_tmp")

    # 4. LOAD & FORCE-RENAME PNL_DATA
    if os.path.exists("pnl_data.xlsx"):
        df_pnl = pd.read_excel("pnl_data.xlsx")
        # Month -> Month_Label
        df_pnl.rename(columns={"Month": "Month_Label"}, inplace=True)
        # Helper for P&L Sorting
        m_map = {'Jan':1,'Feb':2,'Mar':3,'Apr':4,'May':5,'Jun':6,'Jul':7,'Aug':8,'Sep':9,'Oct':10,'Nov':11,'Dec':12}
        df_pnl['Month_Num'] = df_pnl['Month_Label'].map(m_map)
        conn.register("pnl_tmp", df_pnl)
        conn.execute("CREATE TABLE pnl_data AS SELECT * FROM pnl_tmp")
            
    return conn, kpi_rules, field_rules

conn, kpi_defs, field_defs = init_system()

# --- EXECUTION ---
if prompt := st.chat_input("Ask: FTE trend by FinalCustomerName"):
    with st.chat_message("assistant"):
        llm = ChatOpenAI(model="gpt-4o", temperature=0)
        
        architect_prompt = f"""
        You are the L&T Financial Architect. 
        
        KNOWLEDGE BASE:
        KPI DIRECTORY: {kpi_defs}
        FIELD DIRECTORY: {field_defs}
        
        STRICT SCHEMA RULES (USE THESE NAMES ONLY):
        - UT Table (ut_data): 
            * Use 'Month_Label' for display/labels. 
            * Use 'Month_Num' for sorting. 
            * Use 'FinalCustomerName' for Client/Customer.
            * Use 'PSNo' for Headcount/FTE count.
        - P&L Table (pnl_data):
            * Use 'Month_Label' for labels.
            * Use 'Month_Num' for sorting.
            * Use 'Amount in USD' for financial values.
        
        QUERY RULES:
        1. Always include 'ORDER BY Month_Num ASC' for trends.
        2. Use double quotes for all column names.
        
        Write ONLY the DuckDB SQL.
        """
        
        sql = llm.invoke(architect_prompt + f"\nUser Question: {prompt}").content.strip().replace("```sql", "").replace("```", "")
        
        try:
            df = conn.execute(sql).df()
            st.dataframe(df)
            
            # Smart Plotting
            if not df.empty and len(df.columns) >= 2:
                fig = px.line(df, x=df.columns[0], y=df.columns[1], markers=True, title=prompt)
                st.plotly_chart(fig)
        except Exception as e:
            st.error(f"SQL Error: {e}")
            st.code(sql)
