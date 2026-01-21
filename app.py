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
def get_system():
    try:
        # Load Analyst once - this loads Excel files into DuckDB memory ONLY ONCE
        analyst = AnalystAgent()
        architect = ArchitectAgent(KPI_DIRECTORY_PATH, ARCHITECT_PROMPT_PATH, MODEL_NAME)
        bi = BIAgent(KPI_DIRECTORY_PATH)
        return {"architect": architect, "analyst": analyst, "bi": bi}
    except Exception as e:
        st.error(f"Initialization Failed: {e}")
        return None

# Get the initialized system (cached)
system = get_system()

if system:
    user_query = st.text_input("Analyze Data:", placeholder="e.g. What is the Margin % by Segment for June 2025?")

    if user_query:
        try:
            with st.spinner("Thinking..."):
                # 1. Architect maps query
                architecture = system["architect"].run(user_query)
                
                if not architecture.get("kpi_id"):
                    st.warning("⚠️ KPI not recognized. Please use terms like 'Revenue', 'Margin', or 'FTE'.")
                    st.stop()

                # 2. Analyst runs SQL (Uses pre-loaded memory)
                df = system["analyst"].run(architecture)

                # 3. Render Tabs
                if df is not None and not df.empty:
                    tab_res, tab_audit = st.tabs(["📊 Results Dashboard", "🔍 Technical Audit"])
                    with tab_res:
                        system["bi"].render(architecture["kpi_id"], df)
                    with tab_audit:
                        st.markdown("### 🛠️ Data Traceability")
                        st.code(system["analyst"].last_sql, language="sql")
                        st.dataframe(df)
                else:
                    st.error("The query returned no data. Check your filters (e.g. Month format).")

        except Exception:
            st.error("The app encountered a processing error.")
            st.expander("Technical Details").code(traceback.format_exc())
