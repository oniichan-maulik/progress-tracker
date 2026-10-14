"""Helpers shared by the Streamlit pages."""

from datetime import date, datetime

import pandas as pd
import streamlit as st

from core import services as svc
from core.db import get_session
from core.reports import summarize, weekly_breakdown
from views.ui import stat_cards, style_table
from core.models import APPROVED, CHANGES_REQUESTED, DRAFT, STATUSES, SUBMITTED, User

REVIEW_BADGES = {
    DRAFT: ("Draft", "gray", ":material/edit_note:"),
    SUBMITTED: ("Submitted - awaiting review", "blue", ":material/send:"),
    APPROVED: ("Approved", "green", ":material/check_circle:"),
    CHANGES_REQUESTED: ("Changes requested", "orange", ":material/undo:"),
}


# ---------------------------------------------------------------- session


def current_user() -> User | None:
    user_id = st.session_state.get("user_id")
    if user_id is None:
        return None
    with get_session() as s:
        user = svc.get_user(s, user_id)
    if user is None or not user.is_active:
        logout()
        return None
    return user


def login(user: User) -> None:
    st.session_state["user_id"] = user.id


def logout() -> None:
    for key in list(st.session_state.keys()):
        del st.session_state[key]


def flash(message: str, icon: str = ":material/check_circle:") -> None:
    """Queue a toast that survives the next st.rerun()."""
    st.session_state.setdefault("_flash", []).append((message, icon))


def show_flash() -> None:
    for message, icon in st.session_state.pop("_flash", []):
        st.toast(message, icon=icon)


# ---------------------------------------------------------------- widgets


def month_selector(key: str, extra_months: list[str] | None = None) -> str:
    months = sorted(set(svc.recent_months(12)) | set(extra_months or []), reverse=True)
    return st.selectbox("Month", months, format_func=svc.month_label, key=key)


def review_badge(state: str) -> None:
    label, color, icon = REVIEW_BADGES.get(state, (state, "gray", None))
    st.badge(label, color=color, icon=icon)


def metrics_row(stats: dict) -> None:
    open_tasks = stats["tasks"] - stats["completed"]
    stat_cards(
        [
            {"label": "Tasks", "value": stats["tasks"], "icon": "tasks", "tone": "neutral", "hint": f"{open_tasks} still open"},
            {"label": "Completed", "value": stats["completed"], "icon": "done", "tone": "green",
             "hint": f"{stats['under_review']} under review"},
            {"label": "Hours logged", "value": f"{stats['hours']:g}", "icon": "clock", "tone": "blue"},
            {"label": "Completion rate", "value": f"{stats['completion_rate']:.0%}", "icon": "target", "tone": "lime"},
        ]
    )


def display_tasks(df: pd.DataFrame, include_employee: bool = False) -> None:
    """Read-only task table."""
    view = df.copy()
    view["Date"] = [f"{d:%d %b %Y}" for d in view["Date"]]
    view["Due Date"] = [
        f"{d:%d %b} · overdue" if overdue else (f"{d:%d %b}" if pd.notna(d) and d else "")
        for d, overdue in zip(view["Due Date"], view["Overdue"])
    ]
    cols = (["Employee"] if include_employee else []) + ["Date", "Task", "Status", "Hours", "Notes", "Assigned By", "Due Date"]
    st.dataframe(
        style_table(view[cols].reset_index(drop=True)),
        hide_index=True,
        width="stretch",
        column_config={
            "Task": st.column_config.TextColumn(width="large"),
            "Notes": st.column_config.TextColumn(width="medium"),
        },
    )


def to_date(value) -> date | None:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.to_datetime(value).date()


def to_hours(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def weekly_view(month: str, df: pd.DataFrame, include_employee: bool = False) -> None:
    weeks = weekly_breakdown(df, month)
    if not weeks:
        st.caption("No tasks this month yet.")
        return
    for week, start, end, rows in weeks:
        stats = summarize(rows)
        label = (
            f"**Week {week}** · {start:%d %b} – {end:%d %b} · "
            f":green[{stats['completed']}/{stats['tasks']} completed] · :gray[{stats['hours']:g} h]"
        )
        with st.expander(label, icon=":material/date_range:"):
            st.progress(stats["completion_rate"], text=f"{stats['completion_rate']:.0%} of this week's tasks completed")
            display_tasks(rows, include_employee=include_employee)


STATUS_OPTIONS = list(STATUSES)
