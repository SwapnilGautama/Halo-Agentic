import streamlit as st
import traceback
from agents.architect import ArchitectAgent
from agents.analyst import AnalystAgent
from agents.bi import BIAgent
from config import KPI_DIRECTORY_PATH, ARCHITECT_PROMPT_PATH, MODEL_NAME

st.set_page_config(page_title="L&T Executive AI Analyst", layout="wide")
st.title("🤖 L&T Executive AI Analyst")

# --- GLOBAL SYSTEM INITIALIZATION (The Crash-Stopper) ---
@st.cache_resource
def get_system_core():
    try:
        # This loads the Excel files into DuckDB ONLY ONCE at startup
        analyst = AnalystAgent()
        architect = ArchitectAgent(KPI_DIRECTORY_PATH, ARCHITECT_PROMPT_PATH, MODEL_NAME)
        bi = BIAgent(KPI_DIRECTORY_PATH)
        return {"architect": architect, "analyst": analyst, "bi": bi}
    except Exception as e:
        st.error(f"Critical System Failure: {e}")
        return None

# Load or retrieve from cache
system = get_system_core()

if system:
    user_query = st.text_input("Analyze Data:", placeholder="e.g. What is the Margin % for June 2025?")

    if user_query:
        try:
            with st.spinner("Processing..."):
                # 1. Architect maps query to metadata
                architecture = system["architect"].run(user_query)
                
                if not architecture.get("kpi_id"):
                    st.warning("⚠️ KPI not recognized. Try 'Margin', 'Revenue', or 'FTE'.")
                    st.stop()

                # 2. Analyst runs SQL (Fast, memory-only)
                df = system["analyst"].run(architecture)

                # 3. Render
                if df is not None and not df.empty:
                    tab_res, tab_audit = st.tabs(["📊 Dashboard", "🔍 Audit"])
                    with tab_res:
                        system["bi"].render(architecture["kpi_id"], df)
                    with audit_tab:
                        st.code(system["analyst"].last_sql, language="sql")
                        st.dataframe(df)
                else:
                    st.error("No data found for this period/segment.")

        except Exception:
            st.error("An error occurred during processing.")
            st.expander("Technical Log").code(traceback.format_exc())
