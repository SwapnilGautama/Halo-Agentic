import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

class BIAgent:
    def __init__(self, kpi_directory_path="metadata/kpi_directory.xlsx"):
        self.kpi_df = pd.read_excel(kpi_directory_path)

    def get_kpi_meta(self, kpi_id):
        row = self.kpi_df[self.kpi_df["KPI_ID"] == kpi_id]
        if row.empty:
            raise ValueError("KPI not found for BI Agent")
        return row.iloc[0]

    def format_value(self, val, unit):
        if pd.isna(val):
            return "NA"
        if unit == "%":
            return f"{val:.1f}%"
        if "USD" in unit:
            return f"${val:,.0f}"
        return f"{val:,.2f}"

    def render_table(self, df, kpi_meta):
        st.subheader("📋 Results Table")
        st.dataframe(df, use_container_width=True)

    def render_chart(self, df, kpi_meta, comparison):
        chart_type = kpi_meta["Preferred_Chart"]

        dim_col = df.columns[0]

        if comparison:
            y_col = "current_value"
        else:
            y_col = "value"

        fig, ax = plt.subplots(figsize=(10, 4))

        if chart_type == "Bar":
            ax.bar(df[dim_col].astype(str), df[y_col])
        else:
            ax.plot(df[dim_col].astype(str), df[y_col], marker="o")

        ax.set_title(kpi_meta["KPI_Name"])
        ax.set_ylabel(kpi_meta["Unit"])
        ax.set_xlabel(dim_col)
        plt.xticks(rotation=45)

        st.pyplot(fig)

    def generate_insights(self, df, kpi_meta, comparison):
        unit = kpi_meta["Unit"]
        good = kpi_meta["Good_Threshold"]
        risk = kpi_meta["Risk_Threshold"]

        insights = []

        if comparison:
            avg_change = df["pct_change"].mean()
            insights.append(
                f"Average change: {avg_change:.1f}% compared to previous period."
            )
        else:
            avg_val = df["value"].mean()
            insights.append(
                f"Average {kpi_meta['KPI_Name']}: {self.format_value(avg_val, unit)}"
            )

        if not pd.isna(good) and not comparison:
            breached = df[df["value"] < good]
            if not breached.empty:
                insights.append(
                    f"⚠️ {len(breached)} segments below healthy threshold ({good}{unit})"
                )

        return insights

    def render(self, kpi_id, df, comparison=None):
        kpi_meta = self.get_kpi_meta(kpi_id)

        st.markdown(f"## 📊 {kpi_meta['KPI_Name']}")

        self.render_chart(df, kpi_meta, comparison)
        self.render_table(df, kpi_meta)

        st.markdown("### 💡 Insights")
        for insight in self.generate_insights(df, kpi_meta, comparison):
            st.info(insight)
