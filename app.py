import streamlit as st
import pandas as pd
import duckdb
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_openai import ChatOpenAI
import os

# Page Config
st.set_page_config(page_title="L&T Financial AI Agent", layout="wide")
st.title("🤖 L&T Financial Analyst AI")

# 1. Load OpenAI Key from Streamlit Secrets
if "OPENAI_API_KEY" in st.secrets:
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
else:
    st.error("Missing OPENAI_API_KEY in Secrets!")
    st.stop()

# 2. Initialize Database from Excel files
@st.cache_resource
def init_db():
    # Use a persistent file
    db_file = "lnt_analytics.db"
    con = duckdb.connect(db_file)
    
    # Load P&L Data
    if os.path.exists("pnl_data.xlsx"):
        df_pnl = pd.read_excel("pnl_data.xlsx", engine="openpyxl")
        # Explicitly create/replace table
        con.execute("CREATE OR REPLACE TABLE pnl_data AS SELECT * FROM df_pnl")
    
    # Load Utilization Data
    if os.path.exists("ut_data.xlsx"):
        df_ut = pd.read_excel("ut_data.xlsx", engine="openpyxl")
        con.execute("CREATE OR REPLACE TABLE ut_data AS SELECT * FROM df_ut")
    
    con.close() # Close to release file lock for SQLAlchemy
    
    # Use standard DuckDB URI format
    return SQLDatabase.from_uri(f"duckdb:///{db_file}")

# 3. Load KPI Context
@st.cache_data
def get_kpi_context():
    if os.path.exists("kpi_directory.xlsx"):
        df_kpi = pd.read_excel("kpi_directory.xlsx", engine="openpyxl")
        return df_kpi.to_string()
    return "No KPI directory found."

# Resources
db = init_db()
kpi_context = get_kpi_context()

# 4. Agent Setup
llm = ChatOpenAI(model="gpt-4o", temperature=0)
toolkit = SQLDatabaseToolkit(db=db, llm=llm)

system_message = f"""
You are a senior L&T Financial Analyst. Use the 'pnl_data' and 'ut_data' tables.
KPI RULES: {kpi_context}
Always use 'Amount in USD' for revenue unless INR is specified.
"""

agent_executor = create_sql_agent(
    llm=llm,
    toolkit=toolkit,
    verbose=True,
    agent_type="openai-tools",
    extra_prompt_messages=[("system", system_message)]
)

# 5. Chat Interface
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask: What was the FMCG Revenue in Q3?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analyzing financial data..."):
            try:
                response = agent_executor.invoke({"input": prompt})
                st.markdown(response["output"])
                st.session_state.messages.append({"role": "assistant", "content": response["output"]})
            except Exception as e:
                st.error(f"Error: {e}")
