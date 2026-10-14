"""App settings, read from environment variables first, then Streamlit secrets."""

import os
from pathlib import Path
from urllib.parse import quote, unquote

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


def normalize_db_url(url: str) -> str:
    """Make a pasted Postgres URL usable by SQLAlchemy.

    - "postgres://" / "postgresql://" -> "postgresql+psycopg2://" (the driver we ship)
    - URL-encodes the password, so passwords containing @ # / : ? % work as pasted
    """
    url = url.strip()
    scheme, sep, rest = url.partition("://")
    if not sep or scheme not in ("postgres", "postgresql"):
        return url
    creds, at, host = rest.rpartition("@")
    if at and ":" in creds:
        user, _, password = creds.partition(":")
        rest = f"{user}:{quote(unquote(password), safe='')}@{host}"
    return f"postgresql+psycopg2://{rest}"


def database_url() -> str:
    return normalize_db_url(get_setting("DATABASE_URL", DEFAULT_DB_URL))


def org_name() -> str:
    return get_setting("ORG_NAME", "My Organization")
