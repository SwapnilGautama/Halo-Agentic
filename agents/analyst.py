import pandas as pd

# -----------------------------
# Metadata Loaders
# -----------------------------
def load_kpi_directory(path="metadata/kpi_directory.xlsx"):
    df = pd.read_excel(path)
    return df


def load_field_directory(path="metadata/field_directory.xlsx"):
    df = pd.read_excel(path)
    return df


# -----------------------------
# Core Analyst Agent
# -----------------------------
class AnalystAgent:
    def __init__(self):
        self.kpi_df = load_kpi_directory()
        self.field_df = load_field_directory()

    # -------------------------
    # KPI Resolver
    # -------------------------
    def get_kpi(self, kpi_id: str):
        row = self.kpi_df[self.kpi_df["KPI_ID"] == kpi_id]
        if row.empty:
            raise ValueError(f"KPI_ID {kpi_id} not found in KPI directory")
        return row.iloc[0]

    # -------------------------
    # Filter Builder
    # -------------------------
    def build_filters(self, filters: dict):
        clauses = []
        for col, val in filters.items():
            if isinstance(val, list):
                values = ",".join([f"'{v}'" for v in val])
                clauses.append(f"{col} IN ({values})")
            else:
                clauses.append(f"{col} = '{val}'")
        return " AND ".join(clauses)

    # -------------------------
    # Single Table SQL
    # -------------------------
    def build_single_table_sql(self, kpi, filters):
        where_clause = self.build_filters(filters)

        numerator = kpi["Numerator_Formula"]
        denominator = kpi["Denominator_Formula"]

        select_expr = (
            numerator
            if pd.isna(denominator)
            else f"({numerator}) / NULLIF({denominator},0)"
        )

        sql = f"""
        SELECT
            {kpi['Default_Dimension']},
            {select_expr} AS value
        FROM {kpi['Primary_Table']}
        WHERE {where_clause}
        GROUP BY {kpi['Default_Dimension']}
        """
        return sql.strip()

    # -------------------------
    # Multi Table SQL (Safe Join)
    # -------------------------
    def build_multi_table_sql(self, kpi, filters):
        join_keys = [k.strip() for k in kpi["Join_Keys"].split("+")]
        time_key = kpi["Join_Time_Alignment"]

        base_filters = self.build_filters(filters)

        # Pre-aggregate PRIMARY table
        primary_cte = f"""
        primary_data AS (
            SELECT
                {', '.join(join_keys)},
                {time_key},
                {kpi['Numerator_Formula']} AS numerator
            FROM {kpi['Primary_Table']}
            WHERE {base_filters}
            GROUP BY {', '.join(join_keys)}, {time_key}
        )
        """

        # Pre-aggregate SECONDARY table
        secondary_cte = f"""
        secondary_data AS (
            SELECT
                {', '.join(join_keys)},
                {time_key},
                {kpi['Denominator_Formula']} AS denominator
            FROM {kpi['Secondary_Table']}
            WHERE {base_filters}
            GROUP BY {', '.join(join_keys)}, {time_key}
        )
        """

        join_conditions = " AND ".join(
            [f"p.{k}=s.{k}" for k in join_keys]
            + [f"p.{time_key}=s.{time_key}"]
        )

        sql = f"""
        WITH
        {primary_cte},
        {secondary_cte}
        SELECT
            p.{join_keys[0]},
            (p.numerator / NULLIF(s.denominator,0)) AS value
        FROM primary_data p
        JOIN secondary_data s
          ON {join_conditions}
        """
        return sql.strip()

    # -------------------------
    # Public API
    # -------------------------
    def generate_sql(self, kpi_id: str, filters: dict):
        kpi = self.get_kpi(kpi_id)

        if kpi["Uses_Multiple_Tables"] == "Yes":
            return self.build_multi_table_sql(kpi, filters)
        else:
            return self.build_single_table_sql(kpi, filters)
