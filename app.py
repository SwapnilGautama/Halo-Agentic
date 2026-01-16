import streamlit as st
import pandas as pd
import duckdb
import os
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

st.set_page_config(page_title="L&T Financial AI", layout="wide")
st.title("🏛️ L&T AI Financial System")

# 1. DATABASE & KNOWLEDGE INITIALIZATION
@st.cache_resource
def init_system():
    conn = duckdb.connect(database=':memory:')
    
    # Load Directories
    field_rules = pd.read_excel("field_directory.xlsx").to_string(index=False) if os.path.exists("field_directory.xlsx") else ""
    kpi_rules = pd.read_excel("kpi_directory.xlsx").to_string(index=False) if os.path.exists("kpi_directory.xlsx") else ""
    
    # --- LOAD & SANITIZE UT DATA ---
    if os.path.exists("ut_data.xlsx"):
        df_ut = pd.read_excel("ut_data.xlsx")
        # Ensure Date_a is a real date
        df_ut['Date_a'] = pd.to_datetime(df_ut['Date_a'])
        # PHYSICAL LOCKDOWN: Rename original numeric Month/Year so AI can't find them
        df_ut.rename(columns={"Month": "HIDDEN_MONTH", "Year": "HIDDEN_YEAR"}, inplace=True)
        conn.register("ut_tmp", df_ut)
        conn.execute("CREATE TABLE ut_data AS SELECT * FROM ut_tmp")

    # --- LOAD & SANITIZE PNL DATA ---
    if os.path.exists("pnl_data.xlsx"):
        df_pnl = pd.read_excel("pnl_data.xlsx")
        # Ensure 'Month' label is consistent
        df_pnl.rename(columns={"Month": "Month_Label"}, inplace=True)
        conn.register("pnl_tmp", df_pnl)
        conn.execute("CREATE TABLE pnl_data AS SELECT * FROM pnl_tmp")
            
    return conn, kpi_rules, field_rules

conn, kpi_defs, field_defs = init_system()

# --- SIDEBAR DATA INSPECTOR ---
with st.sidebar:
    st.header("🔍 Data Inspector")
    if st.checkbox("Show Table Schemas"):
        st.subheader("ut_data Columns")
        st.write(conn.execute("DESCRIBE ut_data").df()[['column_name', 'column_type']])
    
    if st.checkbox("Preview ut_data (First 5 Rows)"):
        st.dataframe(conn.execute("SELECT * FROM ut_data LIMIT 5").df())

# --- ARCHITECT AGENT ---
if prompt := st.chat_input("FTE trend by Customer Name for Feb 2025"):
    with st.chat_message("assistant"):
        llm = ChatOpenAI(model="gpt-4o", temperature=0)
        
        system_instruction = f"""
        You are the L&T Financial Architect. 
        
        FIELD DIRECTORY: {field_defs}
        KPI DIRECTORY: {kpi_defs}
        
        STRICT DATE RULES (ut_data):
        1. "Date_a" is the ONLY field for dates.
        2. Filter Feb 2025 like this: `WHERE MONTH("Date_a") = 2 AND YEAR("Date_a") = 2025`.
        3. For trends, group by: `strftime("Date_a", '%Y-%m')` and ORDER BY "Date_a" ASC.
        
        MANDATORY KPI:
        - FTE / Headcount = COUNT(DISTINCT "PSNo")
        - Customer = "FinalCustomerName"
        
        Write ONLY the DuckDB SQL. Use double quotes for columns.
        """
        
        sql = llm.invoke(system_instruction + f"\nQuestion: {prompt}").content.strip().replace("```sql", "").replace("```", "")
        
        try:
            df = conn.execute(sql).df()
            st.write(f"### Results for: {prompt}")
            st.dataframe(df)
            
            # --- MATPLOTLIB VISUALS ---
            if not df.empty and len(df.columns) >= 2:
                fig, ax = plt.subplots(figsize=(10, 4))
                ax.plot(df.iloc[:, 0].astype(str), df.iloc[:, 1], marker='s', color='#1f77b4', linewidth=2)
                ax.set_title(prompt, fontsize=12, fontweight='bold')
                ax.grid(True, linestyle='--', alpha=0.5)
                plt.xticks(rotation=45)
                st.pyplot(fig)
            
            # CFO Analysis
            analysis = llm.invoke(f"As CFO, summarize this trend: {df.to_string()}").content
            st.markdown(analysis)
            
        except Exception as e:
            st.error(f"SQL Error: {e}")
            st.code(sql)
