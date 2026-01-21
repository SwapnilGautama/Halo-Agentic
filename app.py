import streamlit as st
import traceback
from agents.architect import ArchitectAgent
from agents.analyst import AnalystAgent
from agents.bi import BIAgent
from config import KPI_DIRECTORY_PATH, ARCHITECT_PROMPT_PATH, MODEL_NAME

st.set_page_config(layout="wide")
st.title("🤖 L&T Executive AI Analyst")

@st.cache_resource
def load_agents():
    return {
        "architect": ArchitectAgent(KPI_DIRECTORY_PATH, ARCHITECT_PROMPT_PATH, MODEL_NAME),
        "analyst": AnalystAgent(),
        "bi": BIAgent(KPI_DIRECTORY_PATH)
    }

agents = load_agents()
user_query = st.text_input("Ask a question:")

if user_query:
    try:
        with st.spinner("Analyzing..."):
            arch = agents["architect"].run(user_query)
            if not arch["kpi_id"]:
                st.warning("KPI not recognized.")
            else:
                df = agents["analyst"].run(arch)
                
                res_tab, audit_tab = st.tabs(["📊 Results", "🛠️ Audit"])
                with res_tab:
                    agents["bi"].render(arch["kpi_id"], df)
                with audit_tab:
                    st.code(agents["analyst"].last_sql, language="sql")
                    st.dataframe(df)
    except Exception:
        st.error("The app encountered a critical error. Details below:")
        st.code(traceback.format_exc())
