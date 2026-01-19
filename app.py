import streamlit as st
import json
import pandas as pd

from agents.architect import ArchitectAgent
from agents.analyst import AnalystAgent
from agents.validator import ValidationAgent
from agents.bi import BIAgent

from config import MODEL_NAME

# ----------------------------------
# Streamlit Page Config
# ----------------------------------
st.set_page_config(
    page_title="Metadata-Driven AI Analytics Platform",
    layout="wide"
)

st.title("🤖 Metadata-Driven AI Analytics Platform")

# ----------------------------------
# Initialize Agents (CORRECTLY)
# ----------------------------------
architect = ArchitectAgent(
    kpi_directory_path="metadata/kpi_directory.xlsx",
    prompt_path="prompts/architect_prompt.txt",
    model=MODEL_NAME
)

analyst = AnalystAgent()
validator = ValidationAgent()
bi_agent = BIAgent()

# ----------------------------------
# UI Input
# ----------------------------------
st.subheader("Ask a business question")

user_query = st.text_input(
    label="Business Question",
    placeholder="e.g. give me fte by segment for june 2025",
    label_visibility="collapsed"
)

# ----------------------------------
# Main Execution
# ----------------------------------
if user_query:

    with st.spinner("Thinking..."):

        # -------------------------------
        # Step 1: Architect
        # -------------------------------
        raw_response = architect.run(user_query)

        # Defensive: strip markdown fences
        if isinstance(raw_response, str):
            raw_response = raw_response.strip()
            if raw_response.startswith("```"):
                raw_response = raw_response.replace("```json", "").replace("```", "").strip()

        try:
            architecture = json.loads(raw_response)
        except Exception as e:
            st.error("❌ Architect returned invalid JSON")
            st.code(raw_response)
            st.stop()

        if not architecture or architecture.get("kpi_id") is None:
            st.warning("❌ Could not determine KPI.")
            st.stop()

        # -------------------------------
        # Step 2: Validation
        # -------------------------------
        validation = validator.validate(
            architecture=architecture,
            df=None  # placeholder until BI layer loads real data
        )

        if not validation["is_valid"]:
            st.error(validation["reason"])
            st.stop()

        # -------------------------------
        # Step 3: BI Execution
        # -------------------------------
        result = bi_agent.execute(architecture)

        # -------------------------------
        # Step 4: Display
        # -------------------------------
        st.success("✅ Analysis Complete")

        if isinstance(result, pd.DataFrame):
            st.dataframe(result)
        else:
            st.write(result)
