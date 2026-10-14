"""Entry point: first-run setup, login, and role-based navigation."""

import time

import streamlit as st

from core import services as svc
from core.auth import authenticate
from core.config import org_name
from core.db import get_session
from core.models import ROLE_ADMIN
from views import assign_tasks, manage_users, my_report, team_review
from views.common import current_user, flash, login, logout, show_flash
from views.ui import brand, hide_sidebar, inject_css, page_header, sidebar_logo, user_card

st.set_page_config(page_title=f"{org_name()} · Progress Reports", page_icon=":material/insights:", layout="wide")


def first_run_setup() -> None:
    page_header("Create the admin account", f"No admin exists yet for {org_name()}. The first account you create here manages everyone else.", "First-run setup")
    with st.form("setup"):
        full_name = st.text_input("Full name")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        confirm = st.text_input("Confirm password", type="password")
        if st.form_submit_button("Create admin account", type="primary"):
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
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        st.write("")
        brand(org_name())
        page_header("Sign in", "Use the username and password your admin gave you.", "Progress reports")
        with st.form("login"):
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

    sidebar_logo(org_name())
    with st.sidebar:
        user_card(user.full_name, user.username, user.role)
        if st.button("Sign out", icon=":material/logout:", width="stretch"):
            logout()
            flash("You've been signed out.", ":material/logout:")
            st.rerun()

    if user.is_admin:
        pages = [
            st.Page(team_review.page, title="Team review", icon=":material/groups:", url_path="team", default=True),
            st.Page(assign_tasks.page, title="Assign tasks", icon=":material/assignment_add:", url_path="assign"),
            st.Page(manage_users.page, title="Manage users", icon=":material/manage_accounts:", url_path="users"),
        ]
    else:
        pages = [st.Page(my_report.page, title="My report", icon=":material/table_view:", url_path="report", default=True)]

    show_flash()
    st.navigation(pages).run()


main()
