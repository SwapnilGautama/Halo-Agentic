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

# -----------------------------
# Initialize Agents
# -----------------------------
@st.cache_resource
def load_agents():
    return {
        "architect": ArchitectAgent(
            kpi_directory_path=KPI_DIRECTORY_PATH,
            prompt_path=ARCHITECT_PROMPT_PATH,
            model=MODEL_NAME
        ),
        "analyst": AnalystAgent(),
        "validator": ValidationAgent()
    }

try:
    agents = load_agents()
except Exception as e:
    st.error("❌ Agent initialization failed")
    st.exception(e)
    st.stop()

architect = agents["architect"]
analyst = agents["analyst"]
validator = agents["validator"]

# -----------------------------
# User Input
# -----------------------------
user_query = st.text_input("")

if user_query:
    with st.spinner("Thinking..."):
        try:
            # 🔴 FIX IS HERE (NO route())
            architecture = architect.run(user_query)

            st.write("### 🧠 Architecture Output")
            st.json(architecture)

            if architecture.get("kpi_id") is None:
                st.warning("⚠️ Could not determine KPI")
                st.stop()

            df = analyst.run(architecture)

            warnings, errors = validator.validate(
                architecture["kpi_id"],
                df,
                architecture.get("comparison")
            )

            if errors:
                st.error("❌ Validation Errors")
                st.write(errors)
            else:
                st.success("✅ Result")
                st.dataframe(df)

                if warnings:
                    st.warning("⚠️ Warnings")
                    st.write(warnings)

        except Exception as e:
            st.error("❌ Execution failed")
            st.exception(e)
