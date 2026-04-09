"""SpendCube embedding-based spend classifier.

Implements Pass 4 of the categorisation pipeline: encodes transaction
descriptions with sentence-transformers and compares against pre-computed
category description embeddings.

Only invoked for transactions not classified by passes 0-3.
"""

from __future__ import annotations

import pickle
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# Ensure project root is on sys.path when run as a script.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.models.schema import CategoryMethod
from src.utils.logging import get_logger_from_config

try:
    from sentence_transformers import SentenceTransformer
    _SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    _SENTENCE_TRANSFORMERS_AVAILABLE = False


class EmbeddingCategoriser:
    """Pass 4 of the categorisation pipeline — embedding similarity classification.

    Loads the internal category hierarchy, builds rich category descriptions at
    the L2 level, computes sentence-transformer embeddings, and caches them to
    disk.  At classify time, encodes a transaction description and returns the
    best matching category via cosine similarity.

    Args:
        hierarchy_path: Path to internal_category_hierarchy.csv.
        model_name: Sentence-transformer model identifier.
        cache_path: Path to pickle file for persisting category embeddings.
        config: SpendCube Config object (used for logging configuration).
    """

    def __init__(
        self,
        hierarchy_path: str,
        model_name: str = "all-MiniLM-L6-v2",
        cache_path: str = "data/cache/category_embeddings.pkl",
        config=None,
    ) -> None:
        self.config = config
        if config is not None:
            self.logger = get_logger_from_config(__name__, config)
        else:
            import logging
            self.logger = logging.getLogger(__name__)

        self._model: Optional[object] = None
        self._available = _SENTENCE_TRANSFORMERS_AVAILABLE

        if not self._available:
            self.logger.warning(
                "sentence-transformers not installed — EmbeddingCategoriser will "
                "pass all rows through to LLM. Install with: pip install sentence-transformers"
            )

        # ── Load hierarchy ────────────────────────────────────────────────
        hierarchy = pd.read_csv(hierarchy_path)
        self.logger.info(f"Loaded {len(hierarchy)} hierarchy rows from {hierarchy_path}")

        # ── Build L2-level category descriptions ──────────────────────────
        # For each unique L2, concatenate l1_name + l2_name + all L3 names.
        # This gives richer semantic content for embedding similarity.
        self._categories: list[dict] = []
        for (l2_code, l2_name), group in hierarchy.groupby(["l2_code", "l2_name"]):
            first = group.iloc[0]
            l3_names = " ".join(group["l3_name"].dropna().unique().tolist())
            description = f"{first['l1_name']} {l2_name} {l3_names}".strip()
            self._categories.append(
                {
                    "l1_name": first["l1_name"],
                    "l2_name": l2_name,
                    "l2_code": str(l2_code),
                    "unspsc_segment_code": str(first["unspsc_segment_code"]),
                    "description": description,
                }
            )

        self.logger.info(f"Built {len(self._categories)} L2-level category descriptions")

        # ── Load or compute category embeddings ───────────────────────────
        self._cache_path = Path(cache_path)
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)

        self._category_embeddings: Optional[np.ndarray] = None

        if self._available:
            # Load model
            try:
                self._model = SentenceTransformer(model_name)
                self.logger.info(f"Loaded sentence-transformer model: {model_name}")
            except Exception as exc:
                self.logger.warning(f"Failed to load sentence-transformer model: {exc}")
                self._available = False

        if self._available:
            self._category_embeddings = self._load_or_compute_embeddings()

    # ── Embedding management ──────────────────────────────────────────────

    def _load_or_compute_embeddings(self) -> np.ndarray:
        """Load cached category embeddings or compute and cache them."""
        descriptions = [c["description"] for c in self._categories]

        # Try to load from cache
        if self._cache_path.exists():
            try:
                with open(self._cache_path, "rb") as fh:
                    cached = pickle.load(fh)
                if (
                    isinstance(cached, dict)
                    and cached.get("descriptions") == descriptions
                    and "embeddings" in cached
                ):
                    self.logger.info(
                        f"Loaded category embeddings from cache: {self._cache_path}"
                    )
                    return np.array(cached["embeddings"])
            except Exception as exc:
                self.logger.warning(f"Failed to load embedding cache: {exc}")

        # Compute embeddings
        self.logger.info(
            f"Computing embeddings for {len(descriptions)} category descriptions..."
        )
        embeddings = self._model.encode(descriptions, show_progress_bar=False)
        embeddings = np.array(embeddings)

        # Save to cache
        try:
            with open(self._cache_path, "wb") as fh:
                pickle.dump({"descriptions": descriptions, "embeddings": embeddings}, fh)
            self.logger.info(f"Saved category embeddings to cache: {self._cache_path}")
        except Exception as exc:
            self.logger.warning(f"Failed to save embedding cache: {exc}")

        return embeddings

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """Compute cosine similarity between vector a and matrix b (row-wise)."""
        a_norm = a / (np.linalg.norm(a) + 1e-10)
        b_norms = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-10)
        return (b_norms @ a_norm).astype(float)

    # ── Core classify ─────────────────────────────────────────────────────

    def classify(
        self,
        description: str,
        config,
    ) -> tuple[str | None, str | None, str | None, str | None, float, str, str]:
        """Classify a single transaction description via embedding similarity.

        Args:
            description: Transaction description text to classify.
            config: SpendCube Config object with categorisation thresholds.

        Returns:
            (l1, l2, l3, unspsc_segment, confidence, method, evidence)
            If below threshold: l1/l2/l3/unspsc_segment are None, method='EMBEDDING_REJECT'.
        """
        embedding_threshold = getattr(
            getattr(config, "categorisation", None), "embedding_threshold", 0.80
        )

        if not self._available or self._category_embeddings is None or not description:
            return (None, None, None, None, 0.0, "EMBEDDING_REJECT", "sentence-transformers unavailable")

        # Encode description
        desc_embedding = self._model.encode([description], show_progress_bar=False)[0]
        similarities = self._cosine_similarity(desc_embedding, self._category_embeddings)

        # Top-2 indices
        top_indices = np.argsort(similarities)[::-1]
        top_idx = int(top_indices[0])
        second_idx = int(top_indices[1]) if len(top_indices) > 1 else top_idx

        top_similarity = float(similarities[top_idx])
        second_similarity = float(similarities[second_idx])

        best = self._categories[top_idx]
        best_category = f"{best['l1_name']}/{best['l2_name']}"
        evidence = (
            f"cosine={top_similarity:.3f} "
            f"top_category={best_category} "
            f"second={second_similarity:.3f}"
        )

        # Ambiguity check: top-2 within 0.05 AND both above 0.70
        ambiguous = (
            abs(top_similarity - second_similarity) <= 0.05
            and top_similarity > 0.70
            and second_similarity > 0.70
        )

        if top_similarity >= embedding_threshold:
            if ambiguous:
                confidence = top_similarity * 0.75
            else:
                confidence = top_similarity * 0.9
            return (
                best["l1_name"],
                best["l2_name"],
                None,
                best["unspsc_segment_code"],
                confidence,
                CategoryMethod.EMBEDDING.value,
                evidence,
            )

        # Below threshold
        return (None, None, None, None, top_similarity, "EMBEDDING_REJECT", evidence)

    # ── Batch classify ────────────────────────────────────────────────────

    def classify_batch(
        self,
        df: pd.DataFrame,
        config,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Classify a DataFrame of unclassified transactions.

        Args:
            df: DataFrame of transactions to classify (not yet classified by passes 0-3).
            config: SpendCube Config object.

        Returns:
            (classified_df, unclassified_df) — unclassified = rows where
            category_confidence < config.categorisation.confidence_medium.
        """
        confidence_medium = getattr(
            getattr(config, "categorisation", None), "confidence_medium", 0.60
        )

        if df.empty:
            return pd.DataFrame(columns=df.columns), df.copy()

        if not self._available or self._category_embeddings is None:
            self.logger.warning(
                "sentence-transformers unavailable — passing all rows to LLM fallback"
            )
            return pd.DataFrame(columns=df.columns), df.copy()

        # Ensure output columns exist
        df = df.copy()
        for col in (
            "category_l1", "category_l2", "category_l3",
            "unspsc_code", "category_confidence", "category_method", "category_evidence",
        ):
            if col not in df.columns:
                df[col] = None

        classified_mask = pd.Series(False, index=df.index)

        for idx in df.index:
            desc = ""
            if "cleaned_description" in df.columns and pd.notna(df.at[idx, "cleaned_description"]):
                desc = str(df.at[idx, "cleaned_description"])
            elif "raw_line_description" in df.columns and pd.notna(df.at[idx, "raw_line_description"]):
                desc = str(df.at[idx, "raw_line_description"])

            l1, l2, l3, unspsc, confidence, method, evidence = self.classify(desc, config)

            df.at[idx, "category_l1"] = l1
            df.at[idx, "category_l2"] = l2
            df.at[idx, "category_l3"] = l3
            df.at[idx, "unspsc_code"] = unspsc
            df.at[idx, "category_confidence"] = confidence
            df.at[idx, "category_method"] = method
            if "category_evidence" in df.columns:
                df.at[idx, "category_evidence"] = evidence

            if confidence >= confidence_medium:
                classified_mask.at[idx] = True

        classified = df[classified_mask].copy()
        unclassified = df[~classified_mask].copy()
        self.logger.info(
            f"Pass 4 (embedding): {len(classified)} classified, "
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

    categoriser = EmbeddingCategoriser(
        hierarchy_path=hierarchy_path,
        cache_path="data/cache/category_embeddings.pkl",
        config=config,
    )

    sample_descriptions = [
        "Office supplies - toner cartridges HP",
        "Catering - Q1 events",
        "International freight - Shanghai to Melbourne",
        "Mobile fleet management - Feb 2024",
        "Software licence renewal - Microsoft Azure",
        "Legal advisory fees",
        "Staff recruitment agency fees",
        "Cleaning and janitorial services",
        "Electricity and gas utilities",
        "Management consulting services",
    ]

    print(f"\nEmbedding classifier — top-3 category matches per description")
    print("=" * 70)

    if not categoriser._available or categoriser._category_embeddings is None:
        print("WARNING: sentence-transformers not available. Cannot run demo.")
    else:
        for desc in sample_descriptions:
            desc_embedding = categoriser._model.encode([desc], show_progress_bar=False)[0]
            similarities = categoriser._cosine_similarity(
                desc_embedding, categoriser._category_embeddings
            )
            top_indices = np.argsort(similarities)[::-1][:3]

            print(f"\n  Description: '{desc}'")
            for rank, idx in enumerate(top_indices, 1):
                cat = categoriser._categories[idx]
                sim = float(similarities[idx])
                print(
                    f"    #{rank}: {cat['l1_name']}/{cat['l2_name']} "
                    f"(cosine={sim:.3f})"
                )

            # Full classify result
            l1, l2, l3, unspsc, conf, method, evidence = categoriser.classify(desc, config)
            print(f"    → classify(): l1={l1} l2={l2} conf={conf:.3f} method={method}")
