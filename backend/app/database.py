import os
import sys

# Allow 'from src.models.database import ...' imports from the repo root
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


def get_db_url() -> str:
    url = os.getenv("SUPABASE_DATABASE_URL")
    if not url:
        raise RuntimeError("SUPABASE_DATABASE_URL environment variable is not set")
    return url


def get_engine() -> Engine:
    return create_engine(get_db_url(), pool_pre_ping=True)
