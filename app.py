import streamlit as st
import pandas as pd
import duckdb
import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from langchain_openai import ChatOpenAI

st.set_page_config(page_title="L&T Financial AI", layout="wide")
st.title("🏛️ L&T AI Financial System")

# 1. DATABASE & KNOWLEDGE INITIALIZATION
@st.cache_resource
def init_system():
    conn = duckdb.connect(database=':memory:')
    
    # Load Field Directory as the "Source of Truth"
    field_rules = ""
    if os.path.exists("field_directory.xlsx"):
        field_rules = pd.read_excel("field_directory.xlsx").to_string(index=False)
    
    # Load and Sanitize UT Data
    if os.path.exists("ut_data.xlsx"):
        df_ut = pd.read_excel("ut_data.xlsx")
        # Standardize Date_a to datetime objects
        df_ut['Date_a'] = pd.to_datetime(df_ut['Date_a'])
        # PHYSICAL LOCKDOWN: Rename original columns so AI can't use them
        df_ut.rename(columns={"Month": "HIDDEN_MONTH_NUM", "Year": "HIDDEN_FY"}, inplace=True)
        conn.register("ut_tmp", df_ut)
        conn.execute("CREATE TABLE ut_data AS SELECT * FROM ut_tmp")

    # Load and Sanitize PNL Data
    if os.path.exists("pnl_data.xlsx"):
        df_pnl = pd.read_excel("pnl_data.xlsx")
        # Ensure Month labels are consistently parsed as dates if possible
        conn.register("pnl_tmp", df_pnl)
        conn.execute("CREATE TABLE pnl_data AS SELECT * FROM pnl_tmp")
            
    return conn, field_rules

conn, field_definitions = init_system()

# 2. CHAT EXECUTION
if prompt := st.chat_input("FTE trend by Customer Name for 2025"):
    with st.chat_message("assistant"):
        llm = ChatOpenAI(model="gpt-4o", temperature=0)
        
        # 
        architect_msg = f"""
        You are the L&T Financial Architect. 
        
        FIELD DEFINITIONS:
        {field_definitions}
        
        STRICT DATE RULES (MANDATORY):
        1. "Date_a" is the ONLY field for dates in ut_data.
        2. To filter by Year: Use `WHERE YEAR("Date_a") = 2025`.
        3. To filter by Month: Use `WHERE MONTH("Date_a") = 2`.
        4. To display a Month Name: Use `strftime("Date_a", '%b %Y')`.
        5. CHRONOLOGICAL ORDER: Always use `ORDER BY "Date_a" ASC`.
        
        KPI RULES:
        - FTE / Headcount = COUNT(DISTINCT "PSNo")
        - Customer = "FinalCustomerName"
        
        TABLES: 'ut_data' (for FTE/UT), 'pnl_data' (for Financials).
        
        Write ONLY the DuckDB SQL. Use double quotes for all columns.
        """
        
        sql = llm.invoke(architect_msg + f"\nQuestion: {prompt}").content.strip().replace("```sql", "").replace("```", "")
        
        try:
            df = conn.execute(sql).df()
            st.dataframe(df)
            
            # 3. MATPLOTLIB VISUALS (High Quality)
            if not df.empty and len(df.columns) >= 2:
                fig, ax = plt.subplots(figsize=(10, 5))
                # Convert the first column to string if it's a date label for the x-axis
                x_labels = df.iloc[:, 0].astype(str)
                y_values = df.iloc[:, 1]
                
                ax.plot(x_labels, y_values, marker='o', linestyle='-', linewidth=2, color='#0072b2')
                ax.set_title(f"Analysis: {prompt}", fontsize=14, fontweight='bold')
                ax.grid(True, linestyle='--', alpha=0.6)
                plt.xticks(rotation=45)
                plt.tight_layout()
                
                st.pyplot(fig)
            
            # CFO Narrative
            narrative = llm.invoke(f"Briefly summarize this for a CFO: {df.to_string()}").content
            st.markdown(narrative)
                
        except Exception as e:
            st.error(f"Logic Conflict: {e}")
            st.code(sql)
