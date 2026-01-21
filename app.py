import streamlit as st
import traceback
from agents.architect import ArchitectAgent
from agents.analyst import AnalystAgent
from agents.bi import BIAgent
from config import KPI_DIRECTORY_PATH, ARCHITECT_PROMPT_PATH, MODEL_NAME

st.set_page_config(page_title="L&T AI Analyst", layout="wide")
st.title("🤖 L&T Executive AI Analyst")

@st.cache_resource
def startup_system():
    # Load everything into memory ONCE
    return {
        "architect": ArchitectAgent(KPI_DIRECTORY_PATH, ARCHITECT_PROMPT_PATH, MODEL_NAME),
        "analyst": AnalystAgent(),
        "bi": BIAgent(KPI_DIRECTORY_PATH)
    }

system = startup_system()

user_query = st.text_input("Analyze business data:", placeholder="e.g. What is the Margin % for June 2025?")

if user_query:
    try:
        with st.spinner("Processing Request..."):
            # 1. Map Intent
            arch_out = system["architect"].run(user_query)
            
            if not arch_out.get("kpi_id"):
                st.warning("KPI not identified. Please try 'Revenue' or 'Margin'.")
                st.stop()

            # 2. Run Data Engine
            data = system["analyst"].run(arch_out)

            # 3. Display Results
            if not data.empty:
                tab_dash, tab_audit = st.tabs(["📊 Dashboard", "🔍 Technical Audit"])
                with tab_dash:
                    system["bi"].render(arch_out["kpi_id"], data)
                with tab_audit:
                    st.markdown("### SQL Logic Used")
                    st.code(system["analyst"].last_sql, language="sql")
                    st.dataframe(data)
            else:
                st.error("No data found for the selected period.")

    except Exception:
        st.error("System Error encountered.")
        st.expander("Details").code(traceback.format_exc())
