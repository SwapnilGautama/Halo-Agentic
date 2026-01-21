import streamlit as st

from agents.architect import ArchitectAgent
from agents.analyst import AnalystAgent
from agents.validator import ValidationAgent

from config import (
    KPI_DIRECTORY_PATH,
    ARCHITECT_PROMPT_PATH,
    MODEL_NAME
)

st.set_page_config(page_title="Metadata-Driven AI Analytics Platform", layout="wide")
st.title("🤖 Metadata-Driven AI Analytics Platform")
st.subheader("Ask a business question")

@st.cache_resource
def load_agents():
    return {
        "architect": ArchitectAgent(
            KPI_DIRECTORY_PATH,
            ARCHITECT_PROMPT_PATH,
            MODEL_NAME
        ),
        "analyst": AnalystAgent(),
        "validator": ValidationAgent(KPI_DIRECTORY_PATH)
    }

agents = load_agents()

architect = agents["architect"]
analyst = agents["analyst"]
validator = agents["validator"]

user_query = st.text_input("")

if user_query:
    with st.spinner("Thinking..."):
        architecture = architect.run(user_query)

        st.write("### 🧠 Architecture Output")
        st.json(architecture)

        if architecture["kpi_id"] is None:
            st.warning("⚠️ Could not determine KPI")
            st.stop()

        df = analyst.run(architecture)

        warnings, errors = validator.validate(
            architecture["kpi_id"],
            df,
            architecture.get("comparison")
        )

        if errors:
            st.error(errors)
        else:
            st.success("✅ Result")
            st.dataframe(df)
