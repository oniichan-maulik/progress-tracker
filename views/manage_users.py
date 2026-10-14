"""Admin view: create users, reset passwords, change roles, deactivate accounts."""

import pandas as pd
import streamlit as st

from core import services as svc
from core.auth import MIN_PASSWORD_LENGTH
from core.config import org_name
from core.db import get_session
from core.models import ROLE_EMPLOYEE, ROLES
from views.common import current_user, flash
from views.ui import page_header, section, stat_cards, style_table


def _create_form() -> None:
    with st.form("new_user", clear_on_submit=True):
        c1, c2 = st.columns(2)
        full_name = c1.text_input("Full name")
        username = c2.text_input("Username", help="Letters, numbers, '.' and '_'. Case-insensitive.")
        password = c1.text_input("Temporary password", type="password", help=f"At least {MIN_PASSWORD_LENGTH} characters.")
        role = c2.selectbox("Role", ROLES, index=ROLES.index(ROLE_EMPLOYEE), format_func=str.title)
        if st.form_submit_button("Create user", type="primary", icon=":material/person_add:"):
            try:
                with get_session() as s:
                    user = svc.create_user(s, username, full_name, password, role)
                flash(f"Created {user.full_name} (@{user.username}).")
                st.rerun()
            except svc.ServiceError as e:
                st.error(str(e))


def _edit_user(admin, user) -> None:
    def run(action, message):
        try:
            with get_session() as s:
                action(s)
            flash(message)
            st.rerun()
        except svc.ServiceError as e:
            st.error(str(e))

    c1, c2, c3 = st.columns(3)
    with c1, st.form(f"role_{user.id}"):
        role = st.selectbox("Role", ROLES, index=ROLES.index(user.role), format_func=str.title)
        if st.form_submit_button("Update role"):
            run(lambda s: svc.set_user_role(s, user.id, role, actor=admin), f"{user.full_name} is now {role}.")
    with c2, st.form(f"pw_{user.id}", clear_on_submit=True):
        new_pw = st.text_input("New password", type="password")
        if st.form_submit_button("Reset password"):
            run(lambda s: svc.reset_password(s, user.id, new_pw), f"Password reset for {user.full_name}.")
    with c3:
        st.write("Account status")
        if user.is_active:
            if st.button("Deactivate", icon=":material/person_off:", help="Blocks sign-in; keeps all their reports."):
                run(lambda s: svc.set_user_active(s, user.id, False, actor=admin), f"{user.full_name} deactivated.")
        elif st.button("Reactivate", icon=":material/person_check:"):
            run(lambda s: svc.set_user_active(s, user.id, True, actor=admin), f"{user.full_name} reactivated.")


def page() -> None:
    admin = current_user()
    page_header("Manage users", "Create accounts, reset passwords and control who can sign in.", org_name())

    with st.expander("Add a user", icon=":material/person_add:"):
        _create_form()

    with get_session() as s:
        users = svc.list_users(s)
    stat_cards(
        [
            {"label": "Users", "value": len(users), "icon": "users", "tone": "neutral"},
            {"label": "Admins", "value": sum(u.is_admin for u in users), "icon": "shield", "tone": "lime"},
            {"label": "Employees", "value": sum(not u.is_admin for u in users), "icon": "user", "tone": "blue"},
            {"label": "Inactive", "value": sum(not u.is_active for u in users), "icon": "pause", "tone": "amber"},
        ]
    )
    st.dataframe(
        style_table(pd.DataFrame(
            [
                {
                    "Name": u.full_name,
                    "Username": u.username,
                    "Role": u.role.title(),
                    "Status": "Active" if u.is_active else "Inactive",
                    "Created": u.created_at.date(),
                }
                for u in users
            ]
        )),
        hide_index=True,
        width="stretch",
        column_config={"Created": st.column_config.DateColumn(format="DD MMM YYYY")},
    )

    section("Edit a user")
    by_id = {u.id: u for u in users}
    user_id = st.selectbox(
        "User",
        list(by_id),
        format_func=lambda i: f"{by_id[i].full_name} (@{by_id[i].username})" + ("" if by_id[i].is_active else " - inactive"),
    )
    if user_id:
        _edit_user(admin, by_id[user_id])
