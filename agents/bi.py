import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

class BIAgent:
    def __init__(self, kpi_directory_path):
        self.kpi_df = pd.read_excel(kpi_directory_path)

    def format_val(self, val, unit):
        if pd.isna(val): return "N/A"
        if unit == "%": return f"{int(round(val))}%"
        if "USD" in str(unit): return f"${val/1000:,.0f}K"
        return f"{val:,.0f}"

    def render(self, kpi_id, df):
        # Get KPI Metadata
        meta = self.kpi_df[self.kpi_df["KPI_ID"] == kpi_id].iloc[0]
        
        st.subheader(f"📊 {meta['KPI_Name']} Analysis")
        
        # Summary Metric
        total_avg = df["value"].mean()
        st.metric("Average across Segments", self.format_val(total_avg, meta["Unit"]))

        # Visuals
        col1, col2 = st.columns([2, 1])
        with col1:
            fig, ax = plt.subplots()
            ax.bar(df.iloc[:, 0].astype(str), df["value"], color="#00529B")
            plt.xticks(rotation=45, ha='right')
            st.pyplot(fig)
        
        with col2:
            display_df = df.copy()
            display_df["value"] = display_df["value"].apply(lambda x: self.format_val(x, meta["Unit"]))
            st.dataframe(display_df, use_container_width=True)
