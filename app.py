import streamlit as st
import pandas as pd
import duckdb
import plotly.express as px
import os
from typing import TypedDict, Annotated, List, Union
from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langgraph.graph import StateGraph, END

# --- PAGE CONFIG ---
st.set_page_config(page_title="L&T Financial Multi-Agent", layout="wide")
st.title("🏛️ L&T AI Analyst: Multi-Agent System")

# 1. API KEY SETUP
if "OPENAI_API_KEY" in st.secrets:
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
else:
    st.error("Add OPENAI_API_KEY to Secrets.")
    st.stop()

# 2. DATABASE INIT
@st.cache_resource
def init_db():
    db_file = "lnt_data.db"
    con = duckdb.connect(db_file)
    for f in ["pnl_data.xlsx", "ut_data.xlsx"]:
        if os.path.exists(f):
            t_name = f.split(".")[0]
            df = pd.read_excel(f, engine="openpyxl")
            con.execute(f"CREATE OR REPLACE TABLE {t_name} AS SELECT * FROM df")
    con.close()
    return SQLDatabase.from_uri(f"duckdb:///{db_file}", view_support=False)

db = init_db()
llm = ChatOpenAI(model="gpt-4o", temperature=0) # Deterministic for accuracy

# --- MULTI-AGENT STATE ---
class AgentState(TypedDict):
    question: str
    sql_query: str
    raw_data: Union[pd.DataFrame, str]
    review_status: str # "Approved" or "Fix Needed"
    final_narrative: str

# --- AGENT NODES ---

def analyst_node(state: AgentState):
    """Analyst: Generates the SQL query based on schema."""
    # Simplified prompt for demonstration; in production, use a full SQL chain
    prompt = f"Given the tables pnl_data and ut_data, write a SQL query to answer: {state['question']}. Return ONLY the SQL query code."
    response = llm.invoke(prompt)
    return {"sql_query": response.content.replace("```sql", "").replace("```", "").strip()}

def reviewer_node(state: AgentState):
    """Reviewer: Validates SQL logic and checks for hallucinations."""
    validation_prompt = f"Review this SQL: {state['sql_query']} for the question: {state['question']}. Does it use correct columns? Answer 'Approved' or 'Fix Needed'."
    check = llm.invoke(validation_prompt)
    
    if "Approved" in check.content:
        # If approved, execute the query
        try:
            con = duckdb.connect("lnt_data.db")
            data = con.execute(state['sql_query']).df()
            con.close()
            return {"raw_data": data, "review_status": "Approved"}
        except Exception as e:
            return {"review_status": "Fix Needed", "final_narrative": f"Execution Error: {str(e)}"}
    return {"review_status": "Fix Needed"}

def visualizer_node(state: AgentState):
    """Visualizer: Creates Narrative and Plotly charts."""
    if state["review_status"] == "Approved":
        narrative = llm.invoke(f"Summarize this data for a CFO: {state['raw_data'].to_string()}").content
        return {"final_narrative": narrative}
    return {"final_narrative": "The Reviewer rejected the query logic. Please try rephrasing."}

# --- GRAPH ORCHESTRATION ---
workflow = StateGraph(AgentState)
workflow.add_node("analyst", analyst_node)
workflow.add_node("reviewer", reviewer_node)
workflow.add_node("visualizer", visualizer_node)

workflow.set_entry_point("analyst")
workflow.add_edge("analyst", "reviewer")
workflow.add_edge("reviewer", "visualizer")
workflow.add_edge("visualizer", END)

app = workflow.compile()

# --- CHAT UI ---
if prompt := st.chat_input("Ask about FMCG Revenue Trend..."):
    with st.spinner("Multi-Agent Team (Analyst -> Reviewer -> Visualizer) at work..."):
        result = app.invoke({"question": prompt})
        
        st.subheader("Analysis Results")
        st.write(result["final_narrative"])
        
        if result["review_status"] == "Approved":
            df = result["raw_data"]
            st.dataframe(df)
            
            # Simple Chart Logic
            if len(df.columns) >= 2:
                fig = px.bar(df, x=df.columns[0], y=df.columns[1], title="Automated Visualization", template="plotly_white")
                st.plotly_chart(fig, use_container_width=True)
