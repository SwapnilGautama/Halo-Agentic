import streamlit as st
import pandas as pd
import duckdb
import os
import matplotlib.pyplot as plt
from langchain_openai import ChatOpenAI

# --- 1. DATA ENGINE (The Foundation) ---
@st.cache_resource
def init_engine():
    conn = duckdb.connect(database=':memory:')
    
    # Load standardized files
    # Expecting: pnl_data (Month, FinalCustomerName, USD, Type, Group1)
    # Expecting: ut_data (Date, FinalCustomerName, PSNo, TotalBillableHours, NetAvailableHours)
    if os.path.exists("ut_data.xlsx"):
        df_ut = pd.read_excel("ut_data.xlsx")
        df_ut['Date'] = pd.to_datetime(df_ut['Date'])
        conn.register("ut_data", df_ut)

    if os.path.exists("pnl_data.xlsx"):
        df_pnl = pd.read_excel("pnl_data.xlsx")
        df_pnl['Month'] = pd.to_datetime(df_pnl['Month'])
        conn.register("pnl_data", df_pnl)

    # Load Knowledge Directories
    kpi_lib = pd.read_excel("kpi_directory.xlsx").to_string() if os.path.exists("kpi_directory.xlsx") else ""
    field_lib = pd.read_excel("field_directory.xlsx").to_string() if os.path.exists("field_directory.xlsx") else ""
    
    return conn, kpi_lib, field_lib

conn, kpi_ctx, field_ctx = init_engine()

# --- 2. MULTI-AGENT ANALYST ---
def run_financial_analysis(user_query):
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # ARCHITECT: Strictly maps the query to the Directory rules
    architect_prompt = f"""
    You are a Financial Systems Architect. Use the following directories as your ONLY source of truth.
    
    FIELD DIRECTORY: {field_ctx}
    KPI DIRECTORY: {kpi_ctx}

    RULES:
    1. JOIN: If query needs both P&L and UT data, join on 'FinalCustomerName' AND 'Month' = 'Date'.
    2. MARGIN %: 
       - Numerator: (SUM(USD) FILTER (WHERE Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE'))) - (SUM(USD) FILTER (WHERE Type = 'Cost'))
       - Denominator: SUM(USD) FILTER (WHERE Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE'))
       - Final_Result: (Numerator / NULLIF(Denominator, 0)) * 100
    3. FTE: COUNT(DISTINCT PSNo)
    
    OUTPUT:
    You must return a SQL query that selects:
    - The Dimension (e.g., FinalCustomerName or Month)
    - The 'Numerator' (Calculated value)
    - The 'Denominator' (Calculated value)
    - The 'Final_Result' (The KPI result)
    
    Return ONLY the DuckDB SQL.
    """
    
    sql = llm.invoke(architect_prompt + f"\nUser Query: {user_query}").content.strip().replace("```sql", "").replace("```", "")
    
    try:
        df = conn.execute(sql).df()
        
        # VIZ AGENT: Decides best chart based on data shape
        viz_prompt = f"Data columns: {list(df.columns)}. If the first column is a date, return 'line'. If it's a category/customer, return 'bar'. 1 word only."
        chart_choice = llm.invoke(viz_prompt).content.strip().lower()
        
        return sql, df, chart_choice
    except Exception as e:
        return sql, None, str(e)

# --- 3. THE INTERFACE ---
st.title("🏛️ L&T Executive Intelligence")
st.markdown("---")

query = st.text_input("Ask a question (e.g., 'Contribution Margin by Customer' or 'FTE trend'):")

if query:
    sql, df, chart_type = run_financial_analysis(query)
    
    if df is not None:
        tab1, tab2 = st.tabs(["📊 Executive Dashboard", "🔍 Logic & Details"])
        
        with tab1:
            # CFO Narrative Summary
            llm_summary = ChatOpenAI(model="gpt-4o", temperature=0)
            summary = llm_summary.invoke(f"Provide a 1-sentence CFO insight on these results: {df.head(5).to_string()}").content
            st.info(f"**Analyst Insight:** {summary}")
            
            # Professional Visualization
            fig, ax = plt.subplots(figsize=(10, 4))
            x_col = df.columns[0]
            y_col = 'Final_Result'
            
            if 'line' in chart_type:
                ax.plot(df[x_col].astype(str), df[y_col], marker='o', color='#00529B', linewidth=2)
            else:
                ax.bar(df[x_col].astype(str), df[y_col], color='#00529B')
            
            plt.xticks(rotation=45)
            ax.set_ylabel(y_col)
            ax.set_title(query, fontweight='bold')
            st.pyplot(fig)
            
            # Simple Output Table
            st.write("### Data Table")
            st.dataframe(df[[x_col, 'Final_Result']])

        with tab2:
            st.subheader("Audit Trail")
            st.markdown("This tab provides full transparency into the AI's calculation logic.")
            
            col1, col2 = st.columns(2)
            with col1:
                st.write("**Fields Used:**")
                st.write(f"- Table 1: `pnl_data` (USD, Type, Group1)")
                st.write(f"- Table 2: `ut_data` (PSNo, Date)")
            
            with col2:
                st.write("**Formula Applied:**")
                if "Margin" in query:
                    st.latex(r"Margin \% = \frac{Revenue - Cost}{Revenue} \times 100")
                elif "FTE" in query:
                    st.latex(r"FTE = Count(Distinct(PSNo))")
            
            st.markdown("---")
            st.write("**Calculation Components (Numerator & Denominator):**")
            st.dataframe(df) # Shows the full breakdown
            
            st.write("**Generated SQL Query:**")
            st.code(sql, language='sql')
    else:
        st.error(f"Execution Error: {chart_type}")
        st.code(sql)
