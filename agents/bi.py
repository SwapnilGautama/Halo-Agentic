import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

class BIAgent:
    def __init__(self, kpi_directory_path="metadata/kpi_directory.xlsx"):
        """
        Initializes the BI Agent by loading the KPI Directory for metadata lookup.
        """
        try:
            self.kpi_df = pd.read_excel(kpi_directory_path)
        except Exception as e:
            st.error(f"Error loading KPI Directory in BIAgent: {e}")
            self.kpi_df = pd.DataFrame()

    def get_kpi_meta(self, kpi_id):
        """
        Retrieves metadata for a specific KPI ID.
        """
        row = self.kpi_df[self.kpi_df["KPI_ID"] == kpi_id]
        if row.empty:
            raise ValueError(f"KPI ID {kpi_id} not found in directory.")
        return row.iloc[0]

    def format_value(self, val, unit):
        """
        Business Logic for Formatting:
        - Percentages: Rounded to 0 decimals (e.g., 75%)
        - USD: Divided by 1000 and suffixed with 'K' (e.g., $1,250K)
        - Counts: Comma separated integers (e.g., 1,024)
        """
        try:
            if val is None or pd.isna(val):
                return "NA"
            
            val = float(val)
            
            if unit == "%":
                return f"{int(round(val))}%"
            
            if "USD" in str(unit):
                k_val = val / 1000
                return f"${k_val:,.0f}K"
            
            return f"{val:,.0f}"
        except:
            return str(val)

    def render_kpi_card(self, df, kpi_meta):
        """
        Renders a large metric card showing the average value for the period.
        """
        avg_val = df["value"].mean()
        formatted_val = self.format_value(avg_val, kpi_meta["Unit"])
        
        st.metric(
            label=f"Avg {kpi_meta['KPI_Name']}", 
            value=formatted_val
        )

    def render_primary_chart(self, df, kpi_meta):
        """
        Renders a bar chart using the first column as dimension and 'value' as the metric.
        """
        fig, ax = plt.subplots(figsize=(10, 4))
        
        # Determine labels and values
        labels = df.iloc[:, 0].astype(str)
        values = df["value"]
        
        ax.bar(labels, values, color='#00529B')
        
        # Styling
        ax.set_ylabel(kpi_meta["Unit"])
        plt.xticks(rotation=45, ha='right')
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        st.pyplot(fig)

    def render(self, kpi_id, df, comparison=None):
        """
        Main entry point for the UI.
        Creates a structured layout with a Metric, Chart, and Table.
        """
        try:
            kpi_meta = self.get_kpi_meta(kpi_id)
            
            st.markdown(f"## 📊 {kpi_meta['KPI_Name']} Analysis")
            
            # 1. Top Level Metric
            self.render_kpi_card(df, kpi_meta)
            
            st.divider()
            
            # 2. Visuals and Data Grid
            col1, col2 = st.columns([2, 1])
            
            with col1:
                st.markdown("**Performance Trend**")
                self.render_primary_chart(df, kpi_meta)
            
            with col2:
                st.markdown("**Data Detail**")
                # Format the dataframe for display
                display_df = df.copy()
                # If Margin logic was used, we show Revenue and Cost columns if they exist
                cols_to_show = [c for c in display_df.columns if c != 'value'] + ['value']
                
                # Apply business formatting to the 'value' column
                display_df["value"] = display_df["value"].apply(
                    lambda x: self.format_value(x, kpi_meta["Unit"])
                )
                
                # Apply formatting to Revenue/Cost columns if they were part of the result
                for col in ["Revenue", "Cost"]:
                    if col in display_df.columns:
                        display_df[col] = display_df[col].apply(
                            lambda x: self.format_value(x, "USD")
                        )
                
                st.dataframe(display_df, use_container_width=True, hide_index=True)
                
        except Exception as e:
            st.error(f"BI Rendering Error: {e}")
