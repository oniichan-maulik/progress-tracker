"""Smoke tests: every page renders without errors against a seeded demo database."""

import random
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from streamlit.testing.v1 import AppTest

import core.db
from core.models import User
from scripts.seed_demo import PASSWORD, seed

TIMEOUT = 60
APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def db_url(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    core.db._default_sessionmaker.cache_clear()
    yield url
    core.db._default_sessionmaker.cache_clear()


@pytest.fixture
def seeded(db_url):
    with core.db.get_session() as s:
        seed(s, date.today(), random.Random(1))
        return {u.username: u.id for u in s.scalars(select(User))}


def _assert_ok(at: AppTest) -> None:
    assert not at.exception, [e.value for e in at.exception]


def _header(at: AppTest) -> str:
    """Text of the gradient page header."""
    return next(m.value for m in at.markdown if "pt-header" in m.value)


def test_first_run_creates_admin(db_url):
    at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    _assert_ok(at)
    assert "Create the admin account" in _header(at)
    at.text_input[0].input("Ada Admin")
    at.text_input[1].input("ada")
    at.text_input[2].input("supersecret")
    at.text_input[3].input("supersecret")
    at.button[0].click().run()
    _assert_ok(at)
    assert "Team review" in _header(at)


@pytest.mark.parametrize("username,title", [("admin", "Team review"), ("priya", "My report")])
def test_login_lands_on_role_home(seeded, username, title):
    at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    at.text_input[0].input(username)
    at.text_input[1].input(PASSWORD)
    at.button[0].click().run()
    _assert_ok(at)
    assert title in _header(at)


def test_wrong_password_rejected(seeded):
    at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    at.text_input[0].input("admin")
    at.text_input[1].input("wrong-password")
    at.button[0].click().run()
    assert at.error and "Incorrect" in at.error[0].value


@pytest.mark.parametrize(
    "module,username", [("team_review", "admin"), ("assign_tasks", "admin"), ("manage_users", "admin"), ("my_report", "rahul"), ("my_report", "priya")]
)
def test_pages_render(seeded, module, username):
    at = AppTest.from_string(f"from views import {module}\n{module}.page()", default_timeout=TIMEOUT)
    at.session_state["user_id"] = seeded[username]
    at.run()
    _assert_ok(at)


def test_grid_change_detection():
    import pandas as pd

    from views.my_report import _collect_changes

    d1, d2 = date(2026, 10, 5), date(2026, 10, 6)
    original = pd.DataFrame(
        [
            {"id": 1, "Date": d1, "Task": "Keep", "Status": "In Progress", "Hours": None, "Notes": ""},
            {"id": 2, "Date": d1, "Task": "Edit me", "Status": "In Progress", "Hours": 1.0, "Notes": ""},
        ]
    )
    edited = pd.DataFrame(
        [
            {"id": 1, "Date": d1, "Task": "Keep", "Status": "In Progress", "Hours": float("nan"), "Notes": ""},
            {"id": 2, "Date": "2026-10-06", "Task": "Edit me", "Status": "Completed", "Hours": 2.5, "Notes": "x"},
            {"id": None, "Date": None, "Task": "Brand new", "Status": None, "Hours": None, "Notes": None},
            {"id": None, "Date": d2, "Task": "  ", "Status": "Not Started", "Hours": None, "Notes": None},
        ]
    )
    added, updated = _collect_changes(original, edited, default_date=d2)
    assert updated == {2: {"work_date": d2, "title": "Edit me", "status": "Completed", "hours": 2.5, "notes": "x"}}
    assert added == [{"work_date": d2, "title": "Brand new", "status": "Not Started", "hours": None, "notes": ""}]


def test_sign_out_hides_sidebar(seeded):
    at = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    assert not at.sidebar.button  # signed out: nothing in the sidebar
    at.text_input[0].input("admin")
    at.text_input[1].input(PASSWORD)
    at.button[0].click().run()
    assert at.sidebar.button[0].label == "Sign out"

    at.sidebar.button[0].click().run()
    _assert_ok(at)
    assert "Sign in" in _header(at)
    assert not at.sidebar.button and not at.sidebar.markdown
    assert any('data-testid="stSidebar"' in h.proto.body for h in at.get("html"))
    assert "user_id" not in at.session_state
