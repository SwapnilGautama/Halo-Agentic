import streamlit as st
import json

from config import (
    KPI_DIRECTORY_PATH,
    ARCHITECT_PROMPT_PATH,
    MODEL_NAME
)

from agents.architect import ArchitectAgent
from agents.analyst import AnalystAgent
from agents.bi import BIAgent
from agents.validator import ValidationAgent


# -----------------------------
# Streamlit Setup
# -----------------------------
st.set_page_config(
    page_title="Metadata-Driven AI Analytics Platform",
    layout="wide"
)

st.title("🤖 Metadata-Driven AI Analytics Platform")
st.subheader("Ask a business question")

user_query = st.text_input("")


# -----------------------------
# Initialize Agents (NO CACHE)
# -----------------------------
try:
    architect = ArchitectAgent(
        kpi_directory_path=KPI_DIRECTORY_PATH,
        prompt_path=ARCHITECT_PROMPT_PATH,
        model=MODEL_NAME
    )

    analyst = AnalystAgent()
    validator = ValidationAgent()
    bi = BIAgent()

except Exception as e:
    st.error("❌ Agent initialization failed")
    st.exception(e)
    st.stop()


# -----------------------------
# Run Pipeline
# -----------------------------
if user_query:

    with st.spinner("Thinking..."):

        # ---- STEP 1: ARCHITECT ----
        architecture = architect.route(user_query)

        # JSON safety
        if isinstance(architecture, str):
            try:
                architecture = json.loads(architecture)
            except json.JSONDecodeError:
                st.error("❌ Architect returned invalid JSON")
                st.code(architecture)
                st.stop()

        if not architecture or not architecture.get("kpi_id"):
            st.warning("Could not determine KPI.")
            st.json(architecture)
            st.stop()

        # ---- STEP 2: ANALYST ----
        try:
            df = analyst.run(
                kpi_id=architecture["kpi_id"],
                filters=architecture.get("filters", {}),
                comparison=architecture.get("comparison")
            )
        except Exception as e:
            st.error("❌ Analyst execution failed")
            st.exception(e)
            st.stop()

        # ---- STEP 3: VALIDATION ----
        warnings, errors = validator.validate(
            kpi_id=architecture["kpi_id"],
            df=df,
            comparison=architecture.get("comparison")
        )

        if errors:
            st.error("❌ Validation failed")
            st.json(errors)
            st.stop()

        if warnings:
            st.warning("⚠️ Validation warnings")
            st.json(warnings)

        # ---- STEP 4: BI AGENT ----
        output = bi.render(
            df=df,
            kpi_id=architecture["kpi_id"]
        )

        # -----------------------------
        # Final Output
        # -----------------------------
        st.success("✅ Query executed successfully")
        st.dataframe(df)

        if output:
            st.markdown("### 📊 Insights")
            st.write(output)
