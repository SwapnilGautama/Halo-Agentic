import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

class BIAgent:
    def __init__(self, kpi_directory_path="metadata/kpi_directory.xlsx"):
        self.kpi_df = pd.read_excel(kpi_directory_path)

    def get_kpi_meta(self, kpi_id):
        row = self.kpi_df[self.kpi_df["KPI_ID"] == kpi_id]
        if row.empty: return None
        return row.iloc[0]

    def format_value(self, val, unit):
        try:
            if pd.isna(val): return "NA"
            val = float(val)
            if unit == "%": return f"{int(round(val))}%"
            if "USD" in str(unit): return f"${val/1000:,.0f}K"
            return f"{val:,.0f}"
        except:
            return str(val)

    def render(self, kpi_id, df, comparison=None):
        if "Error" in df.columns:
            st.error(f"SQL Error: {df['Error'].iloc[0]}")
            return

        kpi_meta = self.get_kpi_meta(kpi_id)
        if kpi_meta is None:
            st.error(f"KPI {kpi_id} metadata missing.")
            return

        st.metric(label=f"Avg {kpi_meta['KPI_Name']}", value=self.format_value(df["value"].mean(), kpi_meta["Unit"]))
        
        c1, c2 = st.columns([2, 1])
        with c1:
            fig, ax = plt.subplots()
            ax.bar(df.iloc[:, 0].astype(str), df["value"], color='#00529B')
            plt.xticks(rotation=45)
            st.pyplot(fig)
        with c2:
            st.dataframe(df)
