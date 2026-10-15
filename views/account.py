"""Everyone's own account: profile details and changing their password."""

from html import escape

import streamlit as st

from core import services as svc
from core.auth import MIN_PASSWORD_LENGTH
from core.config import org_name
from core.db import get_session
from views.common import current_user, flash
from views.ui import card, card_title, page_header


def _profile(user) -> None:
    with card("profile"):
        card_title("Profile", "Ask an admin if any of this needs to change.")
        for label, value in (
            ("Name", user.full_name),
            ("Username", f"@{user.username}"),
            ("Role", user.role.title()),
            ("Member since", f"{user.created_at:%d %b %Y}"),
        ):
            st.markdown(
                f'<div class="pt-field"><span class="pt-eyebrow">{label}</span><span>{escape(value)}</span></div>',
                unsafe_allow_html=True,
            )


def _change_password(user) -> None:
    with card("password"):
        card_title("Change password", f"At least {MIN_PASSWORD_LENGTH} characters. You'll stay signed in.")
        with st.form("change_password", clear_on_submit=True, border=False):
            current = st.text_input("Current password", type="password")
            new = st.text_input("New password", type="password")
            confirm = st.text_input("Confirm new password", type="password")
            if st.form_submit_button("Update password", type="primary", icon=":material/lock_reset:"):
                if new != confirm:
                    st.error("The new passwords don't match.")
                    return
                try:
                    with get_session() as s:
                        svc.change_own_password(s, user.id, current, new)
                    flash("Password updated.", ":material/lock:")
                    st.rerun()
                except svc.ServiceError as e:
                    st.error(str(e))


def page() -> None:
    user = current_user()
    page_header("My account", "Your profile and sign-in details.", org_name())
    left, right = st.columns([1, 1.2])
    with left:
        _profile(user)
    with right:
        _change_password(user)
