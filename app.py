"""Entry point: first-run setup, login, and role-based navigation."""

import time

import streamlit as st

from core import services as svc
from core.auth import authenticate
from core.config import org_name
from core.db import get_session
from core.models import ROLE_ADMIN
from views import account, assign_tasks, manage_users, my_report, team_review
from views.common import current_user, flash, login, logout, show_flash
from views.ui import brand, card, hide_sidebar, inject_css, nav_label, user_card

st.set_page_config(page_title=f"{org_name()} · Progress Reports", page_icon=":material/insights:", layout="wide")


def _auth_shell(title: str, subtitle: str):
    """Centered card used by sign-in and first-run setup."""
    _, center, _ = st.columns([1, 1.1, 1])
    with center:
        st.markdown('<div class="pt-login"></div>', unsafe_allow_html=True)
        brand(org_name())
        st.write("")
        box = card("auth")
        with box:
            # page_header's marker class keeps the title findable in tests.
            st.markdown(
                f'<div class="pt-header"><div class="pt-header-title">{title}</div>'
                f'<div class="pt-header-sub">{subtitle}</div></div>',
                unsafe_allow_html=True,
            )
        return box


def first_run_setup() -> None:
    box = _auth_shell(
        "Create the admin account",
        f"No admin exists yet for {org_name()}. The first account created here manages everyone else.",
    )
    with box, st.form("setup", border=False):
        full_name = st.text_input("Full name")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        confirm = st.text_input("Confirm password", type="password")
        if st.form_submit_button("Create admin account", type="primary", width="stretch"):
            if password != confirm:
                st.error("Passwords don't match.")
                return
            try:
                with get_session() as s:
                    if svc.has_admin(s):  # someone else finished setup first
                        st.rerun()
                    user = svc.create_user(s, username, full_name, password, ROLE_ADMIN)
                login(user)
                st.rerun()
            except svc.ServiceError as e:
                st.error(str(e))


def login_page() -> None:
    box = _auth_shell("Sign in", "Use the username and password your admin gave you.")
    with box, st.form("login", border=False):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in", type="primary", width="stretch"):
            with get_session() as s:
                user = authenticate(s, username, password)
            if user:
                login(user)
                st.rerun()
            time.sleep(1)  # slow down password guessing
            st.error("Incorrect username or password, or the account is inactive.")


def _sidebar(user, sections: dict[str, list]) -> None:
    with st.sidebar:
        brand(org_name())
        for label, pages in sections.items():
            nav_label(label)
            for page in pages:
                st.page_link(page)
        with st.container(key="sidebar_account"):
            user_card(user.full_name, user.username, user.role)
            if st.button("Sign out", icon=":material/logout:", width="stretch"):
                logout()
                flash("You've been signed out.", ":material/logout:")
                st.rerun()


def main() -> None:
    inject_css()
    with get_session() as s:
        needs_setup = not svc.has_admin(s)
    user = None if needs_setup else current_user()

    if user is None:
        # Signed out: a single hidden page, so no sidebar or menu and no
        # reachable app pages (any URL falls back to sign-in).
        hide_sidebar()
        show_flash()
        entry = first_run_setup if needs_setup else login_page
        st.navigation([st.Page(entry, title="Sign in", url_path="login", default=True)], position="hidden").run()
        return

    report = st.Page(my_report.page, title="My report", icon=":material/table_view:", url_path="report",
                     default=not user.is_admin)
    my_account = st.Page(account.page, title="My account", icon=":material/account_circle:", url_path="account")
    if user.is_admin:
        sections = {
            "Team": [
                st.Page(team_review.page, title="Team review", icon=":material/space_dashboard:", url_path="team", default=True),
                st.Page(assign_tasks.page, title="Assign tasks", icon=":material/assignment_add:", url_path="assign"),
                st.Page(manage_users.page, title="Manage users", icon=":material/group:", url_path="users"),
            ],
            "Personal": [report, my_account],
        }
    else:
        sections = {"Workspace": [report, my_account]}

    pages = [p for group in sections.values() for p in group]
    nav = st.navigation(pages, position="hidden")
    _sidebar(user, sections)
    show_flash()
    nav.run()


main()
