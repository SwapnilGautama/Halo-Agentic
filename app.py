import streamlit as st
import pandas as pd
import duckdb
import plotly.express as px
import os
from langchain_openai import ChatOpenAI

st.set_page_config(page_title="L&T Financial AI", layout="wide")
st.title("🏛️ L&T AI Financial Analyst")

# 1. INIT SYSTEM
@st.cache_resource
def init_system():
    conn = duckdb.connect(database=':memory:')
    kpi_map = {}
    if os.path.exists("kpi_directory.xlsx"):
        df_kpi = pd.read_excel("kpi_directory.xlsx", engine="openpyxl")
        # Extract Utilization Rule
        ut_row = df_kpi[df_kpi.iloc[:, 0].str.contains("Utilization", na=False)]
        if not ut_row.empty:
            # We wrap the denominator in NULLIF to prevent division by zero errors
            kpi_map["utilization"] = 'SUM("TotalBillableHours") / NULLIF(SUM("NetAvailableHours"), 0)'
        
        # Extract FTE Rule
        fte_row = df_kpi[df_kpi.iloc[:, 0].str.contains("FTE", na=False)]
        if not fte_row.empty:
            kpi_map["fte"] = 'COUNT(DISTINCT "PSNo")'
            
    # Load Tables
    if os.path.exists("ut_data.xlsx"):
        df = pd.read_excel("ut_data.xlsx", engine="openpyxl")
        conn.register("tmp", df)
        # We rename the duplicate 'Month' columns to ensure the agent knows which is which
        conn.execute("CREATE TABLE ut_data AS SELECT * EXCLUDE (Month), Month AS Month_Name FROM tmp")
    return conn, kpi_map

conn, kpi_rules = init_system()

# 2. UI & HISTORY
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# 3. EXECUTION
if prompt := st.chat_input("How is utilization % trending?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        llm = ChatOpenAI(model="gpt-4o", temperature=0)
        
        # ARCHITECT: Identifying the Rule
        rule = kpi_rules.get("utilization") if "utilization" in prompt.lower() else kpi_rules.get("fte")
        
        # We explicitly tell the AI to sort by the numerical month (e.g., column index or specific name)
        sql_instruction = f"""
        Table: ut_data. 
        MANDATORY Rule for calculation: {rule}
        
        IMPORTANT: 
        1. There are two month columns. Use 'Month_Name' for labels but sort by the numerical 'Month' column.
        2. Use double quotes for column names.
        3. Return ONLY the SQL.
        """
        
        sql = llm.invoke(sql_instruction + f"\nQuestion: {prompt}").content.strip().replace("```sql", "").replace("```", "")
        
        try:
            df = conn.execute(sql).df()
            
            # Show formula for transparency
            st.caption(f"Applied Business Rule: `{rule}`")
            
            narrative = llm.invoke(f"Analyze this trend: {df.to_string()}").content
            st.markdown(narrative)
            st.dataframe(df)
            
            if not df.empty:
                # Plotting trend
                fig = px.line(df, x=df.columns[0], y=df.columns[1], markers=True, title="Utilization Trend")
                # Format Y axis as percentage if it's utilization
                if "utilization" in prompt.lower():
                    fig.update_layout(yaxis_tickformat='.1%')
                st.plotly_chart(fig)
            
            st.session_state.messages.append({"role": "assistant", "content": narrative})
            
        except Exception as e:
            st.error(f"Execution Error: {e}")
            st.code(sql)
