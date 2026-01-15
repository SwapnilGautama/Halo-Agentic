import streamlit as st
import pandas as pd
import duckdb
import plotly.express as px
import os
from langchain_openai import ChatOpenAI

# --- CONFIG & SIDEBAR ---
st.set_page_config(page_title="L&T Multi-Agent Analyst", layout="wide")
st.title("🏛️ L&T AI Financial System")

# 1. API Key from Secrets
if "OPENAI_API_KEY" not in st.secrets:
    st.error("Please add OPENAI_API_KEY to Streamlit Secrets.")
    st.stop()

os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
llm = ChatOpenAI(model="gpt-4o", temperature=0)

# 2. IN-MEMORY DATABASE & DATA DICTIONARY
@st.cache_resource
def init_system():
    # Create one shared in-memory connection to prevent deadlocks
    conn = duckdb.connect(database=':memory:')
    dict_info = {}
    
    files = {"pnl_data": "pnl_data.xlsx", "ut_data": "ut_data.xlsx"}
    for table, path in files.items():
        if os.path.exists(path):
            df = pd.read_excel(path, engine="openpyxl")
            conn.register("tmp", df)
            conn.execute(f"CREATE TABLE {table} AS SELECT * FROM tmp")
            dict_info[table] = list(df.columns)
            
    return conn, dict_info

conn, data_dict = init_system()

# --- SIDEBAR DATA DICTIONARY ---
with st.sidebar:
    st.header("📊 Data Dictionary")
    for table, cols in data_dict.items():
        with st.expander(f"Table: {table}"):
            for c in cols:
                st.write(f"- {c}")
    st.info("The AI uses these exact column names for analysis.")

# --- MULTI-AGENT LOGIC (SEQUENTIAL) ---

def run_analysis(user_query):
    # Step 1: Analyst (SQL Generation)
    schema_context = str(data_dict)
    analyst_prompt = f"""
    Schema: {schema_context}
    Task: Write a DuckDB SQL query for: {user_query}
    Rules: Use double quotes for columns with spaces. Return ONLY the SQL.
    """
    sql = llm.invoke(analyst_prompt).content.replace("```sql", "").replace("```", "").strip()
    
    # Step 2: Reviewer (Execution & Validation)
    try:
        df = conn.execute(sql).df()
        status = "Success"
        error = ""
    except Exception as e:
        df = pd.DataFrame()
        status = "Failed"
        error = str(e)

    # Step 3: Visualizer (Narrative & Plot)
    if status == "Success":
        narrative_prompt = f"Data results: {df.to_string()}\nSummarize this for a CFO in relation to: {user_query}"
        narrative = llm.invoke(narrative_prompt).content
    else:
        narrative = f"The Reviewer found an error in the logic: {error}"
        
    return sql, df, narrative, status

# --- UI INTERFACE ---
if prompt := st.chat_input("Ask: Trend of 'Amount in USD' for FMCG by Month"):
    # Clear visual for the multi-agent process
    with st.status("Team collaborating...", expanded=True) as status_box:
        st.write("👨‍💻 Analyst: Drafting SQL...")
        sql, df, narrative, status = run_analysis(prompt)
        
        st.write("🧐 Reviewer: Verifying data...")
        if status == "Success":
            st.write("🎨 Visualizer: Preparing narrative...")
            status_box.update(label="Analysis Complete!", state="complete", expanded=False)
        else:
            status_box.update(label="Analysis Failed", state="error", expanded=True)

    # Display Output
    st.subheader("Financial Narrative")
    st.write(narrative)

    if not df.empty:
        st.subheader("Data Table")
        st.dataframe(df, use_container_width=True)
        
        # Simple Visualization Logic
        if len(df.columns) >= 2:
            st.subheader("Visualization")
            # Detect numeric columns for Y axis
            numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
            y_col = numeric_cols[0] if numeric_cols else df.columns[1]
            fig = px.bar(df, x=df.columns[0], y=y_col, template="plotly_white", color_discrete_sequence=['#004b87'])
            st.plotly_chart(fig, use_container_width=True)
