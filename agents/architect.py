import json
import pandas as pd
from langchain_openai import ChatOpenAI

class ArchitectAgent:
    def __init__(
        self,
        kpi_directory_path="metadata/kpi_directory.xlsx",
        prompt_path="prompts/architect_prompt.txt",
        model="gpt-4o"
    ):
        self.kpi_df = pd.read_excel(kpi_directory_path)
        self.prompt_template = open(prompt_path).read()
        self.llm = ChatOpenAI(model=model, temperature=0)

    def build_kpi_context(self):
        # Reduce noise: only send what the LLM needs
        cols = ["KPI_ID", "KPI_Name", "Business_Question", "KPI_Category"]
        return self.kpi_df[cols].to_string(index=False)

    def parse_response(self, response_text):
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            raise ValueError("Architect Agent returned invalid JSON")

    def run(self, user_query: str):
        prompt = self.prompt_template.replace(
            "{{KPI_DIRECTORY}}",
            self.build_kpi_context()
        )

        response = self.llm.invoke(
            f"{prompt}\n\nUser: {user_query}\nOutput:"
        )

        return self.parse_response(response.content)

