"""Admin view: create users, reset passwords, change roles, deactivate accounts."""

import pandas as pd
import streamlit as st

from core import services as svc
from core.auth import MIN_PASSWORD_LENGTH
from core.config import org_name
from core.db import get_session
from core.models import ROLE_EMPLOYEE, ROLES
from views.common import current_user, flash
from views.ui import card, card_title, page_header, stat_cards, status_pill, style_table


def _create_form() -> None:
    with card("new_user"):
        card_title("Add a user", "Share the temporary password with them directly.")
        with st.form("new_user", clear_on_submit=True, border=False):
            full_name = st.text_input("Full name")
            username = st.text_input("Username", help="Letters, numbers, '.' and '_'. Case-insensitive.")
            c1, c2 = st.columns([2, 1])
            password = c1.text_input(
                "Temporary password", type="password", help=f"At least {MIN_PASSWORD_LENGTH} characters."
            )
            role = c2.selectbox("Role", ROLES, index=ROLES.index(ROLE_EMPLOYEE), format_func=str.title)
            if st.form_submit_button("Create user", type="primary", icon=":material/person_add:"):
                try:
                    with get_session() as s:
                        user = svc.create_user(s, username, full_name, password, role)
                    flash(f"Created {user.full_name} (@{user.username}).")
                    st.rerun()
                except svc.ServiceError as e:
                    st.error(str(e))


def _edit_user(admin, users) -> None:
    def run(action, message):
        try:
            with get_session() as s:
                action(s)
            flash(message)
            st.rerun()
        except svc.ServiceError as e:
            st.error(str(e))

    with card("edit_user"):
        card_title("Edit a user", "Change role, reset a password, or block sign-in.")
        by_id = {u.id: u for u in users}
        user = by_id[
            st.selectbox(
                "User",
                list(by_id),
                # Labels must not change when an account is edited: Streamlit matches the
                # selection by label, and a changed label (e.g. "inactive") reset the picker
                # to the first user, so the next action hit the wrong account.
                format_func=lambda i: f"{by_id[i].full_name} (@{by_id[i].username})",
                key="edit_user_pick",
            )
        ]
        st.markdown(
            status_pill(user.role.title(), "Submitted" if user.is_admin else "Draft") + "&nbsp;"
            + status_pill("Active" if user.is_active else "Inactive"),
            unsafe_allow_html=True,
        )
        with st.form(f"role_{user.id}", border=False):
            c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
            role = c1.selectbox("Role", ROLES, index=ROLES.index(user.role), format_func=str.title)
            if c2.form_submit_button("Update role", width="stretch"):
                run(lambda s: svc.set_user_role(s, user.id, role, actor=admin), f"{user.full_name} is now {role}.")
        with st.form(f"pw_{user.id}", clear_on_submit=True, border=False):
            c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
            new_pw = c1.text_input("New password", type="password")
            if c2.form_submit_button("Reset password", width="stretch"):
                run(lambda s: svc.reset_password(s, user.id, new_pw), f"Password reset for {user.full_name}.")
        if user.is_active:
            if st.button("Deactivate account", icon=":material/person_off:", help="Blocks sign-in; keeps all their reports."):
                run(lambda s: svc.set_user_active(s, user.id, False, actor=admin), f"{user.full_name} deactivated.")
        elif st.button("Reactivate account", icon=":material/person_check:"):
            run(lambda s: svc.set_user_active(s, user.id, True, actor=admin), f"{user.full_name} reactivated.")

        st.markdown('<div class="pt-danger pt-eyebrow">Danger zone</div>', unsafe_allow_html=True)
        if user.id == admin.id:
            st.caption("You can't delete your own account.")
        elif st.button("Delete permanently…", key="open_delete_user", icon=":material/delete_forever:"):
            _confirm_delete(admin.id, user.id)


@st.dialog("Delete user permanently")
def _confirm_delete(admin_id: int, user_id: int) -> None:
    with get_session() as s:
        admin, user = svc.get_user(s, admin_id), svc.get_user(s, user_id)
        if user is None:
            st.info("This user no longer exists.")
            return
        footprint = svc.user_footprint(s, user_id)

    st.error(
        f"**This can't be undone.** {user.full_name} (@{user.username}) will be removed along with "
        f"**{footprint['tasks']} task(s)** and **{footprint['reviews']} monthly report(s)**.",
        icon=":material/warning:",
    )
    kept = []
    if footprint["assigned_to_others"]:
        kept.append(f"{footprint['assigned_to_others']} task(s) they assigned to others")
    if footprint["reviewed"]:
        kept.append(f"{footprint['reviewed']} report(s) they reviewed")
    if kept:
        st.caption(f"Kept, without their name: {' and '.join(kept)}.")
    st.caption("To block sign-in but keep their history, use **Deactivate account** instead.")

    typed = st.text_input(f"Type **{user.username}** to confirm", placeholder=user.username)
    c1, c2 = st.columns(2)
    if c1.button("Cancel", width="stretch"):
        st.rerun()
    if c2.button(
        "Delete permanently",
        key="confirm_delete_user",
        icon=":material/delete_forever:",
        disabled=typed.strip().lower() != user.username,
        width="stretch",
    ):
        try:
            with get_session() as s:
                svc.delete_user(s, user_id, actor=admin)
            flash(f"{user.full_name} was permanently deleted.", ":material/delete_forever:")
            st.rerun()
        except svc.ServiceError as e:
            st.error(str(e))


def page() -> None:
    admin = current_user()
    page_header("Manage users", "Create accounts, reset passwords and control who can sign in.", org_name())

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

    with card("users"):
        card_title("Team members", f"{len(users)} account(s)")
        st.dataframe(
            style_table(
                pd.DataFrame(
                    [
                        {
                            "Name": u.full_name,
                            "Username": f"@{u.username}",
                            "Role": u.role.title(),
                            "Status": "Active" if u.is_active else "Inactive",
                            "Created": f"{u.created_at:%d %b %Y}",
                        }
                        for u in users
                    ]
                )
            ),
            hide_index=True,
            width="stretch",
        )

    left, right = st.columns(2)
    with left:
        _create_form()
    with right:
        _edit_user(admin, users)
