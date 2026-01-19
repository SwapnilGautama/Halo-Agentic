import streamlit as st
import json
import re

from agents.architect import ArchitectAgent
from agents.analyst import AnalystAgent, load_kpi_directory
from agents.validator import ValidationAgent
from agents.bi import BIAgent


# -------------------------------
# App Config
# -------------------------------
st.set_page_config(
    page_title="Metadata-Driven AI Analytics Platform",
    layout="wide"
)

st.title("🤖 Metadata-Driven AI Analytics Platform")
st.subheader("Ask a business question")


# -------------------------------
# Load Agents
# -------------------------------
architect = ArchitectAgent()
analyst = AnalystAgent()
validator = ValidationAgent()
bi_agent = BIAgent()

# Load KPI Directory once
kpi_df = load_kpi_directory()


# -------------------------------
# Helper: Safe JSON Parse
# -------------------------------
def parse_llm_json(raw_text: str):
    """
    Cleans markdown-wrapped JSON and parses safely
    """
    if raw_text is None:
        return None

    # Remove ```json ... ```
    cleaned = re.sub(r"```json|```", "", raw_text).strip()

    try:
        return json.loads(cleaned)
    except Exception as e:
        st.error("❌ Failed to parse LLM JSON")
        st.code(cleaned)
        raise e


# -------------------------------
# User Input
# -------------------------------
user_query = st.text_input(
    label="Business Question",
    placeholder="e.g. give me fte by segment for june 2025",
    label_visibility="collapsed"
)


# -------------------------------
# Main Flow
# -------------------------------
if user_query:

    with st.spinner("Thinking..."):

        # =========================
        # STEP 1 — ARCHITECT
        # =========================
        raw_architecture = architect.run(user_query)

        if not raw_architecture:
            st.warning("❌ Could not determine KPI.")
            st.stop()

        architecture = parse_llm_json(raw_architecture)

        if not architecture or not architecture.get("kpi_id"):
            st.warning("❌ KPI not resolved.")
            st.stop()

        st.success(f"✅ KPI Identified: {architecture['kpi_id']}")


        # =========================
        # STEP 2 — VALIDATION
        # =========================
        validation = validator.validate(architecture, kpi_df)

        if not validation["is_valid"]:
            st.error(validation["reason"])
            st.stop()

        st.success("✅ Request validated")


        # =========================
        # STEP 3 — ANALYSIS
        # =========================
        analysis_result = analyst.execute(architecture)

        if analysis_result is None:
            st.error("❌ Analysis failed")
            st.stop()


        # =========================
        # STEP 4 — BI RENDERING
        # =========================
        bi_agent.render(analysis_result)
