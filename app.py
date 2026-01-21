import streamlit as st
import traceback
from agents.architect import ArchitectAgent
from agents.analyst import AnalystAgent
from agents.bi import BIAgent
from config import KPI_DIRECTORY_PATH, ARCHITECT_PROMPT_PATH, MODEL_NAME

st.set_page_config(page_title="L&T Executive AI Analyst", layout="wide")
st.title("🤖 L&T Executive AI Analyst")

# Use try-except inside the loader to catch path errors early
@st.cache_resource
def load_agents():
    try:
        return {
            "architect": ArchitectAgent(KPI_DIRECTORY_PATH, ARCHITECT_PROMPT_PATH, MODEL_NAME),
            "analyst": AnalystAgent(),
            "bi": BIAgent(KPI_DIRECTORY_PATH)
        }
    except Exception as e:
        st.error(f"Failed to initialize agents: {e}")
        return None

agents = load_agents()

if agents:
    user_query = st.text_input("Ask a business question:")

    if user_query:
        try:
            with st.spinner("Processing..."):
                # 1. Architect
                architecture = agents["architect"].run(user_query)
                
                if not architecture.get("kpi_id"):
                    st.warning("Could not identify KPI. Please try again.")
                    st.stop()

                # 2. Analyst
                df = agents["analyst"].run(architecture)

                # 3. UI Tabs
                if df is not None and not df.empty:
                    tab_dashboard, tab_audit = st.tabs(["📈 Dashboard", "🔍 Technical Audit"])
                    with tab_dashboard:
                        agents["bi"].render(architecture["kpi_id"], df)
                    with tab_audit:
                        st.code(agents["analyst"].last_sql, language="sql")
                        st.dataframe(df)
                else:
                    st.error("No data returned from the database.")
        except Exception as e:
            st.error("An error occurred during processing.")
            st.expander("Show Error Details").code(traceback.format_exc())
