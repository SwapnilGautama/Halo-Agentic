import pandas as pd

class ValidationAgent:
    def __init__(self, kpi_directory_path="metadata/kpi_directory.xlsx"):
        self.kpi_df = pd.read_excel(kpi_directory_path)

    def get_kpi_meta(self, kpi_id):
        row = self.kpi_df[self.kpi_df["KPI_ID"] == kpi_id]
        if row.empty:
            raise ValueError("KPI not found for validation")
        return row.iloc[0]

    def validate(self, kpi_id, df, comparison=None):
        kpi_meta = self.get_kpi_meta(kpi_id)
        unit = kpi_meta["Unit"]

        warnings = []
        errors = []

        value_col = "value" if not comparison else "current_value"

        if value_col not in df.columns:
            errors.append("Expected KPI value column not found")
            return warnings, errors

        series = df[value_col]

        # Null or infinite
        if series.isna().any():
            warnings.append("Null values detected in KPI output")

        if (series == float("inf")).any():
            errors.append("Infinite values detected")

        # Percentage rules
        if unit == "%":
            if (series > 100).any():
                warnings.append("Values exceed 100%")
            if (series < -100).any():
                warnings.append("Values below -100%")

        # Revenue / Cost
        if unit == "USD":
            if (series < 0).any():
                warnings.append("Negative financial values detected")

        # Utilization specific
        if "Utilization" in kpi_meta["KPI_Name"]:
            if (series > 100).any():
                warnings.append("Utilization above 100%")

        return warnings, errors
