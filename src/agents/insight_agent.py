# src/agents/insight_agent.py

from typing import Dict, List, Any
import math


class InsightAgent:
    """
    Generates high-level hypotheses for a campaign based on its time-series data.
    This class focuses on *what* changed (ROAS/CTR/impressions), while the
    EvaluatorAgent will attach detailed numeric evidence, impact, and confidence.
    """

    def __init__(
        self,
        roas_drop_pct: float = 20.0,  # % drop threshold to flag ROAS issues
        ctr_drop_pct: float = 15.0,   # % drop threshold to flag CTR issues
        min_points: int = 4,          # minimum data points required
    ):
        self.roas_drop_pct = roas_drop_pct
        self.ctr_drop_pct = ctr_drop_pct
        self.min_points = min_points

    @staticmethod
    def _safe_mean(values: List[float]) -> float:
        clean = [v for v in values if v is not None and not math.isnan(v)]
        if not clean:
            return 0.0
        return sum(clean) / len(clean)

    @staticmethod
    def _pct_change(old: float, new: float) -> float:
        if old == 0:
            if new > 0:
                return float("inf")
            return 0.0
        return (new - old) / abs(old) * 100.0

    def _split_pre_post(self, timeseries: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        n = len(timeseries)
        if n < 2:
            return {"pre": timeseries, "post": []}
        half = n // 2
        return {
            "pre": timeseries[:half],
            "post": timeseries[half:],
        }

    def generate_hypotheses(self, campaign_name: str, timeseries: List[Dict[str, Any]]) -> List[Dict]:
        """
        Generate high-level hypotheses for a campaign based on time-series patterns.
        Evidence, confidence and impact will be attached later by EvaluatorAgent.
        """
        hypos: List[Dict] = []

        # Not enough data to say anything meaningful
        if len(timeseries) < self.min_points:
            hypos.append(
                {
                    "id": "h_insufficient_data",
                    "hypothesis": "Insufficient data to draw strong conclusions",
                    "segment": "overall",
                }
            )
            return hypos

        split = self._split_pre_post(timeseries)
        pre = split["pre"]
        post = split["post"]

        # Compute baseline vs current averages
        pre_roas = self._safe_mean([d.get("roas", 0.0) for d in pre])
        post_roas = self._safe_mean([d.get("roas", 0.0) for d in post])
        pre_ctr = self._safe_mean([d.get("ctr", 0.0) for d in pre])
        post_ctr = self._safe_mean([d.get("ctr", 0.0) for d in post])
        pre_imps = self._safe_mean([d.get("impressions", 0.0) for d in pre])
        post_imps = self._safe_mean([d.get("impressions", 0.0) for d in post])

        roas_delta_pct = self._pct_change(pre_roas, post_roas)
        ctr_delta_pct = self._pct_change(pre_ctr, post_ctr)
        imps_delta_pct = self._pct_change(pre_imps, post_imps)

        # Hypothesis: ROAS drop
        if roas_delta_pct < -self.roas_drop_pct:
            hypos.append(
                {
                    "id": "h_roas_drop",
                    "hypothesis": "ROAS decreased significantly vs baseline",
                    "segment": "overall",
                }
            )

        # Hypothesis: CTR drop
        if ctr_delta_pct < -self.ctr_drop_pct:
            hypos.append(
                {
                    "id": "h_ctr_drop",
                    "hypothesis": "CTR decreased significantly vs baseline",
                    "segment": "overall",
                }
            )

        # Hypothesis: creative fatigue (impressions up, CTR down)
        if imps_delta_pct > 0 and ctr_delta_pct < 0 and abs(ctr_delta_pct) >= self.ctr_drop_pct:
            hypos.append(
                {
                    "id": "h_fatigue",
                    "hypothesis": "Possible creative fatigue (impressions up, CTR down)",
                    "segment": "overall",
                }
            )

        # If nothing major detected, add a neutral hypothesis
        if not hypos:
            hypos.append(
                {
                    "id": "h_none",
                    "hypothesis": "No major performance shift detected vs baseline",
                    "segment": "overall",
                }
            )

        return hypos
