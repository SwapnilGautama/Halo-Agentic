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

# Sidebar for API Key
with st.sidebar:
    openai_api_key = st.text_input("OpenAI API Key", type="password")
    st.info("Upload your CSVs or ensure they are in the repository.")

# 1. Initialize Database
@st.cache_resource
def init_db():
    con = duckdb.connect("lnt_analytics.db")
    # Load P&L Data
    if os.path.exists("LnTPnL.csv"):
        df_pnl = pd.read_csv("LnTPnL.csv")
        con.execute("CREATE OR REPLACE TABLE pnl_data AS SELECT * FROM df_pnl")
    
    # Load Utilization Data
    if os.path.exists("LNTData.csv"):
        df_ut = pd.read_csv("LNTData.csv")
        con.execute("CREATE OR REPLACE TABLE ut_data AS SELECT * FROM df_ut")
    
    return SQLDatabase.from_uri("duckdb:///lnt_analytics.db")

db = init_db()

# 2. Load KPI Context
@st.cache_data
def get_kpi_context():
    if os.path.exists("KPInOtherDetails.csv"):
        df_kpi = pd.read_csv("KPInOtherDetails.csv")
        return df_kpi.to_string()
    return "No KPI directory found."

kpi_context = get_kpi_context()

# 3. Agent Logic
if openai_api_key:
    os.environ["OPENAI_API_KEY"] = openai_api_key
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    
    system_message = f"""
    You are a senior L&T Financial Analyst. Use the 'pnl_data' and 'ut_data' tables.
    KPI RULES & DEFINITIONS:
    {kpi_context}
    
    Always use 'Amount in USD' for revenue/cost queries unless INR is specified.
    """

    agent_executor = create_sql_agent(
        llm=llm,
        toolkit=toolkit,
        verbose=True,
        agent_type="openai-tools",
        extra_prompt_messages=[("system", system_message)]
    )

    # Chat UI
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Ask about FMCG Revenue, Utilization, or RPP..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing data..."):
                response = agent_executor.invoke({"input": prompt})
                answer = response["output"]
                st.markdown(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})
else:
    st.warning("Please enter your OpenAI API Key in the sidebar to begin.")