import pandas as pd
import json
from langchain_openai import ChatOpenAI


class ArchitectAgent:
    def __init__(self, kpi_directory_path, prompt_path, model):
        # Load KPI Directory
        self.kpi_df = pd.read_excel(kpi_directory_path)

        # Initialize LLM
        self.model = ChatOpenAI(
            model=model,
            temperature=0
        )

        # Load prompt template
        with open(prompt_path, "r") as f:
            self.prompt_template = f.read()

    def run(self, user_query: str):
        """
        Converts user NL query into structured KPI intent
        """

        # -------------------------------------------------
        # Build KPI context (EXPLICITLY include synonyms)
        # -------------------------------------------------
        required_cols = [
            "KPI_ID",
            "KPI_Name",
            "KPI_Synonyms",
            "Business_Question",
            "KPI_Category"
        ]

        # Defensive check (prevents silent failures)
        missing = [c for c in required_cols if c not in self.kpi_df.columns]
        if missing:
            print("❌ KPI DIRECTORY MISSING COLUMNS:", missing)
            return {
                "kpi_id": None,
                "filters": {},
                "comparison": None
            }

        kpi_context_df = self.kpi_df[required_cols]

        # Convert to CSV so LLM sees clean table
        kpi_context = kpi_context_df.to_csv(index=False)

        # -------------------------------------------------
        # Build final prompt (MANUAL STRING REPLACEMENT)
        # -------------------------------------------------
        final_prompt = (
            self.prompt_template
            .replace("{{KPI_DIRECTORY}}", kpi_context)
            .replace("{{USER_QUESTION}}", user_query)
        )

        # -------------------------------------------------
        # 🔍 DEBUG LOGGING (TEMPORARY – VERY IMPORTANT)
        # -------------------------------------------------
        print("\n===== ARCHITECT AGENT DEBUG =====")
        print("USER QUERY:")
        print(user_query)
        print("\nKPI DIRECTORY COLUMNS:")
        print(kpi_context_df.columns.tolist())
        print("\nKPI DIRECTORY PREVIEW:")
        print(kpi_context_df.head(5))
        print("\nPROMPT SENT TO LLM (first 2000 chars):")
        print(final_prompt[:2000])
        print("===== END PROMPT =====\n")

        # -------------------------------------------------
        # Call LLM
        # -------------------------------------------------
        response = self.model.invoke(final_prompt)

        print("RAW LLM RESPONSE:")
        print(response.content)
        print("===== END ARCHITECT DEBUG =====\n")

        # -------------------------------------------------
        # Parse JSON safely
        # -------------------------------------------------
        try:
            return json.loads(response.content)
        except Exception as e:
            print("❌ JSON PARSE FAILED:", e)
            return {
                "kpi_id": None,
                "filters": {},
                "comparison": None
            }
