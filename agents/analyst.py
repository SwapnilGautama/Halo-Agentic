import pandas as pd
import duckdb
import os
from config import PNL_DATA_PATH, UT_DATA_PATH

class AnalystAgent:
    def __init__(self):
        self.conn = duckdb.connect(database=':memory:')
        self._load_data()

    def _load_data(self):
        # Load from paths defined in config.py
        if os.path.exists(PNL_DATA_PATH):
            df_pnl = pd.read_excel(PNL_DATA_PATH)
            df_pnl['Month'] = pd.to_datetime(df_pnl['Month'], errors='coerce')
            self.conn.register("pnl_data", df_pnl)
        
        if os.path.exists(UT_DATA_PATH):
            df_ut = pd.read_excel(UT_DATA_PATH)
            df_ut['Date'] = pd.to_datetime(df_ut['Date'], errors='coerce')
            self.conn.register("ut_data", df_ut)

    def run(self, architecture: dict):
        kpi_id = architecture.get("kpi_id")
        filters = architecture.get("filters", {})
        
        # 1. Handle Filters (Month, etc.)
        month_val = filters.get("Month")
        date_clause = f"Month = '{month_val}'" if month_val else "1=1"
        
        # 2. Handle Dimension (Segment or Account)
        # We check the query context or default to Segment
        dim = "FinalCustomerName" if any(x in str(filters).lower() for x in ["account", "customer"]) else "Segment"

        # 3. KPI Logic Routing (The "Surgical" Fix)
        if kpi_id == "KPI_006":  # Contribution Margin %
            sql = f"""
            WITH Rev AS (
                SELECT "{dim}", SUM("Amount in USD") as r 
                FROM pnl_data 
                WHERE Type='Revenue' AND Group1 IN ('ONSITE','OFFSHORE','INDIRECT REVENUE') AND {date_clause} 
                GROUP BY 1
            ),
            Cost AS (
                SELECT "{dim}", SUM("Amount in USD") as c 
                FROM pnl_data 
                WHERE Type='Cost' AND {date_clause} 
                GROUP BY 1
            )
            SELECT 
                Rev."{dim}", 
                Rev.r as Revenue, 
                COALESCE(Cost.c, 0) as Cost, 
                ((Rev.r - COALESCE(Cost.c, 0)) / NULLIF(Rev.r, 0)) * 100 as value
            FROM Rev 
            LEFT JOIN Cost ON Rev."{dim}" = Cost."{dim}"
            """
        elif kpi_id == "KPI_016": # FTE
            sql = f"""
            SELECT "{dim}", COUNT(DISTINCT PSNo) as value 
            FROM ut_data 
            WHERE {date_clause.replace('Month', 'Date')} 
            GROUP BY 1
            """
        else:
            # Standard Sum Logic for Revenue/Cost
            sql = f"""
            SELECT "{dim}", SUM("Amount in USD") as value 
            FROM pnl_data 
            WHERE {date_clause} 
            GROUP BY 1
            """

        try:
            return self.conn.execute(sql).df()
        except Exception as e:
            return pd.DataFrame({"Error": [str(e)], "SQL": [sql]})
