"""Client configuration helpers for dashboard pages.

Reads the 'client:' block from config.yaml and exposes clean helper functions.
All pages should import from here — never read config.yaml directly in a page file.

client_config.py must NOT import streamlit (it is called before st.set_page_config).
"""
from pathlib import Path

import pandas as pd
import yaml

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
_DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data" / "output"


def _load_config() -> dict:
    try:
        with open(_CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def get_client_name() -> str:
    """Return client.name from config.yaml. Returns empty string if missing or blank."""
    cfg = _load_config()
    return (cfg.get("client", {}).get("name") or "").strip()


def get_engagement_title() -> str:
    """Return client.engagement from config.yaml. Default: 'Procurement Spend Diagnostic'."""
    cfg = _load_config()
    return (cfg.get("client", {}).get("engagement") or "Procurement Spend Diagnostic").strip()


def get_currency_label() -> str:
    """Return client.currency_label from config.yaml.
    Falls back to spend_cube.base_currency, then 'AUD'."""
    cfg = _load_config()
    label = (cfg.get("client", {}).get("currency_label") or "").strip()
    if label:
        return label
    base = (cfg.get("spend_cube", {}).get("base_currency") or "").strip()
    return base if base else "AUD"


def get_page_header(page_title: str) -> str:
    """Return '{client_name} — {page_title}' if client name is set, else page_title."""
    client = get_client_name()
    if client:
        return f"{client} \u2014 {page_title}"
    return page_title


def get_data_freshness(data_dir: Path = None) -> str:
    """Return the most recent ingestion date formatted as 'DD Month YYYY'.

    Reads max(ingested_at) from transactions.parquet. Returns 'Unknown' on any error.
    """
    if data_dir is None:
        data_dir = _DEFAULT_DATA_DIR
    parquet_path = Path(data_dir) / "transactions.parquet"
    try:
        df = pd.read_parquet(parquet_path, columns=["ingested_at"])
        max_ts = pd.to_datetime(df["ingested_at"]).max()
        return max_ts.strftime("%-d %B %Y")
    except Exception:
        return "Unknown"
