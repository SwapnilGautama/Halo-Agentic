import pandas as pd
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
import json

class ArchitectAgent:
    def __init__(self, kpi_directory_path, prompt_path, model):
        self.kpi_df = pd.read_excel(kpi_directory_path)
        self.model = ChatOpenAI(model=model, temperature=0)

        with open(prompt_path, "r") as f:
            self.prompt_template = f.read()

    def run(self, user_query: str):
        # ✅ IMPORTANT: Explicitly include KPI_Synonyms
        kpi_context_df = self.kpi_df[[
            "KPI_ID",
            "KPI_Name",
            "KPI_Synonyms",
            "Business_Question",
            "KPI_Category"
        ]]

        kpi_context = kpi_context_df.to_csv(index=False)

        prompt = PromptTemplate(
            input_variables=["KPI_DIRECTORY", "USER_QUESTION"],
            template=self.prompt_template
        )

        final_prompt = prompt.format(
            KPI_DIRECTORY=kpi_context,
            USER_QUESTION=user_query
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
