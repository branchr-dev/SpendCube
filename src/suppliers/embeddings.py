"""SpendCube supplier embedding generation via sentence-transformers.

Stage 4 of the 5-stage supplier harmonisation pipeline. Uses sentence-transformer
embeddings and cosine similarity to match suppliers not resolved by deterministic
or fuzzy matching. Caches embeddings to disk to avoid recomputation.
"""

from __future__ import annotations

import json
import logging
import pickle
import sys
from pathlib import Path
from typing import Optional

import numpy as np

# Ensure project root is on sys.path when run as a script.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
    _SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    _SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning(
        "sentence-transformers not installed — EmbeddingMatcher will return "
        "EMBEDDING_UNAVAILABLE for all queries. Install with: "
        "pip install sentence-transformers"
    )


# ---------------------------------------------------------------------------
# Pgvector Embedding Store
# ---------------------------------------------------------------------------

class PgvectorEmbeddingStore:
    """Persistent embedding cache backed by the supplier_embeddings Postgres table."""

    _CHUNK_SIZE = 500

    def __init__(self, engine, engagement_id: str) -> None:
        self._engine = engine
        self._engagement_id = engagement_id
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        """Return True only if engine is Postgres and the pgvector extension is present."""
        if self._available is not None:
            return self._available
        if "postgresql" not in str(self._engine.url):
            self._available = False
            return False
        try:
            from sqlalchemy import text
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1::vector"))
            self._available = True
        except Exception:
            self._available = False
        return self._available

    def get(self, names: list[str]) -> dict[str, np.ndarray]:
        """Query supplier_embeddings for the given names and return name -> vector dict."""
        if not names:
            return {}
        from sqlalchemy import text
        placeholders = ", ".join(f":n{i}" for i in range(len(names)))
        params = {f"n{i}": name for i, name in enumerate(names)}
        params["engagement_id"] = self._engagement_id
        sql = text(
            f"SELECT normalised_name, embedding FROM supplier_embeddings "
            f"WHERE engagement_id = :engagement_id AND normalised_name IN ({placeholders})"
        )
        result: dict[str, np.ndarray] = {}
        with self._engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        for row in rows:
            raw = row[1]
            if isinstance(raw, str):
                vec = np.array(json.loads(raw), dtype=np.float32)
            else:
                vec = np.array(raw, dtype=np.float32)
            result[row[0]] = vec
        return result

    def store(self, name_vector_pairs: list[tuple[str, np.ndarray]]) -> None:
        """Upsert name-vector pairs to supplier_embeddings in chunks of 500."""
        if not name_vector_pairs:
            return
        from sqlalchemy import text
        for i in range(0, len(name_vector_pairs), self._CHUNK_SIZE):
            chunk = name_vector_pairs[i : i + self._CHUNK_SIZE]
            with self._engine.begin() as conn:
                for name, vec in chunk:
                    vec_str = "[" + ",".join(str(float(v)) for v in vec) + "]"
                    conn.execute(
                        text(
                            "INSERT INTO supplier_embeddings "
                            "(id, engagement_id, normalised_name, embedding) "
                            "VALUES (gen_random_uuid(), :engagement_id, :name, :embedding::vector) "
                            "ON CONFLICT (engagement_id, normalised_name) DO NOTHING"
                        ),
                        {
                            "engagement_id": self._engagement_id,
                            "name": name,
                            "embedding": vec_str,
                        },
                    )


# ---------------------------------------------------------------------------
# Stage 4 — Embedding Matcher
# ---------------------------------------------------------------------------

class EmbeddingMatcher:
    """
    Stage 4 of the supplier harmonisation pipeline.

    Uses sentence-transformer embeddings and cosine similarity to match
    suppliers not resolved by deterministic or fuzzy matching.
    Embeddings are cached to disk to avoid recomputation on repeated runs.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        cache_path: str = "data/cache/supplier_embeddings.pkl",
        pgvector_store: Optional[PgvectorEmbeddingStore] = None,
    ) -> None:
        """
        Load sentence-transformers model and initialise embedding cache.

        Args:
            model_name:      Sentence-transformer model to use.
            cache_path:      Path to pickle file for persisting embedding cache.
            pgvector_store:  Optional pgvector-backed store. When provided and
                             available, used as primary cache instead of pickle.
        """
        self._cache_path = Path(cache_path)
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._pgvector_store = pgvector_store

        # Load disk cache if it exists
        self._cache: dict[str, np.ndarray] = {}
        if self._cache_path.exists():
            try:
                with open(self._cache_path, "rb") as fh:
                    loaded = pickle.load(fh)
                if isinstance(loaded, dict):
                    self._cache = loaded
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to load embedding cache from %s: %s", self._cache_path, exc)

        self._model: Optional[object] = None
        if _SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                self._model = SentenceTransformer(model_name)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to load sentence-transformers model %r: %s", model_name, exc)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _save_cache(self) -> None:
        """Persist the in-memory embedding cache to disk."""
        try:
            with open(self._cache_path, "wb") as fh:
                pickle.dump(self._cache, fh)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to save embedding cache to %s: %s", self._cache_path, exc)

    def _unavailable_result(self) -> tuple[None, float, str, str]:
        return (None, 0.0, "EMBEDDING_UNAVAILABLE", "sentence-transformers not installed")

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def encode(self, names: list[str]) -> np.ndarray:
        """
        Encode a list of normalised supplier names to embedding vectors.

        Checks the disk-backed cache first. Encodes only uncached names in
        batch, then updates and saves the cache.

        Args:
            names: List of normalised supplier name strings.

        Returns:
            2-D numpy array of shape (len(names), embedding_dim).

        Raises:
            RuntimeError: If sentence-transformers is not available.
        """
        if not _SENTENCE_TRANSFORMERS_AVAILABLE or self._model is None:
            raise RuntimeError("sentence-transformers is not available")

        use_pgvector = (
            self._pgvector_store is not None
            and self._pgvector_store.is_available()
        )

        if use_pgvector:
            # Populate in-memory cache from pgvector for names not already present.
            pg_missing = [n for n in names if n not in self._cache]
            if pg_missing:
                pg_hits = self._pgvector_store.get(pg_missing)
                self._cache.update(pg_hits)

        uncached = [n for n in names if n not in self._cache]
        if uncached:
            vectors = self._model.encode(uncached, convert_to_numpy=True)
            for name, vec in zip(uncached, vectors):
                self._cache[name] = vec
            if use_pgvector:
                self._pgvector_store.store(list(zip(uncached, vectors)))
            self._save_cache()

        return np.array([self._cache[n] for n in names])

    def match(
        self,
        query_name: str,
        candidate_names: list[str],
        candidate_ids: list[str],
        config,
    ) -> tuple[str | None, float, str, str]:
        """
        Match a single query supplier name against a list of candidates.

        Args:
            query_name:      Normalised name of the supplier to match.
            candidate_names: Normalised names of canonical supplier master entries.
            candidate_ids:   Corresponding canonical_supplier_id values.
            config:          Project Config; reads config.supplier_matching thresholds.

        Returns:
            (canonical_supplier_id, confidence, method, evidence) where method is
            EMBEDDING_AUTO, EMBEDDING_REVIEW, EMBEDDING_REJECT, or EMBEDDING_UNAVAILABLE.
        """
        if not _SENTENCE_TRANSFORMERS_AVAILABLE or self._model is None:
            return self._unavailable_result()

        if not candidate_names:
            return (None, 0.0, "EMBEDDING_REJECT", "no candidates")

        sm = config.supplier_matching
        auto_threshold: float = sm.embedding_auto_threshold
        review_threshold: float = sm.embedding_review_threshold

        all_names = [query_name] + candidate_names
        embeddings = self.encode(all_names)

        query_vec = embeddings[0]
        candidate_vecs = embeddings[1:]

        # Cosine similarity: dot product of normalised vectors
        query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
        candidate_norms = candidate_vecs / (
            np.linalg.norm(candidate_vecs, axis=1, keepdims=True) + 1e-10
        )
        similarities = candidate_norms @ query_norm

        best_idx = int(np.argmax(similarities))
        top_similarity = float(similarities[best_idx])
        best_candidate = candidate_names[best_idx]
        best_id = candidate_ids[best_idx]

        evidence = f"cosine_similarity={top_similarity:.3f} matched={best_candidate}"

        if top_similarity >= auto_threshold:
            return (best_id, top_similarity * 0.95, "EMBEDDING_AUTO", evidence)
        elif top_similarity >= review_threshold:
            return (best_id, top_similarity * 0.85, "EMBEDDING_REVIEW", evidence)
        else:
            return (None, top_similarity, "EMBEDDING_REJECT", evidence)

    def match_batch(
        self,
        query_names: list[str],
        candidate_names: list[str],
        candidate_ids: list[str],
        config,
    ) -> list[tuple]:
        """
        Batch-match multiple query names against the same candidate set.

        More efficient than calling match() in a loop because all embeddings
        (queries + candidates) are encoded in a single model pass.

        Args:
            query_names:     Normalised names of suppliers to match.
            candidate_names: Normalised names of canonical supplier master entries.
            candidate_ids:   Corresponding canonical_supplier_id values.
            config:          Project Config; reads config.supplier_matching thresholds.

        Returns:
            List of (canonical_supplier_id, confidence, method, evidence) tuples,
            one per entry in query_names.
        """
        if not _SENTENCE_TRANSFORMERS_AVAILABLE or self._model is None:
            return [self._unavailable_result() for _ in query_names]

        if not candidate_names:
            return [
                (None, 0.0, "EMBEDDING_REJECT", "no candidates")
                for _ in query_names
            ]

        sm = config.supplier_matching
        auto_threshold: float = sm.embedding_auto_threshold
        review_threshold: float = sm.embedding_review_threshold

        # Encode all unique names in one pass
        all_names = query_names + candidate_names
        embeddings = self.encode(all_names)

        query_vecs = embeddings[: len(query_names)]
        candidate_vecs = embeddings[len(query_names):]

        # Normalise for cosine similarity
        query_norms = query_vecs / (
            np.linalg.norm(query_vecs, axis=1, keepdims=True) + 1e-10
        )
        candidate_norms = candidate_vecs / (
            np.linalg.norm(candidate_vecs, axis=1, keepdims=True) + 1e-10
        )

        # similarity matrix: shape (n_queries, n_candidates)
        sim_matrix = query_norms @ candidate_norms.T

        results = []
        for i, query_name in enumerate(query_names):
            similarities = sim_matrix[i]
            best_idx = int(np.argmax(similarities))
            top_similarity = float(similarities[best_idx])
            best_candidate = candidate_names[best_idx]
            best_id = candidate_ids[best_idx]

            evidence = f"cosine_similarity={top_similarity:.3f} matched={best_candidate}"

            if top_similarity >= auto_threshold:
                results.append((best_id, top_similarity * 0.95, "EMBEDDING_AUTO", evidence))
            elif top_similarity >= review_threshold:
                results.append((best_id, top_similarity * 0.85, "EMBEDDING_REVIEW", evidence))
            else:
                results.append((None, top_similarity, "EMBEDDING_REJECT", evidence))

        return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("EmbeddingMatcher — Acme Variant Similarity Matrix\n")

    if not _SENTENCE_TRANSFORMERS_AVAILABLE:
        print("ERROR: sentence-transformers not installed.")
        print("Install with: pip install sentence-transformers")
        sys.exit(1)

    matcher = EmbeddingMatcher()

    acme_variants = [
        "acme",           # normalised form of "Acme Pty Ltd"
        "acme",           # normalised form of "ACME PTY LIMITED"
        "acme",           # normalised form of "acme p/l"
        "sodexo australia",  # normalised form of "SODEXO AUSTRALIA"
        "sodexo australia",  # normalised form of "Sodexo Aust P/L"
        "dhl express",
        "telstra",
        "intercompany legal",
    ]

    # De-duplicate for encoding
    unique_names = list(dict.fromkeys(acme_variants))
    print(f"Encoding {len(unique_names)} unique supplier names...")
    embeddings = matcher.encode(unique_names)

    # Compute full cosine similarity matrix
    norms = embeddings / (np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-10)
    sim_matrix = norms @ norms.T

    header = f"{'':25}" + "".join(f"{n[:14]:>16}" for n in unique_names)
    print(header)
    print("-" * (25 + 16 * len(unique_names)))
    for i, row_name in enumerate(unique_names):
        row_vals = "".join(f"{sim_matrix[i, j]:>16.3f}" for j in range(len(unique_names)))
        print(f"{row_name:<25}{row_vals}")

    print()
    print("Embedding cache saved to:", matcher._cache_path)
    print()
    print("PASS  EmbeddingMatcher operational.")
    sys.exit(0)
