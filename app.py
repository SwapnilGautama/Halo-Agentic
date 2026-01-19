# app.py

import os
import sys
import streamlit as st
import hashlib

# -------------------------------------------------
# Ensure repo root is on PYTHONPATH (CRITICAL FOR CLOUD)
# -------------------------------------------------
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# -------------------------------------------------
# Imports (AFTER path fix)
# -------------------------------------------------
from agents.architect import ArchitectAgent
from agents.analyst import AnalystAgent
from agents.bi import BIAgent
from agents.validator import ValidationAgent
import config

# -------------------------------------------------
# Streamlit Page Config
# -------------------------------------------------
st.set_page_config(
    page_title="Metadata-Driven AI Analytics Platform",
    layout="wide"
)

st.title("🤖 Metadata-Driven AI Analytics Platform")
st.subheader("Ask a business question")

# -------------------------------------------------
# File existence checks (FAIL FAST)
# -------------------------------------------------
KPI_PATH = "metadata/kpi_directory.xlsx"
PROMPT_PATH = "prompts/architect_prompt.txt"

missing_files = []
if not os.path.exists(KPI_PATH):
    missing_files.append(KPI_PATH)

if not os.path.exists(PROMPT_PATH):
    missing_files.append(PROMPT_PATH)

if missing_files:
    st.error("❌ Required files missing:")
    for f in missing_files:
        st.code(f)
    st.stop()

# -------------------------------------------------
# Initialize Agents (cached)
# -------------------------------------------------
@st.cache_resource(show_spinner=False)
def init_agents():
    architect = ArchitectAgent(
        kpi_directory_path=KPI_PATH,
        prompt_path=PROMPT_PATH,
        model=config.MODEL_NAME
    )

    analyst = AnalystAgent()
    bi = BIAgent()
    validator = ValidationAgent()

    return architect, analyst, bi, validator


architect, analyst, bi, validator = init_agents()

# -------------------------------------------------
# User Input (NO EMPTY LABEL)
# -------------------------------------------------
user_query = st.text_input(
    label="Business Question",
    placeholder="e.g. give me FTE by segment for June 2025",
    label_visibility="collapsed"
)

# -------------------------------------------------
# Run Pipeline
# -------------------------------------------------
if user_query:
    with st.spinner("Thinking..."):

        # Step 1: Architect
        architecture = architect.route(user_query)

        if not architecture:
            st.warning("❌ Could not determine KPI.")
            st.stop()

        # Step 2: Validation
        validation = validator.validate(architecture)
        if not validation["is_valid"]:
            st.error(validation["reason"])
            st.stop()

        # Step 3: Analysis
        analysis_output = analyst.run(architecture)

        # Step 4: BI Formatting
        final_output = bi.render(analysis_output)

    # -------------------------------------------------
    # Display Results
    # -------------------------------------------------
    st.success("✅ Query processed successfully")

    if "summary" in final_output:
        st.markdown("### 📌 Summary")
        st.write(final_output["summary"])

    if "table" in final_output:
        st.markdown("### 📊 Data")
        st.dataframe(final_output["table"])

    if "chart" in final_output:
        st.markdown("### 📈 Chart")
        st.plotly_chart(final_output["chart"], use_container_width=True)
