import pandas as pd
import json
from langchain_openai import ChatOpenAI


class ArchitectAgent:
    def __init__(self, kpi_directory_path, prompt_path, model):
        self.kpi_df = pd.read_excel(kpi_directory_path)

        self.kpi_df["KPI_Synonyms"] = (
            self.kpi_df["KPI_Synonyms"]
            .fillna("")
            .str.lower()
        )

        self.model = ChatOpenAI(
            model=model,
            temperature=0
        )

        with open(prompt_path, "r") as f:
            self.prompt_template = f.read()

    # -------------------------------------------------
    # 🔒 HARD KPI RESOLVER (NO LLM GUESSING)
    # -------------------------------------------------
    def resolve_kpi_id(self, user_query: str):
        q = user_query.lower()

        for _, row in self.kpi_df.iterrows():
            synonyms = row["KPI_Synonyms"].split("|")
            name = row["KPI_Name"].lower()

            if name in q:
                return row["KPI_ID"]

            for s in synonyms:
                if s.strip() and s.strip() in q:
                    return row["KPI_ID"]

        return None

    # -------------------------------------------------
    # MAIN ENTRY
    # -------------------------------------------------
    def run(self, user_query: str):
        kpi_id = self.resolve_kpi_id(user_query)

        if kpi_id is None:
            return {
                "kpi_id": None,
                "filters": {},
                "comparison": None
            }

        # Only filters go to LLM (NOT KPI selection)
        final_prompt = (
            self.prompt_template
            .replace("{{USER_QUESTION}}", user_query)
        )

        response = self.model.invoke(final_prompt)

        try:
            parsed = json.loads(response.content)
        except Exception:
            parsed = {}

        return {
            "kpi_id": kpi_id,
            "filters": parsed.get("filters", {}),
            "comparison": parsed.get("comparison")
        }
