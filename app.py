import streamlit as st
import pandas as pd
import duckdb
import re
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- 1. DATA ENGINE ---
@st.cache_resource
def initialize_engine():
    conn = duckdb.connect(database=':memory:')
    
    # Load P&L
    pnl = pd.read_excel("pnl_data.xlsx")
    pnl['Month'] = pd.to_datetime(pnl['Month'])
    pnl.columns = [c.strip() for c in pnl.columns]
    conn.register("pnl_data", pnl)
    
    # Load UT (FTE logic lives here)
    ut = pd.read_excel("ut_data.xlsx")
    ut['Date'] = pd.to_datetime(ut['Date'])
    ut.columns = [c.strip() for c in ut.columns]
    conn.register("ut_data", ut)
    
    # Directories
    f_dir = pd.read_excel("field_directory.xlsx").to_string()
    k_dir = pd.read_excel("kpi_directory.xlsx").to_string()
    return conn, f_dir, k_dir

conn, FIELD_BIBLE, KPI_BIBLE = initialize_engine()

# --- 2. THE SHIELDED PIPELINE ---

def clean_sql(raw_sql):
    """Kills conversational filler like 'To', 'Certainly', or markdown."""
    clean = re.sub(r"```sql|```", "", raw_sql).strip()
    # Find the start of the real query
    match = re.search(r"\b(WITH|SELECT)\b", clean, re.IGNORECASE)
    if match:
        return clean[match.start():]
    return clean

def execute_pipeline(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # AGENT 1: THE ARCHITECT (Intent & Field Mapping)
    architect_prompt = f"""
    FIELDS: {FIELD_BIBLE}
    KPIs: {KPI_BIBLE}
    
    USER QUESTION: {user_query}
    
    TASK: 
    1. Identify if this is about P&L (Money) or UT (FTE/Hours). 
    2. If FTE is mentioned, use table 'ut_data' and column 'PSNo'. 
    3. If 'Segment' is mentioned, use column 'Segment'.
    4. FORGET previous questions about Margin unless asked now.
    """
    logic_plan = llm.invoke(architect_prompt).content

    # AGENT 2: THE ANALYST (SQL Generation)
    analyst_prompt = f"""
    LOGIC PLAN: {logic_plan}
    
    RULES:
    1. START SQL IMMEDIATELY. No 'To' or 'Certainly'.
    2. If FTE: COUNT(DISTINCT PSNo) from ut_data.
    3. If Margin %: Use the 2-CTE approach (Rev and Cost).
    4. Group by 'Segment' if requested.
    """
    sql_raw = llm.invoke(analyst_prompt).content
    final_sql = clean_sql(sql_raw)

    try:
        df = conn.execute(final_sql).df()
        return "SUCCESS", logic_plan, final_sql, df
    except Exception as e:
        return "ERROR", logic_plan, final_sql, str(e)

# --- 3. UI ---
st.set_page_config(layout="wide")
st.title("🏛️ L&T Executive Analyst v26.0")

q = st.text_input("Enter your query:", placeholder="e.g., FTE by Segment for June 2025")

if q:
    status, logic, sql, result = execute_pipeline(q)
    
    if status == "SUCCESS":
        st.subheader("📊 Analysis Results")
        c1, c2 = st.columns([1, 2])
        with c1:
            st.dataframe(result)
        with c2:
            if not result.empty:
                fig, ax = plt.subplots()
                result.plot(kind='bar', x=result.columns[0], y=result.columns[-1], ax=ax, color='#00529B')
                st.pyplot(fig)
        
        # TAB 2: AUDIT LOG (Formula, SQL, and Raw Values)
        st.markdown("---")
        with st.expander("🧾 View Formula, SQL, and Calculation Details"):
            t1, t2, t3 = st.tabs(["Formula Used", "Generated SQL", "Numerator/Denominator Used"])
            with t1:
                st.info(logic)
            with t2:
                st.code(sql, language="sql")
            with t3:
                st.write("Below is the underlying data used for this specific calculation:")
                st.dataframe(result)
    else:
        st.error(f"SQL Error: {result}")
        st.code(sql)
