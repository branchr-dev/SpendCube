"""SpendCube LLM-based spend categorisation using Claude.

Implements Pass 5 of the categorisation pipeline: batched Claude API
classification for transactions still unclassified after passes 0-4.

Respects dry_run mode — no API calls when dry_run=true.
Confidence capped at 0.70 regardless of model output.
Every call logged via log_llm_call() for auditability.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

# Ensure project root is on sys.path when run as a script.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.models.schema import CategoryMethod
from src.utils.logging import get_logger_from_config, log_llm_call

_LLM_CONFIDENCE_CAP = 0.70


class LLMCategoriser:
    """Pass 5 of the categorisation pipeline — LLM fallback via Claude API.

    Only invoked for transactions that remain below the confidence threshold
    after passes 0-4.  Batches 20 items per API call.  Confidence capped at
    0.70 regardless of model output.  All calls logged for auditability.

    Args:
        config: SpendCube Config object (provides llm.dry_run, llm.model, etc.)
        hierarchy_path: Path to internal_category_hierarchy.csv.
    """

    def __init__(self, config, hierarchy_path: str) -> None:
        self.config = config
        self.logger = get_logger_from_config(__name__, config)

        # ── Load hierarchy and build L1 category list ──────────────────────
        hierarchy = pd.read_csv(hierarchy_path)
        self.logger.info(f"Loaded {len(hierarchy)} hierarchy rows from {hierarchy_path}")

        l1_names = hierarchy["l1_name"].unique().tolist()
        self._l1_list = ", ".join(sorted(l1_names))
        self.logger.info(f"L1 categories: {self._l1_list}")

        # ── Initialise Anthropic client (only when not dry_run) ────────────
        self._client: Optional[object] = None
        dry_run = getattr(getattr(config, "llm", None), "dry_run", True)

        if not dry_run:
            try:
                import anthropic  # noqa: PLC0415
                import os

                api_key_env = getattr(
                    getattr(config, "llm", None), "api_key_env", "ANTHROPIC_API_KEY"
                )
                api_key = os.environ.get(api_key_env)
                self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
                self.logger.info("Anthropic client initialised")
            except ImportError:
                self.logger.warning(
                    "anthropic SDK not installed — LLM pass will be skipped. "
                    "Install with: pip install anthropic"
                )

    # ── Batch classify (list[dict] interface) ─────────────────────────────

    def classify_batch(self, items: list[dict], config) -> list[dict]:
        """Classify a batch of transaction dicts via the Claude API.

        Args:
            items: List of dicts with keys: transaction_id, description,
                   supplier_name, gl_account.
            config: SpendCube Config object.

        Returns:
            List of result dicts with keys: transaction_id,
            internal_category_l1, internal_category_l2, internal_category_l3,
            unspsc_segment_code, confidence, method, reasoning.
        """
        dry_run = getattr(getattr(config, "llm", None), "dry_run", True)

        if dry_run:
            return [
                {
                    "transaction_id": item.get("transaction_id"),
                    "internal_category_l1": None,
                    "internal_category_l2": None,
                    "internal_category_l3": None,
                    "unspsc_segment_code": None,
                    "confidence": 0.0,
                    "method": "DRY_RUN",
                    "reasoning": None,
                }
                for item in items
            ]

        if not items:
            return []

        batch_size = getattr(getattr(config, "llm", None), "batch_size", 20)
        model = getattr(getattr(config, "llm", None), "model", "claude-sonnet-4-20250514")

        results: list[dict] = []

        for batch_start in range(0, len(items), batch_size):
            batch = items[batch_start : batch_start + batch_size]
            batch_results = self._call_llm_batch(batch, model)
            results.extend(batch_results)

        return results

    def _call_llm_batch(self, batch: list[dict], model: str) -> list[dict]:
        """Call Claude API for a single batch and return parsed results."""
        if self._client is None:
            self.logger.warning("Anthropic client not available — skipping batch")
            return [
                {
                    "transaction_id": item.get("transaction_id"),
                    "internal_category_l1": None,
                    "internal_category_l2": None,
                    "internal_category_l3": None,
                    "unspsc_segment_code": None,
                    "confidence": 0.0,
                    "method": "LLM",
                    "reasoning": "client unavailable",
                }
                for item in batch
            ]

        transactions_json = json.dumps(
            [
                {
                    "transaction_id": item.get("transaction_id"),
                    "description": item.get("description", ""),
                    "supplier_name": item.get("supplier_name", ""),
                    "gl_account": item.get("gl_account", ""),
                }
                for item in batch
            ],
            indent=2,
        )

        prompt = (
            "You are a procurement spend categorisation expert. "
            "Classify each transaction into the most appropriate category "
            "from the provided taxonomy. Return a JSON array.\n\n"
            f"Valid L1 categories: {self._l1_list}\n\n"
            f"Transactions to classify:\n{transactions_json}\n\n"
            "For each transaction return: transaction_id, internal_category_l1, "
            "internal_category_l2 (or null), internal_category_l3 (or null), "
            "unspsc_segment_code (or null), confidence (0.0-1.0), "
            "reasoning (one sentence)."
        )

        response_text = ""
        try:
            response = self._client.messages.create(
                model=model,
                max_tokens=2000,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            response_text = response.content[0].text if response.content else ""
            tokens_used = (
                response.usage.input_tokens + response.usage.output_tokens
                if hasattr(response, "usage")
                else 0
            )
        except Exception as exc:
            self.logger.error(f"LLM API call failed: {exc}")
            log_llm_call(self.logger, prompt=prompt, response=str(exc), model=model)
            return [
                {
                    "transaction_id": item.get("transaction_id"),
                    "internal_category_l1": None,
                    "internal_category_l2": None,
                    "internal_category_l3": None,
                    "unspsc_segment_code": None,
                    "confidence": 0.0,
                    "method": "LLM",
                    "reasoning": f"API error: {exc}",
                }
                for item in batch
            ]
        else:
            log_llm_call(
                self.logger,
                prompt=prompt,
                response=response_text,
                model=model,
                tokens_used=tokens_used,
            )

        # ── Parse JSON response ────────────────────────────────────────────
        try:
            # Strip markdown code fences if present
            text = response_text.strip()
            if text.startswith("```"):
                lines = text.splitlines()
                # Remove opening fence (```json or ```)
                lines = lines[1:]
                # Remove closing fence
                if lines and lines[-1].strip().startswith("```"):
                    lines = lines[:-1]
                text = "\n".join(lines)

            parsed = json.loads(text)
            if not isinstance(parsed, list):
                raise ValueError(f"Expected JSON array, got {type(parsed).__name__}")
        except Exception as exc:
            self.logger.error(f"Failed to parse LLM response as JSON: {exc}")
            return [
                {
                    "transaction_id": item.get("transaction_id"),
                    "internal_category_l1": None,
                    "internal_category_l2": None,
                    "internal_category_l3": None,
                    "unspsc_segment_code": None,
                    "confidence": 0.0,
                    "method": "LLM",
                    "reasoning": f"parse error: {exc}",
                }
                for item in batch
            ]

        # ── Build result list, capping confidence ─────────────────────────
        # Index parsed results by transaction_id for lookup
        parsed_by_id: dict[str, dict] = {}
        for row in parsed:
            tid = str(row.get("transaction_id", ""))
            parsed_by_id[tid] = row

        results = []
        for item in batch:
            tid = str(item.get("transaction_id", ""))
            row = parsed_by_id.get(tid)
            if row is None:
                self.logger.warning(f"LLM response missing result for transaction_id={tid}")
                results.append(
                    {
                        "transaction_id": item.get("transaction_id"),
                        "internal_category_l1": None,
                        "internal_category_l2": None,
                        "internal_category_l3": None,
                        "unspsc_segment_code": None,
                        "confidence": 0.0,
                        "method": "LLM",
                        "reasoning": "missing from LLM response",
                    }
                )
                continue

            raw_confidence = float(row.get("confidence", 0.0))
            capped_confidence = min(raw_confidence, _LLM_CONFIDENCE_CAP)

            results.append(
                {
                    "transaction_id": item.get("transaction_id"),
                    "internal_category_l1": row.get("internal_category_l1"),
                    "internal_category_l2": row.get("internal_category_l2"),
                    "internal_category_l3": row.get("internal_category_l3"),
                    "unspsc_segment_code": row.get("unspsc_segment_code"),
                    "confidence": capped_confidence,
                    "method": CategoryMethod.LLM.value,
                    "reasoning": row.get("reasoning"),
                }
            )

        return results

    # ── DataFrame interface ───────────────────────────────────────────────

    def classify_dataframe(
        self, df: pd.DataFrame, config
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Classify a DataFrame of unclassified transactions via the LLM.

        Args:
            df: DataFrame of transactions (not yet classified by passes 0-4).
            config: SpendCube Config object.

        Returns:
            (classified_df, unclassified_df) — unclassified = rows where LLM
            returned None category or confidence=0.
        """
        if df.empty:
            return pd.DataFrame(columns=df.columns), df.copy()

        # Build item dicts from DataFrame rows
        items = []
        for idx, row in df.iterrows():
            description = ""
            if "cleaned_description" in df.columns and pd.notna(row.get("cleaned_description")):
                description = str(row["cleaned_description"])
            elif "raw_line_description" in df.columns and pd.notna(row.get("raw_line_description")):
                description = str(row["raw_line_description"])

            items.append(
                {
                    "transaction_id": str(idx),  # use DataFrame index as transaction_id
                    "description": description,
                    "supplier_name": str(row.get("canonical_supplier_name", row.get("raw_supplier_name", ""))),
                    "gl_account": str(row.get("gl_account", "")),
                    "_df_index": idx,
                }
            )

        results = self.classify_batch(items, config)

        # Map results back to DataFrame
        df = df.copy()
        for col in (
            "category_l1", "category_l2", "category_l3",
            "unspsc_code", "category_confidence", "category_method",
        ):
            if col not in df.columns:
                df[col] = None

        results_by_id = {str(r["transaction_id"]): r for r in results}
        classified_mask = pd.Series(False, index=df.index)

        for item in items:
            idx = item["_df_index"]
            tid = str(idx)
            result = results_by_id.get(tid)
            if result is None:
                continue

            df.at[idx, "category_l1"] = result.get("internal_category_l1")
            df.at[idx, "category_l2"] = result.get("internal_category_l2")
            df.at[idx, "category_l3"] = result.get("internal_category_l3")
            df.at[idx, "unspsc_code"] = result.get("unspsc_segment_code")
            df.at[idx, "category_confidence"] = result.get("confidence", 0.0)
            df.at[idx, "category_method"] = result.get("method")

            # Classified = LLM returned a category AND confidence > 0
            if (
                result.get("internal_category_l1") is not None
                and result.get("confidence", 0.0) > 0.0
            ):
                classified_mask.at[idx] = True

        classified = df[classified_mask].copy()
        unclassified = df[~classified_mask].copy()

        dry_run = getattr(getattr(config, "llm", None), "dry_run", True)
        mode = "DRY RUN" if dry_run else "live"
        self.logger.info(
            f"Pass 5 (LLM {mode}): {len(classified)} classified, "
            f"{len(unclassified)} unclassified"
        )
        return classified, unclassified


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from src.config import load_config

    config = load_config("config.yaml")
    hierarchy_path = str(
        Path(config.paths.reference_dir) / "internal_category_hierarchy.csv"
    )

    classifier = LLMCategoriser(config=config, hierarchy_path=hierarchy_path)

    dry_run = getattr(getattr(config, "llm", None), "dry_run", True)

    sample_items = [
        {
            "transaction_id": "TXN-001",
            "description": "Office supplies - toner cartridges HP",
            "supplier_name": "Officeworks",
            "gl_account": "6420",
        },
        {
            "transaction_id": "TXN-002",
            "description": "Catering - Q1 events",
            "supplier_name": "Compass Group",
            "gl_account": "7100",
        },
        {
            "transaction_id": "TXN-003",
            "description": "International freight - Shanghai to Melbourne",
            "supplier_name": "DHL Express",
            "gl_account": "5200",
        },
        {
            "transaction_id": "TXN-004",
            "description": "Mobile fleet management - Feb 2024",
            "supplier_name": "Telstra",
            "gl_account": "6300",
        },
        {
            "transaction_id": "TXN-005",
            "description": "Legal advisory fees - restructuring",
            "supplier_name": "Herbert Smith Freehills",
            "gl_account": "8100",
        },
    ]

    if dry_run:
        print("DRY RUN — no API calls will be made")
        print(f"Model that would be used: {config.llm.model}")
        print(f"Batch size: {config.llm.batch_size}")
        print(f"\nSample items that would be sent to LLM ({len(sample_items)} items):")
        for item in sample_items:
            print(f"  [{item['transaction_id']}] {item['description']!r}")
            print(f"         supplier={item['supplier_name']!r}, gl={item['gl_account']!r}")
        print(f"\nRunning classify_batch in DRY RUN mode...")
        results = classifier.classify_batch(sample_items, config)
        print(f"\nResults ({len(results)} items, all method=DRY_RUN):")
        for r in results:
            print(
                f"  [{r['transaction_id']}] l1={r['internal_category_l1']} "
                f"conf={r['confidence']} method={r['method']}"
            )
    else:
        print(f"LIVE mode — will call {config.llm.model}")
        results = classifier.classify_batch(sample_items, config)
        print(f"\nResults:")
        for r in results:
            print(
                f"  [{r['transaction_id']}] "
                f"l1={r['internal_category_l1']} l2={r['internal_category_l2']} "
                f"conf={r['confidence']:.2f} method={r['method']}"
            )
            if r.get("reasoning"):
                print(f"         reasoning: {r['reasoning']}")
