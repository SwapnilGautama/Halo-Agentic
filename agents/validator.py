import pandas as pd


class ValidationAgent:
    def __init__(self, kpi_directory_path="metadata/kpi_directory.xlsx"):
        self.kpi_df = pd.read_excel(kpi_directory_path)

    def validate(self, kpi_id, df, comparison=None):
        if kpi_id not in self.kpi_df["KPI_ID"].values:
            return [], [f"Invalid KPI_ID: {kpi_id}"]

        if df.empty:
            return [], ["Result dataframe is empty"]

        return [], []
