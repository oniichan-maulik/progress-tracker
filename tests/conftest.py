import os

import pytest
import streamlit.config
from sqlalchemy.orm import sessionmaker

import core.db
from core.config import database_url
from core.db import init_db, make_engine
from core.models import ROLE_ADMIN, ROLE_EMPLOYEE
from core.services import create_user

# Never load real secrets in tests. Streamlit copies secrets.toml values into
# os.environ, which would point the app at a real (e.g. Supabase) database.
streamlit.config.set_option("secrets.files", [])
for key in ("DATABASE_URL", "ORG_NAME"):
    os.environ.pop(key, None)


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    """Every test gets a throwaway SQLite file; fail loudly if anything else is configured."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'isolated.db').as_posix()}")
    core.db._default_sessionmaker.cache_clear()
    assert database_url().startswith("sqlite:///"), "tests must never use a real database"
    yield
    core.db._default_sessionmaker.cache_clear()


@pytest.fixture
def session():
    engine = make_engine("sqlite:///:memory:")
    init_db(engine)
    with sessionmaker(engine, expire_on_commit=False)() as s:
        yield s


@pytest.fixture
def admin(session):
    return create_user(session, "boss", "Bea Boss", "adminpass1", ROLE_ADMIN)


@pytest.fixture
def alice(session):
    return create_user(session, "alice", "Alice Archer", "alicepass1", ROLE_EMPLOYEE)


@pytest.fixture
def bob(session):
    return create_user(session, "bob", "Bob Baker", "bobpass12", ROLE_EMPLOYEE)
