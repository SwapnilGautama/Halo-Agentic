import pandas as pd
import duckdb
import os
from config import PNL_DATA_PATH, UT_DATA_PATH

class AnalystAgent:
    def __init__(self):
        self.conn = duckdb.connect(database=':memory:')
        self.last_sql = "No SQL generated yet"
        self._load_data()

    def _load_data(self):
        try:
            if os.path.exists(PNL_DATA_PATH):
                df_pnl = pd.read_excel(PNL_DATA_PATH)
                df_pnl['Month'] = pd.to_datetime(df_pnl['Month'], errors='coerce')
                self.conn.register("pnl_data", df_pnl)
            
            if os.path.exists(UT_DATA_PATH):
                df_ut = pd.read_excel(UT_DATA_PATH)
                df_ut['Date'] = pd.to_datetime(df_ut['Date'], errors='coerce')
                self.conn.register("ut_data", df_ut)
        except Exception as e:
            print(f"Data loading failed: {e}")

    def run(self, architecture: dict):
        # SECURITY CHECK: Re-register tables if they were dropped from memory
        try:
            self.conn.execute("SELECT 1 FROM pnl_data LIMIT 1")
        except:
            self._load_data()

        kpi_id = architecture.get("kpi_id")
        filters = architecture.get("filters", {})
        month_val = filters.get("Month")
        date_clause = f"Month = '{month_val}'" if month_val else "1=1"
        dim = "FinalCustomerName" if "Customer" in str(architecture) or "Account" in str(architecture) else "Segment"

        # KPI Routing
        if kpi_id == "KPI_006":  # Margin % (Bucket Logic)
            sql = f"""
            WITH Rev AS (
                SELECT "{dim}", SUM("Amount in USD") as r FROM pnl_data 
                WHERE Type='Revenue' AND Group1 IN ('ONSITE','OFFSHORE','INDIRECT REVENUE') AND {date_clause} GROUP BY 1
            ),
            Cost AS (
                SELECT "{dim}", SUM("Amount in USD") as c FROM pnl_data 
                WHERE Type='Cost' AND {date_clause} GROUP BY 1
            )
            SELECT Rev."{dim}", Rev.r as Revenue, COALESCE(Cost.c, 0) as Cost,
            ((Rev.r - COALESCE(Cost.c, 0))/NULLIF(Rev.r, 0))*100 as value
            FROM Rev LEFT JOIN Cost ON Rev."{dim}" = Cost."{dim}"
            """
        elif kpi_id == "KPI_016": # FTE
            sql = f"SELECT \"{dim}\", COUNT(DISTINCT PSNo) as value FROM ut_data WHERE {date_clause.replace('Month','Date')} GROUP BY 1"
        else:
            sql = f"SELECT \"{dim}\", SUM(\"Amount in USD\") as value FROM pnl_data WHERE {date_clause} GROUP BY 1"

        self.last_sql = sql
        try:
            return self.conn.execute(sql).df()
        except Exception as e:
            # Return an error dataframe instead of crashing
            return pd.DataFrame({"Error": [str(e)]})
