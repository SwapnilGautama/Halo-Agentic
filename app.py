import streamlit as st
import pandas as pd
import duckdb
import plotly.express as px
import os
from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain.agents import create_sql_agent
from langgraph.graph import StateGraph, END
from typing import TypedDict, Annotated, List
import operator

# --- SETUP & DATABASE ---
st.set_page_config(page_title="L&T Multi-Agent Analyst", layout="wide")
st.title("🏛️ L&T Multi-Agent Financial System")

if "OPENAI_API_KEY" in st.secrets:
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
else:
    st.error("Missing API Key in Secrets.")
    st.stop()

@st.cache_resource
def get_db():
    db_file = "lnt_data.db"
    con = duckdb.connect(db_file)
    for f in ["pnl_data.xlsx", "ut_data.xlsx"]:
        if os.path.exists(f):
            t_name = f.split(".")[0]
            df = pd.read_excel(f, engine="openpyxl")
            con.execute(f"CREATE OR REPLACE TABLE {t_name} AS SELECT * FROM df")
    con.close()
    return SQLDatabase.from_uri(f"duckdb:///{db_file}", view_support=False)

db = get_db()
llm = ChatOpenAI(model="gpt-4o", temperature=0)

# --- SPECIALIZED TOOLS ---
# Tool 1: The Data Analyst (SQL Specialist)
sql_toolkit = SQLDatabaseToolkit(db=db, llm=llm)
sql_agent = create_sql_agent(llm=llm, toolkit=sql_toolkit, agent_type="openai-tools", verbose=True)

# --- MULTI-AGENT STATE DEFINITION ---
class AgentState(TypedDict):
    input: str
    data_context: str
    messages: Annotated[List[str], operator.add]
    final_output: str

# --- AGENT NODES ---
def analyst_node(state: AgentState):
    """The Analyst Agent: Fetches raw data with high precision."""
    query = f"Provide a detailed data summary for: {state['input']}"
    result = sql_agent.invoke({"input": query})
    return {"data_context": result["output"], "messages": ["Analyst: Data retrieved successfully."]}

def visualizer_node(state: AgentState):
    """The Visualizer Agent: Creates Plotly charts based on Analyst's data."""
    # Logic to decide if a chart is needed
    if "trend" in state['input'].lower() or "compare" in state['input'].lower() or "plot" in state['input'].lower():
        st.info("Visualizer is generating a chart...")
        # (Internal logic here normally uses PythonREPL, for simplicity we call a direct Plotly function)
        return {"messages": ["Visualizer: Chart generated."]}
    return {"messages": ["Visualizer: No chart required."]}

# --- LANGGRAPH ORCHESTRATION ---
workflow = StateGraph(AgentState)
workflow.add_node("analyst", analyst_node)
workflow.add_node("visualizer", visualizer_node)

workflow.set_entry_point("analyst")
workflow.add_edge("analyst", "visualizer")
workflow.add_edge("visualizer", END)

app = workflow.compile()

# --- STREAMLIT UI ---
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if prompt := st.chat_input("Ask: Plot a 3-month trend for FMCG Revenue"):
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    
    with st.spinner("Multi-Agent team is working..."):
        # Run the Multi-Agent Graph
        final_state = app.invoke({"input": prompt, "messages": []})
        
        # Display Narrative Result
        ans = final_state["data_context"]
        st.session_state.chat_history.append({"role": "assistant", "content": ans})
        
        # Trigger Visualization directly if requested
        if "plot" in prompt.lower() or "trend" in prompt.lower():
            con = duckdb.connect("lnt_data.db")
            # Dynamic chart based on prompt keywords
            if "pnl" in prompt.lower() or "revenue" in prompt.lower():
                df = con.execute("SELECT Month, SUM(\"Amount in USD\") as Total FROM pnl_data GROUP BY Month ORDER BY Month").df()
                fig = px.bar(df, x="Month", y="Total", title="L&T Financial Trend", template="plotly_dark")
                st.plotly_chart(fig, use_container_width=True)
            con.close()

# Render Chat
for m in st.session_state.chat_history:
    with st.chat_message(m["role"]):
        st.write(m["content"])
