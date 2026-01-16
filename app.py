import streamlit as st
import pandas as pd
import duckdb
import os
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- 1. DATA ENGINE (CLEAN & PRECISE) ---
@st.cache_resource
def init_engine():
    conn = duckdb.connect(database=':memory:')
    
    # Load and force-standardize headers
    if os.path.exists("ut_data.xlsx"):
        df = pd.read_excel("ut_data.xlsx")
        df['Date_a'] = pd.to_datetime(df['Date_a'])
        # Clean naming to stop AI confusion
        df = df.rename(columns={"Date_a": "EntryDate", "FinalCustomerName": "Customer", "PSNo": "EmpID"})
        conn.register("ut_data", df)

    if os.path.exists("pnl_data.xlsx"):
        df = pd.read_excel("pnl_data.xlsx")
        df['Month'] = pd.to_datetime(df['Month'])
        df = df.rename(columns={"Month": "EntryDate", "FinalCustomerName": "Customer", "Amount in USD": "USD"})
        conn.register("pnl_data", df)

    kpi_lib = pd.read_excel("kpi_directory.xlsx").to_string() if os.path.exists("kpi_directory.xlsx") else ""
    field_lib = pd.read_excel("field_directory.xlsx").to_string() if os.path.exists("field_directory.xlsx") else ""
    return conn, kpi_lib, field_lib

conn, kpi_lib, field_lib = init_engine()

# --- 2. MULTI-AGENT CORE ---
def financial_agent_system(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # STEP 1: LOGIC ARCHITECT
    # This agent defines the formula and SQL
    architect_prompt = f"""
    You are a Financial Systems Architect. 
    KNOWLEDGE:
    KPIs: {kpi_lib}
    FIELDS: {field_lib}
    
    SCHEMA:
    - ut_data: [EntryDate, Customer, EmpID, TotalBillableHours, NetAvailableHours]
    - pnl_data: [EntryDate, Customer, USD, Type ('Revenue' or 'Cost'), Group1]

    RULES FOR MARGIN %:
    - Numerator: SUM(USD) FILTER (WHERE Type = 'Revenue') - SUM(USD) FILTER (WHERE Type = 'Cost')
    - Denominator: SUM(USD) FILTER (WHERE Type = 'Revenue')
    - Formula: (Numerator / Denominator) * 100

    TASK:
    Generate a DuckDB SQL query. 
    You MUST include columns for: 
    1. The Dimension (e.g., Customer or Month)
    2. 'Numerator_Value'
    3. 'Denominator_Value'
    4. 'Final_Result'
    
    Return ONLY the SQL.
    """
    
    sql = llm.invoke(architect_prompt + f"\nUser Query: {user_query}").content.strip().replace("```sql", "").replace("```", "")
    
    try:
        df = conn.execute(sql).df()
        
        # STEP 2: VIZ AGENT
        viz_prompt = f"Data columns are {list(df.columns)}. If first column is Date/Month, return 'line'. If it's Customer/Category, return 'bar'. If comparing 2 things, return 'pie'. Return 1 word only."
        chart_type = llm.invoke(viz_prompt).content.strip().lower()
        
        return sql, df, chart_type
    except Exception as e:
        return sql, None, str(e)

# --- 3. UI LAYOUT ---
st.title("🏛️ L&T Finance Intelligence")
query = st.text_input("Ask about FTE, Margins, or Revenue:", placeholder="e.g., What is the Margin % by Customer for 2025?")

if query:
    sql, df, chart_type = financial_agent_system(query)
    
    if df is not None:
        tab1, tab2 = st.tabs(["📊 Executive View", "🔍 Logic Details"])
        
        with tab1:
            # Concise CFO Summary
            llm = ChatOpenAI(model="gpt-4o", temperature=0)
            summary = llm.invoke(f"Summarize this in 1-2 bullet points for a CFO: {df.to_string()}").content
            st.info(summary)
            
            # Smart Chart
            if len(df.columns) >= 2:
                fig, ax = plt.subplots(figsize=(10, 4))
                x_label = df.columns[0]
                y_label = 'Final_Result' if 'Final_Result' in df.columns else df.columns[-1]
                
                if 'bar' in chart_type:
                    ax.bar(df[x_label].astype(str), df[y_label], color='#00529B')
                elif 'pie' in chart_type:
                    ax.pie(df[y_label], labels=df[x_label], autopct='%1.1f%%')
                else:
                    ax.plot(df[x_label].astype(str), df[y_label], marker='o', color='#00529B')
                
                plt.xticks(rotation=45)
                ax.set_ylabel(y_label)
                st.pyplot(fig)
            
            st.dataframe(df)

        with tab2:
            st.subheader("Calculation Logic")
            # Pull the formula used from the library for display
            st.markdown(f"**Primary Formula Logic:** `(Numerator - Denominator) / Numerator` (for Margins)")
            st.write("**Numerator used:** The sum of all Revenue figures.")
            st.write("**Denominator used:** The total specific filter applied.")
            st.write("**SQL Query Generated:**")
            st.code(sql)
            
    else:
        st.error(f"Execution Error: {chart_type}")
        st.code(sql)
