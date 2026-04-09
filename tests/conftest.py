"""SpendCube pytest configuration and shared fixtures."""

import sys
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine

# Ensure project root is on sys.path so src.* imports work from tests/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import load_config
from src.models.database import init_db


@pytest.fixture
def config():
    """Load config from config.yaml at the project root."""
    return load_config(str(_PROJECT_ROOT / "config.yaml"))


@pytest.fixture
def sample_df():
    """Return the 10-row messy sample dataset as a DataFrame.

    Column names match data/input/sample.csv exactly (raw source names).
    """
    return pd.read_csv(str(_PROJECT_ROOT / "data" / "input" / "sample.csv"))


@pytest.fixture
def in_memory_engine():
    """Return an in-memory SQLite engine with all tables initialised via init_db()."""
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    return engine
