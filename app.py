import streamlit as st
import os
import traceback

from agents.architect import ArchitectAgent
from agents.analyst import AnalystAgent
from agents.bi import BIAgent
from agents.validator import ValidationAgent
import config


# -------------------------------------------------
# App setup
# -------------------------------------------------
st.set_page_config(
    page_title="Metadata-Driven AI Analytics Platform",
    layout="wide"
)

st.title("🤖 Metadata-Driven AI Analytics Platform")
st.subheader("Ask a business question")


# -------------------------------------------------
# Resolve BASE DIRECTORY (CRITICAL FIX)
# -------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

KPI_DIRECTORY_PATH = os.path.join(BASE_DIR, "metadata", "kpi_directory.xlsx")
FIELD_DIRECTORY_PATH = os.path.join(BASE_DIR, "metadata", "field_directory.xlsx")
ARCHITECT_PROMPT_PATH = os.path.join(BASE_DIR, "prompts", "architect_prompt.txt")


# -------------------------------------------------
# Initialize Agents (cached)
# -------------------------------------------------
@st.cache_resource
def load_agents():
    architect = ArchitectAgent(
        kpi_directory_path=KPI_DIRECTORY_PATH,
        prompt_path=ARCHITECT_PROMPT_PATH,
        model=config.MODEL_NAME
    )

    analyst = AnalystAgent()
    validator = ValidationAgent()
    bi_agent = BIAgent()

    return architect, analyst, validator, bi_agent


architect, analyst, validator, bi_agent = load_agents()


# -------------------------------------------------
# User input
# -------------------------------------------------
user_query = st.text_input(
    label="",
    placeholder="e.g. give me fte by segment for june 2025"
)


# -------------------------------------------------
# Main execution
# -------------------------------------------------
if user_query:
    try:
        # ---------------------------
        # STEP 1: Architect Agent
        # ---------------------------
        architect_output = architect.run(user_query)

        if not architect_output or not architect_output.get("kpi_id"):
            st.warning("Could not determine KPI.")
            st.stop()

        # ---------------------------
        # STEP 2: Analyst Agent
        # ---------------------------
        analysis_output = analyst.run(architect_output)

        # ---------------------------
        # STEP 3: Validator Agent
        # ---------------------------
        validation_result = validator.run(
            analysis_output,
            architect_output
        )

        if not validation_result.get("is_valid", True):
            st.error("Validation failed.")
            st.json(validation_result)
            st.stop()

        # ---------------------------
        # STEP 4: BI Agent
        # ---------------------------
        bi_output = bi_agent.run(
            analysis_output,
            architect_output
        )

        # ---------------------------
        # Render Outputs
        # ---------------------------
        if "table" in bi_output:
            st.subheader("📊 Result Table")
            st.dataframe(bi_output["table"])

        if "chart" in bi_output:
            st.subheader("📈 Chart")
            st.pyplot(bi_output["chart"])

        if "insights" in bi_output:
            st.subheader("🧠 Insights")
            st.write(bi_output["insights"])

    except Exception as e:
        st.error("Something went wrong while processing your request.")
        st.info("The issue has been logged. Please try rephrasing.")

        # FULL DEBUG TRACE (visible in Streamlit logs)
        print("❌ APP ERROR")
        print(traceback.format_exc())
