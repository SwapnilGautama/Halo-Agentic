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

# 1. Securely load OpenAI Key from Streamlit Secrets
if "OPENAI_API_KEY" in st.secrets:
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
else:
    st.error("Missing OpenAI API Key! Please add 'OPENAI_API_KEY' to your Streamlit Secrets.")
    st.stop()

# 2. Initialize Database from Excel files
@st.cache_resource
def init_db():
    con = duckdb.connect("lnt_analytics.db")
    
    # Load P&L Data
    if os.path.exists("pnl_data.xlsx"):
        df_pnl = pd.read_excel("pnl_data.xlsx", engine="openpyxl")
        con.execute("CREATE OR REPLACE TABLE pnl_data AS SELECT * FROM df_pnl")
    
    # Load Utilization Data
    if os.path.exists("ut_data.xlsx"):
        df_ut = pd.read_excel("ut_data.xlsx", engine="openpyxl")
        con.execute("CREATE OR REPLACE TABLE ut_data AS SELECT * FROM df_ut")
    
    # Use the explicit duckdb+duckdb dialect for SQLAlchemy
    return SQLDatabase.from_uri("duckdb+duckdb:///lnt_analytics.db")

# 3. Load KPI Context
@st.cache_data
def get_kpi_context():
    if os.path.exists("kpi_directory.xlsx"):
        df_kpi = pd.read_excel("kpi_directory.xlsx", engine="openpyxl")
        return df_kpi.to_string()
    return "No KPI directory found."

# Setup Resources
db = init_db()
kpi_context = get_kpi_context()

# 4. Agent Setup
llm = ChatOpenAI(model="gpt-4o", temperature=0)
toolkit = SQLDatabaseToolkit(db=db, llm=llm)

system_message = f"""
You are a senior L&T Financial Analyst. Use the 'pnl_data' and 'ut_data' tables.

KPI RULES & DEFINITIONS:
{kpi_context}

IMPORTANT: 
- Use 'Amount in USD' for revenue/cost queries unless the user asks for INR.
- For FMCG queries, filter the segment columns in pnl_data.
- For headcount/utilization, use ut_data.
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

if prompt := st.chat_input("Ask: What was the total FMCG Revenue?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analyzing financial records..."):
            try:
                response = agent_executor.invoke({"input": prompt})
                answer = response["output"]
                st.markdown(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})
            except Exception as e:
                st.error(f"Agent Error: {e}")
