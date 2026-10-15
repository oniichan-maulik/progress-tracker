"""Employee view: log tasks in an Excel-like grid, review by week, submit the month."""

from datetime import date

import pandas as pd
import streamlit as st

from core import services as svc
from core.config import org_name
from core.db import get_session
from core.models import APPROVED, CHANGES_REQUESTED, DRAFT, NOT_STARTED, SUBMITTED
from core.reports import ReportSection, build_workbook, summarize, tasks_to_df
from views.common import (
    STATUS_OPTIONS,
    current_user,
    display_tasks,
    flash,
    metrics_row,
    review_pill,
    to_date,
    to_hours,
    weekly_view,
)
from views.ui import card, card_title, header_rule, page_header, style_table

EDITABLE = ["Date", "Task", "Status", "Hours", "Notes"]


def _assigned_panel(user_id: int) -> None:
    with get_session() as s:
        tasks = svc.get_assigned_tasks(s, user_id=user_id, open_only=True)
        rows = [
            {
                "Task": t.title,
                "Assigned By": t.assigner.full_name if t.assigner else "",
                "Due": t.due_date,
                "Status": t.status,
                "Overdue": "Overdue" if svc.is_overdue(t) else "",
                "Find it in": svc.month_label(t.month),
            }
            for t in tasks
        ]
    if not rows:
        return
    overdue = sum(1 for r in rows if r["Overdue"])
    with card("assigned"):
        card_title(
            f"Assigned to you · {len(rows)} open" + (f" · {overdue} overdue" if overdue else ""),
            "Update status and hours for these in the task grid of the month shown.",
        )
        table = pd.DataFrame(rows)
        table["Due"] = [f"{d:%d %b %Y}" if d else "" for d in table["Due"]]
        st.dataframe(style_table(table), hide_index=True, width="stretch")


def _collect_changes(original: pd.DataFrame, edited: pd.DataFrame, default_date: date):
    original = original.set_index("id")
    added, updated = [], {}
    for _, row in edited.iterrows():
        fields = {
            "work_date": to_date(row["Date"]) or default_date,
            "title": "" if pd.isna(row["Task"]) else str(row["Task"]),
            "status": row["Status"] if isinstance(row["Status"], str) else NOT_STARTED,
            "hours": to_hours(row["Hours"]),
            "notes": "" if pd.isna(row["Notes"]) else str(row["Notes"]),
        }
        if pd.isna(row["id"]):
            if fields["title"].strip():
                added.append(fields)
            continue
        old = original.loc[int(row["id"])]
        before = {
            "work_date": to_date(old["Date"]),
            "title": old["Task"],
            "status": old["Status"],
            "hours": to_hours(old["Hours"]),
            "notes": old["Notes"] or "",
        }
        if fields != before:
            updated[int(row["id"])] = fields
    return added, updated


def _default_date(month: str) -> date:
    first, last = svc.month_bounds(month)
    today = date.today()
    return today if first <= today <= last else first


def _add_task_form(user, month: str) -> None:
    first, last = svc.month_bounds(month)
    with st.popover("Add task", icon=":material/add:", width="stretch"):
        with st.form(f"add_task_{month}", clear_on_submit=True, border=False):
            title = st.text_input("Task", max_chars=300)
            c1, c2, c3 = st.columns(3)
            work_date = c1.date_input(
                "Date", value=_default_date(month), min_value=first, max_value=last, format="DD/MM/YYYY"
            )
            status = c2.selectbox("Status", STATUS_OPTIONS)
            hours = c3.number_input("Hours taken", min_value=0.0, max_value=1000.0, step=0.25, value=None)
            notes = st.text_area("Notes (optional)", height=80)
            if st.form_submit_button("Add task", type="primary", icon=":material/add:"):
                try:
                    with get_session() as s:
                        svc.add_task(s, user.id, work_date, title, status, hours, notes)
                    st.session_state[f"grid_v_{month}"] = st.session_state.get(f"grid_v_{month}", 0) + 1
                    flash("Task added.")
                    st.rerun()
                except svc.ServiceError as e:
                    st.error(str(e))


def _task_grid(user, month: str, df: pd.DataFrame) -> None:
    first, last = svc.month_bounds(month)
    default_date = _default_date(month)
    version = st.session_state.setdefault(f"grid_v_{month}", 0)

    shown = [*EDITABLE, "Assigned By", "Due", "Flag"]
    grid = df[["id", *EDITABLE, "Assigned By"]].copy()
    grid["Due"] = [f"{d:%d %b}" if pd.notna(d) and d else "" for d in df["Due Date"]]
    grid["Flag"] = ["Delete requested" if f else "" for f in df["Deletion Requested"]]
    with st.form(f"grid_form_{month}", border=False):
        edited = st.data_editor(
            grid,
            key=f"grid_{month}_{version}",
            num_rows="add",
            hide_index=True,
            width="stretch",
            column_order=shown,
            disabled=["Assigned By", "Due", "Flag"],
            column_config={
                "Date": st.column_config.DateColumn(
                    min_value=first, max_value=last, default=default_date, format="DD MMM YYYY", required=True
                ),
                "Task": st.column_config.TextColumn(width="large", max_chars=300, required=True),
                "Status": st.column_config.SelectboxColumn(
                    options=STATUS_OPTIONS, default=NOT_STARTED, required=True, width="small"
                ),
                "Hours": st.column_config.NumberColumn(
                    "Hours", min_value=0, max_value=1000, step=0.25, format="%.2f", help="Time taken, in hours",
                    width="small",
                ),
                "Notes": st.column_config.TextColumn(width="medium"),
                "Assigned By": st.column_config.TextColumn(help="Set when an admin assigned this task", width="small"),
                "Due": st.column_config.TextColumn(width="small"),
                "Flag": st.column_config.TextColumn(
                    "", help="You asked to delete this task; waiting for an admin", width="small"
                ),
            },
        )
        saved = st.form_submit_button("Save changes", type="primary", icon=":material/save:")
    st.caption(
        "Edit cells directly, or add rows with the + below the grid. Completed tasks need their hours. "
        "Assigned tasks can't be renamed."
    )

    if saved:
        added, updated = _collect_changes(df, edited, default_date)
        if not (added or updated):
            st.info("No changes to save.")
            return
        try:
            with get_session() as s:
                svc.save_task_changes(s, user, user.id, added, updated)
        except svc.ServiceError as e:
            st.error(f"Nothing was saved: {e}")
            return
        st.session_state[f"grid_v_{month}"] = version + 1
        flash(f"Saved {len(added)} new and {len(updated)} changed task(s).")
        st.rerun()


def _deletion_panel(user, month: str, df: pd.DataFrame) -> None:
    pending = df[df["Deletion Requested"]]
    available = df[~df["Deletion Requested"]]
    label = "Request deletion" + (f" ({len(pending)})" if len(pending) else "")
    with st.popover(label, icon=":material/delete:", width="stretch"):
        st.caption("Tasks are only removed once an admin approves the request.")
        if not available.empty:
            options = {int(r["id"]): f"{r['Date']:%d %b} · {r['Task']}" for _, r in available.iterrows()}
            with st.form(f"del_req_{month}", clear_on_submit=True, border=False):
                chosen = st.multiselect("Tasks to delete", list(options), format_func=options.get)
                reason = st.text_input("Reason", placeholder="e.g. duplicate entry, logged by mistake")
                if st.form_submit_button("Send deletion request", icon=":material/send:"):
                    if not chosen:
                        st.error("Choose at least one task.")
                    else:
                        try:
                            with get_session() as s:
                                for task_id in chosen:
                                    svc.request_deletion(s, task_id, user, reason)
                            flash(f"Deletion requested for {len(chosen)} task(s).", ":material/delete:")
                            st.rerun()
                        except svc.ServiceError as e:
                            st.error(str(e))
        for _, r in pending.iterrows():
            st.markdown(f"**{r['Task']}** · {r['Date']:%d %b} · :orange[waiting for admin]")
            if st.button("Cancel this request", key=f"cancel_del_{r['id']}"):
                with get_session() as s:
                    svc.cancel_deletion_request(s, int(r["id"]), user)
                flash("Deletion request cancelled.")
                st.rerun()


def page() -> None:
    user = current_user()
    with get_session() as s:
        months_with_tasks = sorted({t.month for t in svc.get_tasks(s, user_id=user.id)})
    (month_col,) = page_header(
        "My report",
        "Log your tasks, track progress by week and submit the month for review.",
        f"{org_name()} · {user.full_name}",
        controls=1,
        ratio=3.4,
    )
    with month_col:
        month = st.selectbox(
            "Month",
            sorted(set(svc.recent_months(12)) | set(months_with_tasks), reverse=True),
            format_func=svc.month_label,
            key="my_month",
            label_visibility="collapsed",
        )
    header_rule()

    with get_session() as s:
        df = tasks_to_df(svc.get_tasks(s, user_id=user.id, month=month))
        review = svc.get_review(s, user.id, month)
        reviewer = review.reviewer.full_name if review and review.reviewer else ""
    state = review.state if review else DRAFT
    stats = summarize(df)
    locked = state in (SUBMITTED, APPROVED)

    if state == CHANGES_REQUESTED:
        st.warning(f"**{reviewer} requested changes:** {review.comment}", icon=":material/undo:")
    elif state == APPROVED and review.comment:
        st.success(f"**{reviewer}:** {review.comment}", icon=":material/check_circle:")
    elif state == SUBMITTED:
        st.info("This month is submitted and locked while it's being reviewed.", icon=":material/lock:")

    metrics_row(stats)
    _assigned_panel(user.id)

    with card("tasks"):
        head, delete, add = st.columns([3, 1.15, 1], vertical_alignment="center")
        with head:
            st.markdown(
                f'<div class="pt-card-title">Tasks · {svc.month_label(month)}&nbsp;&nbsp;{review_pill(state)}</div>',
                unsafe_allow_html=True,
            )
        if locked:
            if df.empty:
                st.caption("No tasks this month.")
            else:
                display_tasks(df)
        else:
            with add:
                _add_task_form(user, month)
            with delete:
                if not df.empty:
                    _deletion_panel(user, month, df)
            if df.empty:
                st.caption("No tasks yet. Use **Add task**, or type straight into the grid below.")
            _task_grid(user, month, df)

    with card("weeks"):
        card_title("Weekly breakdown", "Tasks grouped by week, with completion and hours")
        weekly_view(month, df)

    with card("submit"):
        text, submit, download = st.columns([2.4, 1.2, 1], vertical_alignment="center")
        with text:
            if state in (DRAFT, CHANGES_REQUESTED):
                card_title("Ready to submit?", "Submitting locks the month until it's approved or sent back. Save grid edits first.")
            else:
                card_title(f"Report {REVIEW_LABELS.get(state, state).lower()}", "Download a copy for your records.")
        with submit:
            if state in (DRAFT, CHANGES_REQUESTED):
                if st.button(
                    "Submit for review", type="primary", icon=":material/send:", disabled=df.empty, width="stretch"
                ):
                    try:
                        with get_session() as s:
                            svc.submit_month(s, user.id, month)
                        flash("Report submitted for review.", ":material/send:")
                        st.rerun()
                    except svc.ServiceError as e:
                        st.error(str(e))
        with download:
            section = ReportSection(user.full_name, month, state, df, review.comment if review else "")
            org = org_name()
            st.download_button(
                "Download Excel",
                # Built on click, without a rerun (a rerun would invalidate the download link).
                lambda: build_workbook([section], org),
                on_click="ignore",
                file_name=f"{user.username}_{month}_progress.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                icon=":material/download:",
                disabled=df.empty,
                width="stretch",
            )


REVIEW_LABELS = {SUBMITTED: "Submitted", APPROVED: "Approved"}
