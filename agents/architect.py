import pandas as pd
import json
from langchain_openai import ChatOpenAI

class ArchitectAgent:
    def __init__(self, kpi_directory_path, prompt_path, model):
        self.kpi_df = pd.read_excel(kpi_directory_path)
        self.model = ChatOpenAI(model=model, temperature=0)

        with open(prompt_path, "r") as f:
            self.prompt_template = f.read()

    def run(self, user_query: str):
        # Explicitly include KPI_Synonyms
        kpi_context_df = self.kpi_df[
            [
                "KPI_ID",
                "KPI_Name",
                "KPI_Synonyms",
                "Business_Question",
                "KPI_Category",
            ]
        ]

        kpi_context = kpi_context_df.to_csv(index=False)

        # Build prompt manually (NO PromptTemplate)
        final_prompt = self.prompt_template.replace(
            "{{KPI_DIRECTORY}}", kpi_context
        ).replace(
            "{{USER_QUESTION}}", user_query
        )

        response = self.model.invoke(final_prompt)

        try:
            return json.loads(response.content)
        except Exception:
            return {
                "kpi_id": None,
                "filters": {},
                "comparison": None
            }
