import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

class BIAgent:
    def __init__(self, kpi_directory_path="metadata/kpi_directory.xlsx"):
        self.kpi_df = pd.read_excel(kpi_directory_path)

    def get_kpi_meta(self, kpi_id):
        row = self.kpi_df[self.kpi_df["KPI_ID"] == kpi_id]
        return row.iloc[0] if not row.empty else None

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
        meta = self.get_kpi_meta(kpi_id)
        if meta is None or df.empty:
            st.warning("No displayable data found.")
            return

        st.markdown(f"### 📈 {meta['KPI_Name']} Analysis")
        
        # Metric Card
        avg_val = df["value"].mean()
        st.metric(label=f"Avg {meta['KPI_Name']}", value=self.format_value(avg_val, meta["Unit"]))

        col1, col2 = st.columns([2, 1])
        with col1:
            fig, ax = plt.subplots(figsize=(10, 5))
            ax.bar(df.iloc[:, 0].astype(str), df["value"], color="#00529B")
            plt.xticks(rotation=45, ha='right')
            st.pyplot(fig)
        
        with col2:
            display_df = df.copy()
            display_df["value"] = display_df["value"].apply(lambda x: self.format_value(x, meta["Unit"]))
            st.dataframe(display_df, use_container_width=True)
