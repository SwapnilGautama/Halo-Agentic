import streamlit as st
import traceback
from agents.architect import ArchitectAgent
from agents.analyst import AnalystAgent
from agents.bi import BIAgent
from config import KPI_DIRECTORY_PATH, ARCHITECT_PROMPT_PATH, MODEL_NAME

st.set_page_config(page_title="L&T Executive AI Analyst", layout="wide")
st.title("🤖 L&T Executive AI Analyst")

# --- GLOBAL AGENT LOADER (Prevents Crashes) ---
@st.cache_resource
def initialize_system():
    try:
        # We initialize the Analyst once here so it loads Excel data into memory only ONCE
        analyst = AnalystAgent() 
        architect = ArchitectAgent(KPI_DIRECTORY_PATH, ARCHITECT_PROMPT_PATH, MODEL_NAME)
        bi = BIAgent(KPI_DIRECTORY_PATH)
        return {"architect": architect, "analyst": analyst, "bi": bi}
    except Exception as e:
        st.error(f"Initialization Failed: {e}")
        return None

system = initialize_system()

if system:
    user_query = st.text_input("Enter your business question:", placeholder="e.g. What is the Margin % for June 2025?")

    if user_query:
        try:
            with st.spinner("Thinking..."):
                # 1. ARCHITECT: Identify KPI
                arch_output = system["architect"].run(user_query)
                
                if not arch_output.get("kpi_id"):
                    st.warning("Could not identify the KPI. Please try terms like 'Revenue', 'Margin', or 'FTE'.")
                    st.stop()

                # 2. ANALYST: Run SQL
                df = system["analyst"].run(arch_output)

                # 3. UI TABS
                if df is not None and not df.empty:
                    tab_res, tab_audit = st.tabs(["📊 Results Dashboard", "🔍 Technical Audit"])
                    
                    with tab_res:
                        system["bi"].render(arch_output["kpi_id"], df)
                    
                    with tab_audit:
                        st.markdown("### 🛠️ Query Traceability")
                        st.code(system["analyst"].last_sql, language="sql")
                        st.dataframe(df)
                else:
                    st.error("The database returned no results for this filter.")
                    
        except Exception:
            st.error("The app encountered an error. Please see details below.")
            st.expander("Technical Traceback").code(traceback.format_exc())
