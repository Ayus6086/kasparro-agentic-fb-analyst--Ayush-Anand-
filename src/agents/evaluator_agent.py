# src/agents/evaluator_agent.py

from typing import Dict, List, Any
import math


class EvaluatorAgent:
    """
    Evaluates and enriches hypotheses with numeric evidence, impact and confidence.

    - Computes baseline vs current for key metrics (ROAS, CTR, impressions, spend)
    - Attaches evidence = {metric, pre, post, delta_abs, delta_pct}
    - Assigns impact = low/medium/high based on magnitude of change
    - Computes confidence in [0, 1] based on signal strength
    """

    def __init__(
        self,
        roas_drop_pct: float = 20.0,
        ctr_drop_pct: float = 15.0,
    ):
        self.roas_drop_pct = roas_drop_pct
        self.ctr_drop_pct = ctr_drop_pct

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

    def _compute_metric_stats(self, timeseries: List[Dict[str, Any]], key: str) -> Dict[str, float]:
        split = self._split_pre_post(timeseries)
        pre_vals = [d.get(key, 0.0) for d in split["pre"]]
        post_vals = [d.get(key, 0.0) for d in split["post"]]

        pre_mean = self._safe_mean(pre_vals)
        post_mean = self._safe_mean(post_vals)
        delta_abs = post_mean - pre_mean
        delta_pct = self._pct_change(pre_mean, post_mean)

        return {
            "pre": pre_mean,
            "post": post_mean,
            "delta_abs": delta_abs,
            "delta_pct": delta_pct,
        }

    def _impact_from_delta(self, delta_pct: float, inverse: bool = False) -> str:
        """
        Map % change to impact category.
        inverse=False  => large negative is bad (e.g., ROAS drop).
        inverse=True   => large positive is bad (e.g., cost increase).
        """
        val = delta_pct
        if inverse:
            val = -delta_pct

        if val <= -40:
            return "high"
        if val <= -20:
            return "medium"
        return "low"

    def _confidence_from_delta(self, delta_pct: float) -> float:
        """Map magnitude of % change to a 0–1 confidence score."""
        mag = abs(delta_pct)
        if mag >= 50:
            return 0.9
        if mag >= 30:
            return 0.75
        if mag >= 15:
            return 0.6
        if mag >= 5:
            return 0.45
        return 0.3

    def enrich_hypotheses(
        self,
        campaign_name: str,
        timeseries: List[Dict[str, Any]],
        hypotheses: List[Dict],
    ) -> List[Dict]:
        """
        Attach numeric evidence, impact and confidence to each hypothesis.

        Returns a new list with enriched hypotheses.
        """
        if not timeseries:
            # Nothing to evaluate, just return as-is
            return hypotheses

        # Compute stats for main metrics
        stats_roas = self._compute_metric_stats(timeseries, "roas")
        stats_ctr = self._compute_metric_stats(timeseries, "ctr")
        stats_imps = self._compute_metric_stats(timeseries, "impressions")
        stats_spend = self._compute_metric_stats(timeseries, "spend")

        enriched: List[Dict] = []

        for h in hypotheses:
            hid = h.get("id")

            # Default evidence if we don't recognize the hypothesis type
            evidence = {}
            impact = "low"
            confidence = 0.3

            if hid == "h_roas_drop":
                evidence = {
                    "metric": "roas",
                    **stats_roas,
                }
                impact = self._impact_from_delta(stats_roas["delta_pct"], inverse=False)
                confidence = self._confidence_from_delta(stats_roas["delta_pct"])

            elif hid == "h_ctr_drop":
                evidence = {
                    "metric": "ctr",
                    **stats_ctr,
                }
                impact = self._impact_from_delta(stats_ctr["delta_pct"], inverse=False)
                confidence = self._confidence_from_delta(stats_ctr["delta_pct"])

            elif hid == "h_fatigue":
                # Combine impressions up + CTR down
                evidence = {
                    "metric": "ctr_impressions_combo",
                    "ctr": stats_ctr,
                    "impressions": stats_imps,
                }
                # Fatigue: CTR drop & impressions increase => usually high impact
                impact = "high"
                # Use CTR drop magnitude for confidence
                confidence = self._confidence_from_delta(stats_ctr["delta_pct"])

            elif hid == "h_insufficient_data":
                evidence = {
                    "reason": "Not enough time-series points for robust comparison",
                    "points": len(timeseries),
                }
                impact = "low"
                confidence = 0.2

            elif hid == "h_none":
                evidence = {
                    "reason": "No major change detected across ROAS/CTR/impressions/spend",
                    "roas": stats_roas,
                    "ctr": stats_ctr,
                    "impressions": stats_imps,
                    "spend": stats_spend,
                }
                impact = "low"
                confidence = 0.5

            # Build enriched hypothesis
            enriched.append(
                {
                    **h,
                    "campaign_name": campaign_name,
                    "evidence": evidence,
                    "impact": impact,
                    "confidence": round(confidence, 3),
                }
            )

        return enriched

    # Keep this for backward compatibility if used elsewhere
    def validate_ctr_change(self, pre: List[float], post: List[float]) -> Dict[str, float]:
        pre_mean = self._safe_mean(pre)
        post_mean = self._safe_mean(post)
        delta_pct = self._pct_change(pre_mean, post_mean)
        return {
            "pre_ctr": pre_mean,
            "post_ctr": post_mean,
            "delta_pct": delta_pct,
        }
