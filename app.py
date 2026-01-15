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
    st.error("Missing OPENAI_API_KEY in Secrets!")
    st.stop()

# 2. In-Memory Database Initialization (Best for Cloud)
@st.cache_resource
def init_db():
    # Create an in-memory connection
    con = duckdb.connect(database=':memory:')
    
    # Load each file if it exists in your repo
    files = {
        "pnl_data": "pnl_data.xlsx",
        "ut_data": "ut_data.xlsx"
    }
    
    for table_name, file_path in files.items():
        if os.path.exists(file_path):
            df = pd.read_excel(file_path, engine="openpyxl")
            con.register('df_temp', df)
            con.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df_temp")
            con.unregister('df_temp')
    
    # Return a LangChain SQLDatabase pointing to this in-memory session
    return SQLDatabase.from_uri("duckdb:///:memory:")

@st.cache_data
def get_kpi_context():
    if os.path.exists("kpi_directory.xlsx"):
        df_kpi = pd.read_excel("kpi_directory.xlsx", engine="openpyxl")
        return df_kpi.to_string()
    return "No KPI directory found."

# Initialize Resources
db = init_db()
kpi_context = get_kpi_context()

# 3. Agent Setup
llm = ChatOpenAI(model="gpt-4o", temperature=0)
toolkit = SQLDatabaseToolkit(db=db, llm=llm)

system_message = f"""
You are a senior L&T Financial Analyst. Use 'pnl_data' and 'ut_data' tables.
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

# 4. Chat Interface
if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask about FMCG Revenue or Utilization..."):
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
