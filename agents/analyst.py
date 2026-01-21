import pandas as pd
import duckdb
import os

class AnalystAgent:
    def __init__(self):
        self.conn = duckdb.connect(database=':memory:')
        self._load_initial_data()

    def _load_initial_data(self):
        # Ensure data is loaded into the Analyst's memory
        if os.path.exists("pnl_data.xlsx"):
            df_pnl = pd.read_excel("pnl_data.xlsx")
            df_pnl['Month'] = pd.to_datetime(df_pnl['Month'], errors='coerce')
            self.conn.register("pnl_data", df_pnl)
        if os.path.exists("ut_data.xlsx"):
            df_ut = pd.read_excel("ut_data.xlsx")
            df_ut['Date'] = pd.to_datetime(df_ut['Date'], errors='coerce')
            self.conn.register("ut_data", df_ut)

    def run(self, architecture: dict):
        kpi_id = architecture.get("kpi_id")
        filters = architecture.get("filters", {})
        
        # Build Date Filter
        date_val = filters.get("Month", "1=1")
        date_clause = f"Month = '{date_val}'" if date_val != "1=1" else "1=1"
        
        # Determine Dimension (Default to Segment)
        dim = "Segment" if "Segment" in str(architecture) else "FinalCustomerName"

        # KPI Logic Routing
        if kpi_id == "KPI_006":  # Contribution Margin %
            sql = f"""
            WITH Rev AS (
                SELECT "{dim}", SUM("Amount in USD") as r FROM pnl_data 
                WHERE Type='Revenue' AND Group1 IN ('ONSITE','OFFSHORE','INDIRECT REVENUE') AND {date_clause} GROUP BY 1
            ),
            Cost AS (
                SELECT "{dim}", SUM("Amount in USD") as c FROM pnl_data 
                WHERE Type='Cost' AND {date_clause} GROUP BY 1
            )
            SELECT Rev."{dim}", Rev.r as Revenue, Cost.c as Cost, 
            ((Rev.r - COALESCE(Cost.c, 0))/NULLIF(Rev.r, 0))*100 as value
            FROM Rev LEFT JOIN Cost ON Rev."{dim}" = Cost."{dim}"
            """
        elif kpi_id == "KPI_001": # Total Revenue
            sql = f"SELECT {dim}, SUM(\"Amount in USD\") as value FROM pnl_data WHERE Type='Revenue' AND {date_clause} GROUP BY 1"
        
        elif kpi_id == "KPI_009": # Utilization %
            sql = f"SELECT {dim}, (SUM(TotalBillableHours)/NULLIF(SUM(NetAvailableHours),0))*100 as value FROM ut_data WHERE {date_clause.replace('Month','Date')} GROUP BY 1"
        
        else:
            # Generic fallback for other KPIs
            sql = f"SELECT {dim}, SUM(\"Amount in USD\") as value FROM pnl_data WHERE {date_clause} GROUP BY 1"

        return self.conn.execute(sql).df()
