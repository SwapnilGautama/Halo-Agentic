import streamlit as st
import pandas as pd
import duckdb
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.agent_toolkits.sql.toolkit import SQLDatabaseToolkit
from langchain_openai import ChatOpenAI
import os

st.set_page_config(page_title="L&T Financial AI Agent", layout="wide")
st.title("🤖 L&T Financial Analyst AI")

# 1. API Key from Secrets
if "OPENAI_API_KEY" in st.secrets:
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
else:
    st.error("Please add OPENAI_API_KEY to Streamlit Secrets.")
    st.stop()

# 2. Database Initialization (Using a simple path to avoid reflection errors)
@st.cache_resource
def init_db():
    db_file = "lnt_data.db"
    # Clean up old DB file if it exists to start fresh
    if os.path.exists(db_file):
        os.remove(db_file)
        
    con = duckdb.connect(db_file)
    
    # Load Data
    if os.path.exists("pnl_data.xlsx"):
        df_pnl = pd.read_excel("pnl_data.xlsx", engine="openpyxl")
        con.execute("CREATE TABLE pnl_data AS SELECT * FROM df_pnl")
        
    if os.path.exists("ut_data.xlsx"):
        df_ut = pd.read_excel("ut_data.xlsx", engine="openpyxl")
        con.execute("CREATE TABLE ut_data AS SELECT * FROM df_ut")
    
    con.close()
    
    # We add 'view_support=False' to simplify the reflection process
    return SQLDatabase.from_uri(f"duckdb:///{db_file}", view_support=False)

@st.cache_data
def get_kpi_context():
    if os.path.exists("kpi_directory.xlsx"):
        df_kpi = pd.read_excel("kpi_directory.xlsx", engine="openpyxl")
        return df_kpi.to_string()
    return "No KPI directory found."

# Initialize
try:
    db = init_db()
    kpi_context = get_kpi_context()
except Exception as e:
    st.error(f"Critical Database Error: {e}")
    st.stop()

# 3. Agent Setup
llm = ChatOpenAI(model="gpt-4o", temperature=0)
toolkit = SQLDatabaseToolkit(db=db, llm=llm)

system_message = f"""
You are a senior L&T Financial Analyst. Use 'pnl_data' and 'ut_data' tables.
KPI RULES: {kpi_context}
"""

agent_executor = create_sql_agent(
    llm=llm,
    toolkit=toolkit,
    verbose=True,
    agent_type="openai-tools",
    extra_prompt_messages=[("system", system_message)]
)

# 4. Chat Interface
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask: What is the total FMCG Revenue?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analyzing..."):
            try:
                response = agent_executor.invoke({"input": prompt})
                st.markdown(response["output"])
                st.session_state.messages.append({"role": "assistant", "content": response["output"]})
            except Exception as e:
                st.error(f"Agent Error: {e}")
