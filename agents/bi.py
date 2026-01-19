import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

class BIAgent:
    def __init__(self, kpi_directory_path="metadata/kpi_directory.xlsx"):
        self.kpi_df = pd.read_excel(kpi_directory_path)

    # -------------------------
    # Metadata
    # -------------------------
    def get_kpi_meta(self, kpi_id):
        row = self.kpi_df[self.kpi_df["KPI_ID"] == kpi_id]
        if row.empty:
            raise ValueError("KPI not found")
        return row.iloc[0]

    # -------------------------
    # Formatting helpers
    # -------------------------
    def format_value(self, val, unit):
        if pd.isna(val):
            return "NA"
        if unit == "%":
            return f"{val:.1f}%"
        if "USD" in unit:
            return f"${val:,.0f}"
        return f"{val:,.2f}"

    def get_status_color(self, val, good, risk):
        if pd.isna(val) or pd.isna(good) or pd.isna(risk):
            return "gray"
        if val >= good:
            return "green"
        if val < risk:
            return "red"
        return "orange"

    # -------------------------
    # KPI CARD
    # -------------------------
    def render_kpi_card(self, df, kpi_meta, comparison):
        unit = kpi_meta["Unit"]
        good = kpi_meta["Good_Threshold"]
        risk = kpi_meta["Risk_Threshold"]

        if comparison:
            current = df["current_value"].mean()
            delta = df["pct_change"].mean()
            status = self.get_status_color(current, good, risk)

            st.metric(
                label=kpi_meta["KPI_Name"],
                value=self.format_value(current, unit),
                delta=f"{delta:.1f}%"
            )
        else:
            value = df["value"].mean()
            status = self.get_status_color(value, good, risk)

            st.metric(
                label=kpi_meta["KPI_Name"],
                value=self.format_value(value, unit)
            )

    # -------------------------
    # Charts
    # -------------------------
    def render_primary_chart(self, df, kpi_meta, comparison):
        dim = df.columns[0]
        y_col = "current_value" if comparison else "value"

        fig, ax = plt.subplots(figsize=(10, 4))

        if kpi_meta["Preferred_Chart"] == "Bar":
            ax.bar(df[dim].astype(str), df[y_col])
        else:
            ax.plot(df[dim].astype(str), df[y_col], marker="o")

        ax.set_title(kpi_meta["KPI_Name"])
        ax.set_ylabel(kpi_meta["Unit"])
        plt.xticks(rotation=45)

        st.pyplot(fig)

    def render_secondary_chart(self, df, comparison):
        # Simple ranking chart
        dim = df.columns[0]
        y_col = "current_value" if comparison else "value"

        ranked = df.sort_values(y_col, ascending=False).head(10)

        fig, ax = plt.subplots(figsize=(10, 4))
        ax.barh(ranked[dim].astype(str), ranked[y_col])
        ax.set_title("Top Contributors")

        st.pyplot(fig)

    # -------------------------
    # Smart Table
    # -------------------------
    def render_table(self, df, comparison):
        if comparison:
            df = df.sort_values("pct_change")
        else:
            df = df.sort_values("value", ascending=False)

        st.dataframe(df, use_container_width=True)

    # -------------------------
    # Insights
    # -------------------------
    def render_insights(self, df, kpi_meta, comparison):
        st.markdown("### 💡 Key Insights")

        if comparison:
            worst = df.sort_values("pct_change").iloc[0]
            st.info(
                f"{worst[0]} shows the largest decline ({worst['pct_change']:.1f}%)."
            )
        else:
            best = df.sort_values("value", ascending=False).iloc[0]
            st.info(
                f"{best[0]} leads with {self.format_value(best['value'], kpi_meta['Unit'])}."
            )

    # -------------------------
    # MAIN ENTRY
    # -------------------------
    def render(self, kpi_id, df, comparison=None):
        kpi_meta = self.get_kpi_meta(kpi_id)

        st.markdown(f"## 📊 {kpi_meta['KPI_Name']}")

        # KPI CARD
        self.render_kpi_card(df, kpi_meta, comparison)

        col1, col2 = st.columns(2)

        with col1:
            self.render_primary_chart(df, kpi_meta, comparison)

        with col2:
            self.render_secondary_chart(df, comparison)

        self.render_table(df, comparison)
        self.render_insights(df, kpi_meta, comparison)
