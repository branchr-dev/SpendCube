"""SpendCube supplier parent company mapping via LLM enrichment."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — allow running as a script from any directory
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.config import load_config
from src.utils.logging import get_logger_from_config, log_llm_call


class ParentMapper:
    """Stage 5: LLM-based parent company enrichment for canonical suppliers.

    Batches supplier names and calls Claude to identify ultimate parent
    companies or corporate groups. Results are always capped at LOW
    confidence (0.50) since LLM results require human review.

    When ``config.llm.dry_run`` is True no API calls are made.
    """

    def __init__(self, config) -> None:
        self.config = config
        self.logger = get_logger_from_config(__name__, config)
        self._client = None

        if not config.llm.dry_run:
            try:
                import anthropic  # noqa: PLC0415
                api_key = os.environ.get(config.llm.api_key_env)
                self._client = anthropic.Anthropic(api_key=api_key)
            except ImportError:
                self.logger.error(
                    "anthropic package not installed — LLM enrichment unavailable"
                )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enrich(self, supplier_names: list[str]) -> list[dict]:
        """Identify parent companies for a list of canonical supplier names.

        Args:
            supplier_names: List of canonical supplier name strings.

        Returns:
            List of dicts (one per input name) with keys:
            ``supplier_name``, ``parent_company_name``, ``confidence``,
            ``method``.
        """
        if self.config.llm.dry_run:
            self.logger.info("DRY RUN: skipping parent company LLM enrichment")
            return [
                {
                    "supplier_name": name,
                    "parent_company_name": None,
                    "confidence": 0.0,
                    "method": "DRY_RUN",
                }
                for name in supplier_names
            ]

        if not self._client:
            self.logger.error("No Anthropic client — returning empty results")
            return [
                {
                    "supplier_name": name,
                    "parent_company_name": None,
                    "confidence": 0.0,
                    "method": "LLM_UNAVAILABLE",
                }
                for name in supplier_names
            ]

        batch_size = self.config.llm.batch_size
        results: list[dict] = []

        for start in range(0, len(supplier_names), batch_size):
            batch = supplier_names[start : start + batch_size]
            batch_results = self._enrich_batch(batch)
            results.extend(batch_results)

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _enrich_batch(self, batch: list[str]) -> list[dict]:
        """Send a single Claude API call for one batch of supplier names."""
        names_json = json.dumps(batch, indent=2)
        prompt = (
            "For each of the following supplier names, identify the ultimate parent "
            "company or corporate group if known. If unsure, return null. "
            "Format: JSON array of objects with fields: supplier_name, "
            "parent_company_name (null if unknown or same entity), confidence (0.0-1.0). "
            "Only include well-known parent relationships you are confident about.\n\n"
            f"Suppliers:\n{names_json}"
        )

        model = self.config.llm.model

        try:
            response = self._client.messages.create(
                model=model,
                max_tokens=1000,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.error("LLM API error for batch: %s", exc)
            return [
                {
                    "supplier_name": name,
                    "parent_company_name": None,
                    "confidence": 0.0,
                    "method": "LLM_ERROR",
                }
                for name in batch
            ]

        response_text = response.content[0].text if response.content else ""
        tokens_used = (response.usage.input_tokens or 0) + (response.usage.output_tokens or 0)

        log_llm_call(
            self.logger,
            prompt=prompt,
            response=response_text,
            model=model,
            tokens_used=tokens_used,
        )

        return self._parse_response(response_text, batch)

    def _parse_response(self, response_text: str, batch: list[str]) -> list[dict]:
        """Parse JSON from the LLM response, cap confidence at 0.50."""
        # Strip markdown code fences if present
        text = response_text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(
                line for line in lines if not line.startswith("```")
            ).strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            self.logger.warning("Failed to parse LLM JSON response; falling back to nulls")
            return [
                {
                    "supplier_name": name,
                    "parent_company_name": None,
                    "confidence": 0.0,
                    "method": "LLM_PARSE_ERROR",
                }
                for name in batch
            ]

        # Build a lookup by supplier_name from the parsed results
        parsed_by_name: dict[str, dict] = {}
        for item in parsed:
            if isinstance(item, dict) and "supplier_name" in item:
                parsed_by_name[item["supplier_name"]] = item

        results: list[dict] = []
        for name in batch:
            item = parsed_by_name.get(name, {})
            raw_confidence = float(item.get("confidence", 0.0))
            capped_confidence = min(raw_confidence, 0.50)
            results.append(
                {
                    "supplier_name": name,
                    "parent_company_name": item.get("parent_company_name"),
                    "confidence": capped_confidence,
                    "method": "LLM_PARENT",
                }
            )

        return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    config = load_config()
    mapper = ParentMapper(config)

    sample_suppliers = [
        "acme",
        "sodexo australia",
        "dhl express",
        "telstra",
        "microsoft",
    ]

    print(f"Enriching {len(sample_suppliers)} suppliers (dry_run={config.llm.dry_run})...\n")
    results = mapper.enrich(sample_suppliers)
    for r in results:
        parent = r["parent_company_name"] or "(none)"
        print(
            f"  {r['supplier_name']:<30} → {parent:<30} "
            f"conf={r['confidence']:.2f}  method={r['method']}"
        )
