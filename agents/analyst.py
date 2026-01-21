import pandas as pd


class AnalystAgent:
    def __init__(self):
        pass

    def run(self, architecture: dict):
        kpi_id = architecture["kpi_id"]

        # Stub logic for now (no silent failure)
        return pd.DataFrame({
            "kpi_id": [kpi_id],
            "value": [1]
        })
