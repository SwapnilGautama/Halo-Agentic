import streamlit as st
import traceback
from agents.architect import ArchitectAgent
from agents.analyst import AnalystAgent
from agents.bi import BIAgent
from config import KPI_DIRECTORY_PATH, ARCHITECT_PROMPT_PATH, MODEL_NAME

st.set_page_config(page_title="L&T AI Analyst", layout="wide")
st.title("🤖 L&T Executive AI Analyst")

@st.cache_resource
def initialize_agents():
    """Initializes agents once to save memory and prevent crashes."""
    return {
        "architect": ArchitectAgent(KPI_DIRECTORY_PATH, ARCHITECT_PROMPT_PATH, MODEL_NAME),
        "analyst": AnalystAgent(),
        "bi": BIAgent(KPI_DIRECTORY_PATH)
    }

agents = initialize_agents()

if agents:
    user_query = st.text_input("Ask a question about Revenue, Margin, or FTE:")

    if user_query:
        try:
            with st.spinner("Analyzing..."):
                # 1. Architect: Maps KPI and Filters
                arch = agents["architect"].run(user_query)
                
                if not arch.get("kpi_id"):
                    st.warning("Could not identify KPI. Please try 'Revenue' or 'Margin %'.")
                    st.stop()

                # 2. Analyst: Generates and Runs SQL
                df = agents["analyst"].run(arch)

                # 3. BI & Audit
                if not df.empty and "Error" not in df.columns:
                    tab_dash, tab_audit = st.tabs(["📊 Dashboard", "🔍 Technical Audit"])
                    with tab_dash:
                        agents["bi"].render(arch["kpi_id"], df)
                    with tab_audit:
                        st.code(agents["analyst"].last_sql, language="sql")
                        st.dataframe(df)
                else:
                    st.error(f"Analysis failed: {df.get('Error', ['No data found'])[0]}")

        except Exception:
            st.error("A critical error occurred.")
            st.expander("Technical Traceback").code(traceback.format_exc())
