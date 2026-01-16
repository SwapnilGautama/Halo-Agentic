import streamlit as st
import pandas as pd
import duckdb
import os
import matplotlib.pyplot as plt

# --- 1. THE DATA ENGINE (PHYSICAL NORMALIZATION) ---
@st.cache_resource
def power_up_engine():
    conn = duckdb.connect(database=':memory:')
    
    # Load UT Data
    if os.path.exists("ut_data.xlsx"):
        df_ut = pd.read_excel("ut_data.xlsx")
        df_ut['NormalizedDate'] = pd.to_datetime(df_ut['Date_a'])
        df_ut = df_ut.rename(columns={"FinalCustomerName": "Customer", "PSNo": "EmpID"})
        conn.register("ut_data", df_ut)

    # Load PNL Data
    if os.path.exists("pnl_data.xlsx"):
        df_pnl = pd.read_excel("pnl_data.xlsx")
        # Fix the "Sunday, June 1..." issue by forcing pandas to parse it
        df_pnl['NormalizedDate'] = pd.to_datetime(df_pnl['Month'])
        df_pnl = df_pnl.rename(columns={"FinalCustomerName": "Customer", "Amount in USD": "USD"})
        conn.register("pnl_data", df_pnl)

    kpi_lib = pd.read_excel("kpi_directory.xlsx").to_string()
    field_lib = pd.read_excel("field_directory.xlsx").to_string()
    return conn, kpi_lib, field_lib

conn, kpi_lib, field_lib = power_up_engine()

# --- 2. MULTI-AGENT LOGIC ---
def run_financial_analyst(user_query):
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    # ARCHITECT: Strictly follows the directories provided
    architect_prompt = f"""
    You are a Financial Architect. 
    DATA DIRECTORIES:
    {kpi_lib}
    {field_lib}
    
    TABLES & COLUMNS:
    - ut_data: [NormalizedDate, Customer, EmpID, TotalBillableHours, NetAvailableHours]
    - pnl_data: [NormalizedDate, Customer, USD, Type ('Revenue' or 'Cost'), Group1 ('ONSITE', 'OFFSHORE')]

    MARGIN % RULES (From KPI Directory):
    1. Revenue = SUM(USD) WHERE Group1 IN ('ONSITE', 'OFFSHORE', 'INDIRECT REVENUE')
    2. Cost = SUM(USD) WHERE Type = 'Cost'
    3. Numerator = (Revenue - Cost)
    4. Denominator = Revenue
    5. Final_Result = (Numerator / NULLIF(Denominator, 0)) * 100

    Output a DuckDB SQL query. You MUST select:
    - The dimension (Customer or strftime(NormalizedDate, '%Y-%m'))
    - The Numerator AS "Numerator"
    - The Denominator AS "Denominator"
    - The ratio AS "Final_Result"
    
    Return ONLY SQL.
    """
    
    sql = llm.invoke(architect_prompt + f"\nUser: {user_query}").content.strip().replace("```sql", "").replace("```", "")
    
    try:
        df = conn.execute(sql).df()
        
        # VIZ AGENT: Chooses chart based on data shape
        viz_choice = "line" if "NormalizedDate" in sql or "strftime" in sql else "bar"
        if len(df) > 10 and viz_choice == "bar": viz_choice = "line" # Switch if too many customers
        
        return sql, df, viz_choice
    except Exception as e:
        return sql, None, str(e)

# --- 3. THE INTERFACE ---
st.title("🏛️ L&T Financial Intelligence Unit")

query = st.text_input("Enter Question:", placeholder="e.g. What is the Margin % by Customer?")

if query:
    sql, df, viz_type = run_financial_analyst(query)
    
    if df is not None:
        tab1, tab2 = st.tabs(["📊 Executive Dashboard", "🔍 Calculation Details"])
        
        with tab1:
            # CFO Summary
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(model="gpt-4o", temperature=0)
            summary = llm.invoke(f"Provide a 1-sentence CFO insight on this data: {df.head().to_string()}").content
            st.subheader("CFO Insight")
            st.info(summary)

            # Dynamic Visuals
            fig, ax = plt.subplots(figsize=(10, 4))
            if viz_type == "bar":
                ax.bar(df.iloc[:, 0].astype(str), df['Final_Result'], color='#00529B')
            else:
                ax.plot(df.iloc[:, 0].astype(str), df['Final_Result'], marker='o', linewidth=2, color='#00529B')
            
            plt.xticks(rotation=45)
            ax.set_title(f"Target KPI: {query}")
            st.pyplot(fig)
            st.dataframe(df[['Customer', 'Final_Result']] if 'Customer' in df.columns else df)

        with tab2:
            st.subheader("Audit Trail")
            st.write("**Formula Applied:** `(Revenue - Cost) / Revenue`")
            st.write("**Component Values:**")
            st.dataframe(df) # Shows Numerator and Denominator
            st.write("**Generated SQL:**")
            st.code(sql)
    else:
        st.error(f"Logic Conflict: {viz_type}")
        st.code(sql)
