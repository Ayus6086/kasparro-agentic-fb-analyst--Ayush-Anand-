# src/agents/planner_agent.py

class PlannerAgent:
    def __init__(self, roas_drop_pct=20):
        self.roas_drop_pct = roas_drop_pct

    def decompose(self, task_text, data_summary, df=None):
        """
        Improved planner:
        Select campaigns with the MOST data points (at least 10 days).
        """
        if df is None:
            raise ValueError("PlannerAgent needs full dataframe")

        # Count rows per campaign
        counts = df['campaign_name'].value_counts()

        # Select campaigns with at least 10 rows
        eligible = counts[counts >= 10]

        if eligible.empty:
            # fallback: pick top 3 by count
            eligible = counts.head(3)

        # Take top 3 campaigns with most rows
        target_campaigns = eligible.head(3).index.tolist()

        plan = {
            "task": task_text,
            "target_campaigns": target_campaigns,
            "steps": [
                "get timeseries",
                "generate hypotheses",
                "evaluate hypotheses",
                "generate creatives if needed"
            ]
        }
        return plan
