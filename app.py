import streamlit as st
import pandas as pd
import duckdb
import plotly.express as px
import os
from typing import TypedDict, Annotated, List, Union
from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langgraph.graph import StateGraph, END

st.set_page_config(page_title="L&T Financial Multi-Agent", layout="wide")
st.title("🏛️ L&T AI Analyst: Self-Correcting System")

# 1. DATABASE & SCHEMA INJECTION
@st.cache_resource
def init_db_and_schema():
    db_file = "lnt_data.db"
    con = duckdb.connect(db_file)
    schema_info = ""
    for f in ["pnl_data.xlsx", "ut_data.xlsx"]:
        if os.path.exists(f):
            t_name = f.split(".")[0]
            df = pd.read_excel(f, engine="openpyxl")
            con.execute(f"CREATE OR REPLACE TABLE {t_name} AS SELECT * FROM df")
            schema_info += f"Table {t_name} columns: {list(df.columns)}\n"
    con.close()
    return SQLDatabase.from_uri(f"duckdb:///{db_file}", view_support=False), schema_info

db, db_schema = init_db_and_schema()
llm = ChatOpenAI(model="gpt-4o", temperature=0)

# 2. STATE WITH RETRY COUNTER
class AgentState(TypedDict):
    question: str
    sql_query: str
    raw_data: Union[pd.DataFrame, str]
    error_log: str
    retry_count: int
    final_narrative: str

# 3. NODES WITH FEEDBACK
def analyst_node(state: AgentState):
    """Analyst uses schema info and previous error logs to write SQL."""
    retry_msg = f"Previous Error: {state.get('error_log', 'None')}" if state.get('error_log') else ""
    prompt = f"""
    Schema: {db_schema}
    Question: {state['question']}
    {retry_msg}
    Write a DuckDB SQL query. Use double quotes for columns with spaces (e.g. "Amount in USD").
    Return ONLY the SQL.
    """
    response = llm.invoke(prompt)
    return {"sql_query": response.content.replace("```sql", "").replace("```", "").strip(), "retry_count": state.get("retry_count", 0) + 1}

def reviewer_node(state: AgentState):
    """Reviewer validates logic and attempts execution."""
    try:
        con = duckdb.connect("lnt_data.db")
        data = con.execute(state['sql_query']).df()
        con.close()
        return {"raw_data": data, "error_log": "", "review_status": "Approved"}
    except Exception as e:
        return {"error_log": str(e), "review_status": "Fix Needed"}

def router(state: AgentState):
    """Decides whether to retry or finish."""
    if not state.get("error_log") or state["retry_count"] >= 3:
        return "visualizer"
    return "analyst"

def visualizer_node(state: AgentState):
    """Generates final answer and chart."""
    if state.get("error_log"):
        return {"final_narrative": f"Failed after 3 attempts. Error: {state['error_log']}"}
    narrative = llm.invoke(f"Summarize this financial data: {state['raw_data'].to_string()}").content
    return {"final_narrative": narrative}

# 4. GRAPH WITH LOOPS
workflow = StateGraph(AgentState)
workflow.add_node("analyst", analyst_node)
workflow.add_node("reviewer", reviewer_node)
workflow.add_node("visualizer", visualizer_node)

workflow.set_entry_point("analyst")
workflow.add_edge("analyst", "reviewer")
workflow.add_conditional_edges("reviewer", router, {"analyst": "analyst", "visualizer": "visualizer"})
workflow.add_edge("visualizer", END)
app = workflow.compile()

# 5. UI
if prompt := st.chat_input("Show me a bar chart of Revenue by Segment"):
    with st.spinner("Team is collaborating (with self-correction)..."):
        result = app.invoke({"question": prompt, "retry_count": 0})
        st.write(result["final_narrative"])
        if not result.get("error_log"):
            st.dataframe(result["raw_data"])
            # Auto-charting logic
            df = result["raw_data"]
            if len(df.columns) >= 2:
                st.plotly_chart(px.bar(df, x=df.columns[0], y=df.columns[1], template="plotly_white"))
