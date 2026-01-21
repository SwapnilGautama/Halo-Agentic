import streamlit as st
from agents.architect import ArchitectAgent
from agents.analyst import AnalystAgent
from agents.validator import ValidationAgent
from agents.bi import BIAgent
from config import KPI_DIRECTORY_PATH, ARCHITECT_PROMPT_PATH, MODEL_NAME

st.set_page_config(page_title="L&T Metadata AI Analyst", layout="wide")
st.title("🤖 L&T Executive AI Analyst")

@st.cache_resource
def load_agents():
    return {
        "architect": ArchitectAgent(KPI_DIRECTORY_PATH, ARCHITECT_PROMPT_PATH, MODEL_NAME),
        "analyst": AnalystAgent(),
        "validator": ValidationAgent(KPI_DIRECTORY_PATH),
        "bi": BIAgent(KPI_DIRECTORY_PATH)
    }

agents = load_agents()
user_query = st.text_input("Enter your business question (e.g., 'What is the Margin % for June 2025?'):")

if user_query:
    with st.spinner("Analyzing..."):
        # 1. Architect maps query to metadata
        architecture = agents["architect"].run(user_query)
        
        if architecture["kpi_id"] is None:
            st.error("⚠️ I couldn't find a matching KPI. Try rephrasing (e.g., use 'Margin', 'Revenue', or 'FTE').")
            st.stop()

        # 2. Analyst runs the SQL logic
        df = agents["analyst"].run(architecture)

        if df.empty:
            st.warning("No data found for the selected criteria.")
        else:
            # 3. Dashboard Tabs
            tab_dashboard, tab_audit = st.tabs(["📈 Dashboard", "🔍 Technical Audit"])

            with tab_dashboard:
                agents["bi"].render(architecture["kpi_id"], df)

            with tab_audit:
                st.markdown("### 🛠️ Calculation Traceability")
                
                # Show formula
                kpi_meta = agents["bi"].get_kpi_meta(architecture["kpi_id"])
                st.info(f"**KPI:** {kpi_meta['KPI_Name']} | **Formula:** {kpi_meta['Numerator_Formula']} / {kpi_meta['Denominator_Formula']}")
                
                # Show SQL
                st.write("**Generated SQL Logic:**")
                st.code(agents["analyst"].last_sql, language="sql")
                
                # Show Raw Results
                st.write("**Raw Data Table:**")
                st.dataframe(df)
