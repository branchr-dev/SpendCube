"""SpendCube configuration loader."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, Optional

import yaml
from pydantic import BaseModel


REQUIRED_SECTIONS = [
    "paths", "llm", "supplier_matching", "categorisation",
    "spend_cube", "recommendations", "logging", "column_mappings",
]


class ConfigError(Exception):
    pass


class PathsConfig(BaseModel):
    data_dir: str
    input_dir: str
    output_dir: str
    db_path: str
    reference_dir: str


class LLMConfig(BaseModel):
    model: str
    batch_size: int
    dry_run: bool
    max_cost_usd: float
    api_key_env: str


class SupplierMatchingConfig(BaseModel):
    fuzzy_auto_threshold: int
    fuzzy_review_threshold: int
    embedding_auto_threshold: float
    embedding_review_threshold: float
    corroboration_same_city: int
    corroboration_same_postcode: int
    corroboration_same_abn: int


class CategorisationConfig(BaseModel):
    confidence_high: float
    confidence_medium: float
    embedding_threshold: float
    llm_fallback_threshold: float


class SpendCubeConfig(BaseModel):
    base_currency: str
    tail_spend_supplier_pct: float
    tail_spend_value_pct: float


class RecommendationsConfig(BaseModel):
    consolidation_threshold: int
    consolidation_saving_pct: float
    target_payment_days: int
    wacc: float
    min_wc_opportunity: int
    tail_spend_alert_pct: float
    maverick_alert_pct: float
    addressability_defaults: Dict[str, float]
    competitive_tender_min_spend: float
    contract_coverage_gap_min_spend: float


class LoggingConfig(BaseModel):
    level: str
    json_format: bool


class Config(BaseModel):
    paths: PathsConfig
    llm: LLMConfig
    supplier_matching: SupplierMatchingConfig
    categorisation: CategorisationConfig
    spend_cube: SpendCubeConfig
    recommendations: RecommendationsConfig
    logging: LoggingConfig
    column_mappings: Dict[str, Dict[str, str]]


def load_config(path: str = "config.yaml") -> Config:
    """Load and validate config.yaml, resolving relative paths to absolute."""
    config_path = Path(path).resolve()

    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ConfigError(f"Config file is not a valid YAML mapping: {config_path}")

    missing = [s for s in REQUIRED_SECTIONS if s not in raw]
    if missing:
        raise ConfigError(
            f"Config is missing required sections: {', '.join(missing)}"
        )

    # Resolve relative paths to absolute, anchored at the config file's directory
    base_dir = config_path.parent
    paths = raw["paths"]
    for key in ("data_dir", "input_dir", "output_dir", "db_path", "reference_dir"):
        if key in paths and not Path(paths[key]).is_absolute():
            paths[key] = str(base_dir / paths[key])

    return Config(**raw)


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    try:
        config = load_config(config_path)
    except ConfigError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Print as formatted YAML with all sections visible
    print(yaml.dump(config.model_dump(), default_flow_style=False, sort_keys=False))
