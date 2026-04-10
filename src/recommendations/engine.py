"""SpendCube recommendation engine orchestrator.

Wires together: SpendCubeBuilder → CubeMetrics → RecommendationRules →
NarrativeGenerator → JSON export.

JSON schema for each recommendation:
    type (str): recommendation type constant
    context (str): category name or supplier name
    evidence (str): human-readable supporting evidence
    estimated_impact_aud (float): estimated annual saving in AUD
    confidence (str): 'HIGH' | 'MEDIUM' | 'LOW'
    action (str): recommended procurement action
    lever (str): savings lever category
    narrative (str | None): LLM-generated consulting narrative (None when dry_run=true)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

# Ensure project root is on sys.path when run as a script.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import load_config
from src.cube.builder import SpendCubeBuilder
from src.cube.metrics import CubeMetrics
from src.models.database import get_engine
from src.recommendations.narratives import NarrativeGenerator
from src.recommendations.rules import RecommendationRules
from src.utils.logging import get_logger_from_config

_DATAFRAME_COLUMNS = [
    "type",
    "context",
    "evidence",
    "estimated_impact_aud",
    "confidence",
    "action",
    "lever",
    "narrative",
]


class RecommendationEngine:
    """Orchestrate the full recommendations pipeline.

    Args:
        config: SpendCube Config object.
        engine: SQLAlchemy engine connected to the SpendCube database.
    """

    def __init__(self, config, engine) -> None:
        self.config = config
        self.engine = engine
        self.logger = get_logger_from_config(__name__, config)

        self._cube_builder = SpendCubeBuilder(config, engine)
        self._narrative_generator = NarrativeGenerator(config)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self) -> list[dict]:
        """Run the full recommendations pipeline.

        Steps:
        1. Build spend cube (SpendCubeBuilder.build).
        2. Compute KPI metrics (CubeMetrics.compute_all).
        3. Generate rule-based recommendations (RecommendationRules.generate_all).
        4. Optionally enrich with LLM narratives (NarrativeGenerator.enrich).

        Returns:
            List of recommendation dicts sorted by estimated_impact_aud descending.
        """
        self.logger.info("Starting recommendation engine")

        cube = self._cube_builder.build()
        self.logger.info("Cube built — %d transaction rows", len(cube.get("transactions", pd.DataFrame())))

        metrics_obj = CubeMetrics(cube, self.config)
        metrics = metrics_obj.compute_all()
        self.logger.info("Metrics computed — total_spend=%.2f", metrics.get("total_spend", 0.0))

        rules = RecommendationRules(cube, metrics, self.config)
        recommendations = rules.generate_all()
        self.logger.info("Rules generated %d recommendation(s)", len(recommendations))

        recommendations = self._narrative_generator.enrich(recommendations)
        self.logger.info("Narrative enrichment complete")

        # Ensure stable sort by impact descending (enrich may reorder).
        recommendations.sort(
            key=lambda r: r.get("estimated_impact_aud", 0.0), reverse=True
        )
        return recommendations

    def export(
        self,
        recommendations: list[dict],
        path: str = "data/output/recommendations.json",
    ) -> str:
        """Save recommendations to JSON and return the path.

        Args:
            recommendations: List of recommendation dicts.
            path: Output file path (default: data/output/recommendations.json).

        Returns:
            Absolute path to the written file.
        """
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding="utf-8") as fh:
            json.dump(recommendations, fh, indent=2, default=str)

        self.logger.info("Recommendations exported to %s (%d items)", output_path, len(recommendations))
        return str(output_path)

    def to_dataframe(self, recommendations: list[dict]) -> pd.DataFrame:
        """Convert recommendations list to a DataFrame.

        Args:
            recommendations: List of recommendation dicts.

        Returns:
            DataFrame with columns: type, context, evidence,
            estimated_impact_aud, confidence, action, lever, narrative.
        """
        if not recommendations:
            return pd.DataFrame(columns=_DATAFRAME_COLUMNS)

        rows = []
        for rec in recommendations:
            rows.append({col: rec.get(col) for col in _DATAFRAME_COLUMNS})

        return pd.DataFrame(rows, columns=_DATAFRAME_COLUMNS)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_recommendations(recommendations: list[dict]) -> None:
    if not recommendations:
        print("No recommendations generated.")
        return

    total_impact = sum(r.get("estimated_impact_aud", 0.0) for r in recommendations)

    print(f"\n{'=' * 80}")
    print(f"  SpendCube Recommendations  ({len(recommendations)} generated)")
    print(f"{'=' * 80}")
    print(f"  Total identified savings opportunity: ${total_impact:,.0f} AUD")
    print(f"{'=' * 80}\n")

    for i, rec in enumerate(recommendations, 1):
        impact = rec.get("estimated_impact_aud", 0.0)
        conf = rec.get("confidence", "N/A")
        print(f"#{i:02d}  [{rec.get('type', 'UNKNOWN')}]  {rec.get('context', '')}")
        print(f"     Impact:    ${impact:,.0f} AUD  |  Confidence: {conf}")
        print(f"     Evidence:  {rec.get('evidence', '')}")
        print(f"     Action:    {rec.get('action', '')}")
        print(f"     Lever:     {rec.get('lever', '')}")
        narrative = rec.get("narrative")
        if narrative:
            print(f"     Narrative: {narrative}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run SpendCube recommendation engine"
    )
    parser.add_argument("--db", required=True, help="Path to SQLite database file")
    parser.add_argument(
        "--config", default="config.yaml", help="Path to config.yaml"
    )
    parser.add_argument(
        "--export",
        default="data/output/recommendations.json",
        help="Output JSON path (default: data/output/recommendations.json)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    db_engine = get_engine(args.db)

    eng = RecommendationEngine(config, db_engine)
    recs = eng.run()

    output_path = eng.export(recs, args.export)
    print(f"\nExported {len(recs)} recommendation(s) to {output_path}")

    _print_recommendations(recs)
