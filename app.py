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
    st.header("Settings")
    openai_api_key = st.text_input("OpenAI API Key", type="password")
    st.info("Ensure LnTPnL.xlsx, LNTData.xlsx, and KPInOtherDetails.xlsx are in your GitHub repo.")

# 1. Initialize Database from Excel files
@st.cache_resource
def init_db():
    # Connect to a persistent or in-memory DuckDB
    con = duckdb.connect("lnt_analytics.db")
    
    # Load P&L Data (The 78MB file equivalent)
    if os.path.exists("LnTPnL.xlsx"):
        with st.spinner("Loading P&L Data..."):
            # openpyxl engine is used for .xlsx files
            df_pnl = pd.read_excel("LnTPnL.xlsx", engine="openpyxl")
            con.execute("CREATE OR REPLACE TABLE pnl_data AS SELECT * FROM df_pnl")
    
    # Load Utilization Data
    if os.path.exists("LNTData.xlsx"):
        with st.spinner("Loading Utilization Data..."):
            df_ut = pd.read_excel("LNTData.xlsx", engine="openpyxl")
            con.execute("CREATE OR REPLACE TABLE ut_data AS SELECT * FROM df_ut")
    
    return SQLDatabase.from_uri("duckdb:///lnt_analytics.db")

# 2. Load KPI Context for the Prompt
@st.cache_data
def get_kpi_context():
    if os.path.exists("KPInOtherDetails.xlsx"):
        df_kpi = pd.read_excel("KPInOtherDetails.xlsx", engine="openpyxl")
        return df_kpi.to_string()
    return "No KPI directory found."

# Initialize resources
db = init_db()
kpi_context = get_kpi_context()

# 3. Agent Logic
if openai_api_key:
    os.environ["OPENAI_API_KEY"] = openai_api_key
    
    # Define LLM and Toolkit
    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    
    # System Prompt with Financial Context
    system_message = f"""
    You are a senior L&T Financial Analyst. Use the 'pnl_data' and 'ut_data' tables.
    
    KPI RULES & DEFINITIONS:
    {kpi_context}
    
    IMPORTANT: 
    - Use 'Amount in USD' for revenue/cost queries unless the user asks for INR.
    - If asked about FMCG, filter the segment columns accordingly.
    - Be precise with numbers and explain which table you used.
    """

    agent_executor = create_sql_agent(
        llm=llm,
        toolkit=toolkit,
        verbose=True,
        agent_type="openai-tools",
        extra_prompt_messages=[("system", system_message)]
    )

    # Chat Interface
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
                    answer = response["output"]
                    st.markdown(answer)
                    st.session_state.messages.append({"role": "assistant", "content": answer})
                except Exception as e:
                    st.error(f"An error occurred: {e}")
else:
    st.warning("Please enter your OpenAI API Key in the sidebar to start.")