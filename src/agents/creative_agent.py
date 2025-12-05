from __future__ import annotations

from typing import List, Dict, Any, Optional, Tuple
import uuid
import math


def _short_id() -> str:
    return uuid.uuid4().hex[:8]


class CreativeAgent:
    """
    Generates creative recommendations that are *tightly linked* to
    the diagnosed performance issues from the insight/evaluator layer.

    Inputs:
    - campaign_name: name of the campaign
    - examples: list of existing creative messages (strings)
    - insights: enriched hypotheses for this campaign
      (each with id, hypothesis, evidence, impact, confidence)

    Output:
    - List[Dict] of creatives with:
        - id
        - headline
        - message
        - cta
        - rationale
        - linked_issue
    """

    def __init__(self, default_cta: str = "Shop now"):
        self.default_cta = default_cta


    def suggest(
        self,
        campaign_name: str,
        examples: List[str],
        insights: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate 3 creatives that respond to the primary diagnosed issue.

        If no insights are provided, falls back to generic patterns.
        """
        primary_issue, primary_hypo = self._select_primary_issue(insights or [])

        if primary_issue is None:
            return self._generic_creatives(campaign_name, examples)

        return self._issue_aware_creatives(
            campaign_name=campaign_name,
            examples=examples,
            issue_id=primary_issue,
            hypothesis=primary_hypo,
        )


    @staticmethod
    def choose_primary_issue(
        insights: List[Dict[str, Any]]
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Choose the most important issue based on:
        - impact: high > medium > low
        - confidence: numeric score [0, 1]

        Returns (issue_id, full_hypothesis_dict) or (None, None).
        """
        if not insights:
            return None, None

        impact_weight = {"high": 3, "medium": 2, "low": 1}

        best = None
        best_score = -1.0

        for h in insights:
            hid = h.get("id")
            impact = h.get("impact", "low")
            conf = float(h.get("confidence", 0.3) or 0.3)

            if hid in ("h_none", "h_insufficient_data"):
                continue

            score = impact_weight.get(impact, 1) * conf
            if score > best_score:
                best_score = score
                best = h

        if best is None:
            return None, None

        return best.get("id"), best

    def _select_primary_issue(
        self, insights: List[Dict[str, Any]]
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Instance wrapper for backwards compatibility.
        Calls the static `choose_primary_issue`.
        """
        return self.choose_primary_issue(insights)


    def _issue_aware_creatives(
        self,
        campaign_name: str,
        examples: List[str],
        issue_id: str,
        hypothesis: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Map issue types to specific creative strategies.
        """
        base_example = self._extract_base_example(examples)
        ev = hypothesis.get("evidence", {}) or {}
        delta_pct = None

        if isinstance(ev, dict):
            if "delta_pct" in ev:
                delta_pct = ev.get("delta_pct")
            elif isinstance(ev.get("ctr"), dict) and "delta_pct" in ev["ctr"]:
                delta_pct = ev["ctr"]["delta_pct"]

        delta_str = None
        if isinstance(delta_pct, (int, float)) and not math.isinf(delta_pct):
            delta_str = f"{delta_pct:.1f}%"

        linked_issue = hypothesis.get("hypothesis", issue_id)

        if issue_id == "h_roas_drop":
            return self._creatives_for_roas_drop(
                campaign_name, base_example, linked_issue, delta_str
            )
        elif issue_id == "h_ctr_drop":
            return self._creatives_for_ctr_drop(
                campaign_name, base_example, linked_issue, delta_str
            )
        elif issue_id == "h_fatigue":
            return self._creatives_for_fatigue(
                campaign_name, base_example, linked_issue, delta_str
            )
        else:
            return self._generic_creatives(campaign_name, examples, linked_issue=linked_issue)

    def _creatives_for_roas_drop(
        self,
        campaign_name: str,
        base_example: str,
        linked_issue: str,
        delta_str: Optional[str],
    ) -> List[Dict[str, Any]]:
        """
        ROAS drop → focus on:
        - Stronger value proposition
        - Clear pricing / discount
        - Social proof / trust
        - Push for purchase
        """
        change_phrase = f"{delta_str} drop in ROAS" if delta_str else "a recent ROAS drop"

        return [
            {
                "id": _short_id(),
                "headline": "Only today: extra savings on your favourites",
                "message": f"{campaign_name}: Lock in comfort and value now. Limited-time offer to recover from {change_phrase}.",
                "cta": self.default_cta,
                "rationale": f"Addresses ROAS decline by adding a stronger value + discount hook tightly tied to {linked_issue}.",
                "linked_issue": linked_issue,
            },
            {
                "id": _short_id(),
                "headline": "Bestsellers, now with bundle offers",
                "message": f"Turn high-intent visitors into buyers with bundle pricing on {campaign_name}. Make it easier to justify the cart.",
                "cta": self.default_cta,
                "rationale": "Improves conversion by using bundles and perceived savings — common fix when ROAS drops but traffic is present.",
                "linked_issue": linked_issue,
            },
            {
                "id": _short_id(),
                "headline": "Why customers love this fit",
                "message": f"Real reviews, real comfort. Highlight rating badges and reviews for {campaign_name} to rebuild trust and lift ROAS.",
                "cta": self.default_cta,
                "rationale": "Uses social proof and trust elements to improve purchase rate — a core driver of ROAS.",
                "linked_issue": linked_issue,
            },
        ]

    def _creatives_for_ctr_drop(
        self,
        campaign_name: str,
        base_example: str,
        linked_issue: str,
        delta_str: Optional[str],
    ) -> List[Dict[str, Any]]:
        """
        CTR drop → focus on:
        - Thumb-stopping hook
        - Clear benefit in first line
        - Strong visual idea
        """
        change_phrase = f"{delta_str} drop in CTR" if delta_str else "a recent CTR drop"

        return [
            {
                "id": _short_id(),
                "headline": "Scroll-stopping comfort you can feel",
                "message": f"Open with a bold visual of {campaign_name} in use. First line: 'All-day comfort, zero adjustments.' Fixes {change_phrase} by improving the hook.",
                "cta": self.default_cta,
                "rationale": "Directly tackles low CTR with a stronger first-line benefit and visual concept.",
                "linked_issue": linked_issue,
            },
            {
                "id": _short_id(),
                "headline": "Still wearing basic innerwear?",
                "message": f"Ask a provocative question to disrupt the feed, then show how {campaign_name} feels vs regular options.",
                "cta": self.default_cta,
                "rationale": "Question-based hook to re-engage a tired audience and recover click-through.",
                "linked_issue": linked_issue,
            },
            {
                "id": _short_id(),
                "headline": "Upgrade your everyday comfort",
                "message": (f"Use a clean, minimal creative: one product visual, one line — '{base_example or 'Comfort that disappears under clothes'}'.").strip(),
                "cta": self.default_cta,
                "rationale": "Simplifies the message when CTR drops due to cluttered creatives.",
                "linked_issue": linked_issue,
            },
        ]

    def _creatives_for_fatigue(
        self,
        campaign_name: str,
        base_example: str,
        linked_issue: str,
        delta_str: Optional[str],
    ) -> List[Dict[str, Any]]:
        """
        Creative fatigue (impressions up, CTR down) → focus on:
        - New angles
        - New visuals
        - Variant testing (colour, model, background)
        """
        change_phrase = f"impressions up with CTR down ({delta_str})" if delta_str else "impressions up with CTR down"

        return [
            {
                "id": _short_id(),
                "headline": "New colours, same loved comfort",
                "message": f"{campaign_name} in fresh colours and backgrounds. Refresh the feed presence to counter {change_phrase}.",
                "cta": self.default_cta,
                "rationale": "New visual variants to reset fatigue while keeping proven product benefits.",
                "linked_issue": linked_issue,
            },
            {
                "id": _short_id(),
                "headline": "From office to home in one fit",
                "message": f"Show different use-cases of {campaign_name}: work, lounge, travel. New storytelling angle instead of repeating the same product shot.",
                "cta": self.default_cta,
                "rationale": "Introduces a new narrative angle to fight repetitive-feel fatigue.",
                "linked_issue": linked_issue,
            },
            {
                "id": _short_id(),
                "headline": "Make your old innerwear jealous",
                "message": f"Humour-based creative for {campaign_name}: playful copy + bold typography to reset pattern recognition in the feed.",
                "cta": self.default_cta,
                "rationale": "Uses humour and pattern disruption to combat creative fatigue.",
                "linked_issue": linked_issue,
            },
        ]


    def _generic_creatives(
        self,
        campaign_name: str,
        examples: List[str],
        linked_issue: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        base_example = self._extract_base_example(examples)
        linked_issue = linked_issue or "No major performance issue detected"

        return [
            {
                "id": _short_id(),
                "headline": f"{campaign_name}: all-day comfort, zero compromise",
                "message": base_example
                or f"Experience soft, breathable fabric designed for everyday confidence with {campaign_name}.",
                "cta": self.default_cta,
                "rationale": "Generic high-quality creative for stable or scaling campaigns.",
                "linked_issue": linked_issue,
            },
            {
                "id": _short_id(),
                "headline": "Limited-time offer on bestsellers",
                "message": f"Turn stable performance into scale: push {campaign_name} with a simple, time-bound discount message.",
                "cta": self.default_cta,
                "rationale": "Adds light urgency to stable campaigns to test upside.",
                "linked_issue": linked_issue,
            },
            {
                "id": _short_id(),
                "headline": "Why customers keep reordering",
                "message": f"Introduce social proof for {campaign_name}: highlight ratings, reviews and reorders in the creative.",
                "cta": self.default_cta,
                "rationale": "Leverages trust and proof even when no major issue is detected.",
                "linked_issue": linked_issue,
            },
        ]


    def _extract_base_example(self, examples: List[str]) -> str:
        """
        Take the first non-empty creative message as a 'tone' reference.
        """
        for msg in examples:
            msg = (msg or "").strip()
            if msg:
                return msg
        return ""