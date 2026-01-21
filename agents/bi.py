import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

class BIAgent:
    def __init__(self, kpi_directory_path="metadata/kpi_directory.xlsx"):
        self.kpi_df = pd.read_excel(kpi_directory_path)

    def get_kpi_meta(self, kpi_id):
        row = self.kpi_df[self.kpi_df["KPI_ID"] == kpi_id]
        if row.empty: raise ValueError("KPI not found")
        return row.iloc[0]

    def format_value(self, val, unit):
        if pd.isna(val): return "NA"
        
        # 1. Percentages (Margin, Utilization): Round to 0 decimals
        if unit == "%":
            return f"{int(round(val))}%"
            
        # 2. Currency (USD): Round to thousands and add K
        if "USD" in str(unit):
            k_val = val / 1000
            return f"${k_val:,.0f}K"
            
        # 3. Counts (FTE): No decimals
        return f"{val:,.0f}"

    def render_kpi_card(self, df, kpi_meta):
        avg_val = df["value"].mean()
        formatted = self.format_value(avg_val, kpi_meta["Unit"])
        st.metric(label=f"Average {kpi_meta['KPI_Name']}", value=formatted)

    def render_chart(self, df, kpi_meta):
        fig, ax = plt.subplots(figsize=(10, 4))
        # Use simple bar for metrics
        ax.bar(df.iloc[:, 0].astype(str), df["value"], color='#00529B')
        plt.xticks(rotation=45)
        st.pyplot(fig)

    def render(self, kpi_id, df, comparison=None):
        kpi_meta = self.get_kpi_meta(kpi_id)
        st.subheader(f"📊 {kpi_meta['KPI_Name']} Analysis")
        
        self.render_kpi_card(df, kpi_meta)
        
        col1, col2 = st.columns([2, 1])
        with col1:
            self.render_chart(df, kpi_meta)
        with col2:
            # Show formatted table
            display_df = df.copy()
            display_df["value"] = display_df["value"].apply(lambda x: self.format_value(x, kpi_meta["Unit"]))
            st.dataframe(display_df, use_container_width=True)
