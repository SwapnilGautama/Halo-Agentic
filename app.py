import streamlit as st
import pandas as pd
import duckdb
import plotly.express as px
import os
from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langgraph.graph import StateGraph, END
from typing import TypedDict, Union

# --- SYSTEM INITIALIZATION ---
st.set_page_config(page_title="L&T Financial Multi-Agent", layout="wide")
st.title("🏛️ L&T AI Analyst: Multi-Agent Team")

# 1. API Key Check
if "OPENAI_API_KEY" not in st.secrets:
    st.error("Missing OPENAI_API_KEY in Secrets!")
    st.stop()

# 2. Shared Connection (Crucial for Multi-Agent Accuracy)
@st.cache_resource
def get_shared_conn():
    # Use in-memory for zero-latency and zero-locking
    conn = duckdb.connect(database=':memory:')
    schema_desc = ""
    for f in ["pnl_data.xlsx", "ut_data.xlsx"]:
        if os.path.exists(f):
            t_name = f.replace(".xlsx", "")
            df = pd.read_excel(f, engine="openpyxl")
            conn.register("tmp_df", df)
            conn.execute(f"CREATE TABLE {t_name} AS SELECT * FROM tmp_df")
            schema_desc += f"Table '{t_name}' has columns: {list(df.columns)}\n"
    return conn, schema_desc

shared_conn, db_schema = get_shared_conn()
llm = ChatOpenAI(model="gpt-4o", temperature=0)

# --- AGENT DEFINITIONS ---
class AgentState(TypedDict):
    question: str
    sql: str
    data: Union[pd.DataFrame, str]
    feedback: str
    final_ans: str

def analyst_agent(state: AgentState):
    """The Analyst: Writes SQL using the provided schema."""
    prompt = f"Schema:\n{db_schema}\nQuestion: {state['question']}\n{state.get('feedback', '')}\nWrite DuckDB SQL. Use double quotes for columns with spaces."
    res = llm.invoke(prompt).content
    sql = res.replace("```sql", "").replace("```", "").strip()
    return {"sql": sql}

def reviewer_agent(state: AgentState):
    """The Reviewer: Executes the SQL on the shared connection to verify."""
    try:
        # Use the global shared connection
        df = shared_conn.execute(state['sql']).df()
        return {"data": df, "feedback": "Approved"}
    except Exception as e:
        return {"feedback": f"SQL Error: {str(e)}. Please fix the query."}

def visualizer_agent(state: AgentState):
    """The Visualizer: Summarizes data and creates Plotly narratives."""
    if isinstance(state['data'], pd.DataFrame):
        summary = llm.invoke(f"Act as CFO. Summarize this data: {state['data'].to_string()}").content
        return {"final_ans": summary}
    return {"final_ans": "I couldn't retrieve valid data for this request."}

# --- FLOW ORCHESTRATION ---
workflow = StateGraph(AgentState)
workflow.add_node("Analyst", analyst_agent)
workflow.add_node("Reviewer", reviewer_agent)
workflow.add_node("Visualizer", visualizer_agent)

workflow.set_entry_point("Analyst")
workflow.add_edge("Analyst", "Reviewer")

# Logic: If Reviewer approves, go to Visualizer; else, loop back once
workflow.add_conditional_edges(
    "Reviewer",
    lambda x: "Visualizer" if x["feedback"] == "Approved" else "Analyst",
    {"Visualizer": "Visualizer", "Analyst": "Analyst"}
)
workflow.add_edge("Visualizer", END)
app = workflow.compile()

# --- CHAT INTERFACE ---
if prompt := st.chat_input("Ask: What is the total Revenue by Segment?"):
    with st.spinner("Team is working (Analyst -> Reviewer -> Visualizer)..."):
        result = app.invoke({"question": prompt, "feedback": ""})
        
        st.write(result["final_ans"])
        if isinstance(result["data"], pd.DataFrame):
            df = result["data"]
            st.dataframe(df)
            # Automatic Visualization
            if len(df.columns) >= 2:
                fig = px.bar(df, x=df.columns[0], y=df.columns[1], title="L&T Insight", template="plotly_white")
                st.plotly_chart(fig)
