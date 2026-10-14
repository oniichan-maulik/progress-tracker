"""App settings, read from environment variables first, then Streamlit secrets."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_URL = f"sqlite:///{(PROJECT_ROOT / 'data' / 'progress.db').as_posix()}"


def _secret(name: str):
    try:
        import streamlit as st

        return st.secrets.get(name)
    except Exception:  # no secrets.toml, or not running under Streamlit
        return None


def get_setting(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name) or _secret(name) or default


def database_url() -> str:
    url = get_setting("DATABASE_URL", DEFAULT_DB_URL)
    # Supabase/Heroku style URLs use "postgres://", which SQLAlchemy no longer accepts.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def org_name() -> str:
    return get_setting("ORG_NAME", "My Organization")
