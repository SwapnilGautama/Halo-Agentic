import streamlit as st
import json

# ----------------------------
# Agent Imports
# ----------------------------
from agents.architect import ArchitectAgent
from agents.analyst import AnalystAgent
from agents.validator import ValidatorAgent
from agents.bi import BIAgent

# ----------------------------
# App Config
# ----------------------------
st.set_page_config(
    page_title="Metadata-Driven AI Analytics Platform",
    layout="wide"
)

st.title("🤖 Metadata-Driven AI Analytics Platform")
st.subheader("Ask a business question")

# ----------------------------
# Initialize Agents (ONCE)
# ----------------------------
@st.cache_resource
def load_agents():
    return {
        "architect": ArchitectAgent(),
        "analyst": AnalystAgent(),
        "validator": ValidatorAgent(),
        "bi": BIAgent()
    }

agents = load_agents()
architect = agents["architect"]
analyst = agents["analyst"]
validator = agents["validator"]
bi = agents["bi"]

# ----------------------------
# User Input
# ----------------------------
user_query = st.text_input(
    label="",
    placeholder="e.g. give me FTE by segment for June 2025"
)

if not user_query:
    st.stop()

st.markdown("⏳ **Thinking...**")

# ----------------------------
# STEP 1: ARCHITECT
# ----------------------------
raw_response = architect.run(user_query)

# ---- FIX: Handle dict vs JSON string ----
if isinstance(raw_response, dict):
    architecture = raw_response

elif isinstance(raw_response, str):
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    try:
        architecture = json.loads(cleaned)
    except Exception:
        st.error("❌ Architect returned invalid JSON")
        st.code(cleaned)
        st.stop()

else:
    st.error("❌ Architect returned unsupported response type")
    st.write(type(raw_response))
    st.stop()

# Debug (safe to remove later)
st.code(architecture, language="json")

# ----------------------------
# STEP 2: BASIC ARCHITECT VALIDATION
# ----------------------------
if not isinstance(architecture, dict):
    st.error("❌ Architecture is not a dictionary")
    st.stop()

if architecture.get("kpi_id") is None:
    st.warning("❌ Could not determine KPI.")
    st.stop()

# ----------------------------
# STEP 3: VALIDATOR
# ----------------------------
validation = validator.validate(architecture)

if not validation.get("valid", False):
    st.error("❌ Validation failed")
    st.write(validation)
    st.stop()

# ----------------------------
# STEP 4: ANALYST
# ----------------------------
analysis_plan = analyst.build_analysis_plan(architecture)

if not analysis_plan:
    st.error("❌ Analyst could not build analysis plan")
    st.stop()

# ----------------------------
# STEP 5: BI EXECUTION
# ----------------------------
result = bi.execute(analysis_plan)

# ----------------------------
# STEP 6: DISPLAY OUTPUT
# ----------------------------
st.success("✅ Analysis complete")

if isinstance(result, dict):
    if "table" in result:
        st.dataframe(result["table"])

    if "summary" in result:
        st.markdown("### 📊 Summary")
        st.write(result["summary"])
else:
    st.write(result)
