"""SpendCube LLM narrative generation for recommendations.

Optionally enriches rule-based recommendations with consulting-quality narrative
text using the Claude API.  Skipped entirely when dry_run=true.

Every LLM call is logged via log_llm_call() for auditability.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

# Ensure project root is on sys.path when run as a script.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.utils.logging import get_logger_from_config, log_llm_call

_PROMPT_TEMPLATE = (
    "You are a procurement consultant. For each recommendation, write a concise "
    "2-3 sentence consulting-quality narrative explaining the issue, evidence, and "
    "recommended action. Format: JSON array with fields: type, context, narrative."
    "\n\nRecommendations:\n{recs_json}"
)


class NarrativeGenerator:
    """Enrich recommendations with LLM-generated consulting narratives.

    Args:
        config: SpendCube Config object.  Reads ``config.llm.dry_run``,
                ``config.llm.model``, and ``config.llm.api_key_env``.
    """

    def __init__(self, config) -> None:
        self.config = config
        self.logger = get_logger_from_config(__name__, config)

        self._dry_run: bool = getattr(getattr(config, "llm", None), "dry_run", True)
        self._model: str = getattr(
            getattr(config, "llm", None), "model", "claude-sonnet-4-6"
        )

        # Initialise Anthropic client only when not dry_run.
        self._client: Optional[object] = None
        if not self._dry_run:
            try:
                import anthropic  # noqa: PLC0415
                import os

                api_key_env = getattr(
                    getattr(config, "llm", None), "api_key_env", "ANTHROPIC_API_KEY"
                )
                api_key = os.environ.get(api_key_env)
                self._client = (
                    anthropic.Anthropic(api_key=api_key)
                    if api_key
                    else anthropic.Anthropic()
                )
                self.logger.info("Anthropic client initialised for narrative generation")
            except ImportError:
                self.logger.warning(
                    "anthropic SDK not installed — narrative generation will be skipped. "
                    "Install with: pip install anthropic"
                )

    def enrich(self, recommendations: list[dict]) -> list[dict]:
        """Optionally enrich recommendations with consulting-quality narratives.

        When ``dry_run=true`` each recommendation is returned unchanged with
        ``narrative=None``.  When live, all recommendations are batched into a
        single Claude API call and the returned narrative strings are merged back
        into each recommendation dict.

        Args:
            recommendations: List of recommendation dicts produced by
                             :class:`~src.recommendations.rules.RecommendationRules`.

        Returns:
            The same list with a ``narrative`` key added to every dict.
            On API error the narrative key is set to ``None`` and a warning
            is logged, but no exception is raised.
        """
        # Always stamp the narrative key so callers can rely on its presence.
        recs = [dict(r, narrative=None) for r in recommendations]

        if self._dry_run:
            self.logger.debug(
                "dry_run=true — skipping narrative generation for %d recommendation(s)",
                len(recs),
            )
            return recs

        if not recs:
            return recs

        if self._client is None:
            self.logger.warning(
                "Anthropic client not available — returning recommendations without narratives"
            )
            return recs

        return self._call_llm(recs)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _call_llm(self, recs: list[dict]) -> list[dict]:
        """Send all recommendations to Claude in one call and merge narratives."""
        # Build a compact payload for the prompt (omit the narrative key itself).
        payload = [
            {k: v for k, v in r.items() if k != "narrative"}
            for r in recs
        ]
        recs_json = json.dumps(payload, indent=2)
        prompt = _PROMPT_TEMPLATE.format(recs_json=recs_json)

        response_text = ""
        tokens_used = 0
        try:
            response = self._client.messages.create(  # type: ignore[union-attr]
                model=self._model,
                max_tokens=4096,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            response_text = response.content[0].text if response.content else ""
            if hasattr(response, "usage"):
                tokens_used = (
                    response.usage.input_tokens + response.usage.output_tokens
                )
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(
                "LLM narrative generation failed: %s — returning recommendations without narratives",
                exc,
            )
            log_llm_call(
                self.logger,
                prompt=prompt,
                response=str(exc),
                model=self._model,
            )
            return recs

        log_llm_call(
            self.logger,
            prompt=prompt,
            response=response_text,
            model=self._model,
            tokens_used=tokens_used,
        )

        # Parse JSON response and merge narratives.
        try:
            parsed = self._parse_response(response_text)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(
                "Failed to parse narrative response: %s — returning recommendations without narratives",
                exc,
            )
            return recs

        # Build lookup keyed on (type, context) — the combination is unique
        # enough for matching across the small recommendation list.
        narrative_by_key: dict[tuple[str, str], str] = {}
        for item in parsed:
            key = (str(item.get("type", "")), str(item.get("context", "")))
            narrative_by_key[key] = str(item.get("narrative", ""))

        merged: list[dict] = []
        for rec in recs:
            key = (str(rec.get("type", "")), str(rec.get("context", "")))
            narrative = narrative_by_key.get(key)
            merged.append(dict(rec, narrative=narrative))

        self.logger.info(
            "Narrative generation complete: %d/%d recommendations enriched",
            sum(1 for r in merged if r.get("narrative")),
            len(merged),
        )
        return merged

    @staticmethod
    def _parse_response(response_text: str) -> list[dict]:
        """Parse a Claude JSON response, stripping markdown fences if present."""
        text = response_text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            lines = lines[1:]  # remove opening fence
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines)

        parsed = json.loads(text)
        if not isinstance(parsed, list):
            raise ValueError(
                f"Expected JSON array from LLM, got {type(parsed).__name__}"
            )
        return parsed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from src.config import load_config  # noqa: PLC0415

    config = load_config("config.yaml")
    dry_run = getattr(getattr(config, "llm", None), "dry_run", True)

    # Sample recommendations to demonstrate the enrichment pipeline.
    sample_recommendations = [
        {
            "type": "TAIL_SPEND_RATIONALISATION",
            "context": "Portfolio",
            "evidence": "47 tail suppliers, 18.3% of spend",
            "estimated_impact_aud": 91500.0,
            "confidence": "MEDIUM",
            "action": "Rationalise 47 tail suppliers — consolidate or eliminate low-value vendors",
            "lever": "Tail Spend Rationalisation",
        },
        {
            "type": "CONTRACT_COMPLIANCE",
            "context": "Portfolio",
            "evidence": "32.1% of spend is maverick (no PO and not on-contract)",
            "estimated_impact_aud": 80250.0,
            "confidence": "MEDIUM",
            "action": "Enforce PO compliance and contract coverage for maverick spend categories",
            "lever": "Contract Compliance",
        },
        {
            "type": "COMPETITIVE_TENDER",
            "context": "Professional Services",
            "evidence": "Single source: all Professional Services spend ($210,000) with Acme Consulting",
            "estimated_impact_aud": 14700.0,
            "confidence": "HIGH",
            "action": "Run competitive tender for Professional Services — currently single-sourced from Acme Consulting",
            "lever": "Competitive Sourcing",
        },
    ]

    generator = NarrativeGenerator(config)

    print(f"\n{'=' * 80}")
    print(f"  NarrativeGenerator CLI  (dry_run={dry_run})")
    print(f"{'=' * 80}\n")

    enriched = generator.enrich(sample_recommendations)

    for i, rec in enumerate(enriched, 1):
        impact = rec.get("estimated_impact_aud", 0.0)
        print(f"#{i:02d}  [{rec.get('type', 'UNKNOWN')}]  {rec.get('context', '')}")
        print(f"     Impact:    ${impact:,.0f} AUD  |  Confidence: {rec.get('confidence', 'N/A')}")
        print(f"     Evidence:  {rec.get('evidence', '')}")
        print(f"     Narrative: {rec.get('narrative') or '(not generated — dry_run=true)'}")
        print()

    if dry_run:
        print("To generate narratives, set llm.dry_run: false in config.yaml and set ANTHROPIC_API_KEY.")
