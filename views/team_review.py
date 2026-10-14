"""Admin view: team overview, charts, and approving monthly reports."""

import pandas as pd
import streamlit as st

from core import services as svc
from core.config import org_name
from core.db import get_session
from core.models import APPROVED, DRAFT, ROLE_EMPLOYEE, SUBMITTED
from core.reports import ReportSection, build_workbook, summarize, tasks_to_df
from views import charts
from views.ui import page_header, section, style_table
from views.common import REVIEW_BADGES, current_user, flash, metrics_row, month_selector, review_badge, weekly_view

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _load(month: str):
    with get_session() as s:
        employees = svc.list_users(s, role=ROLE_EMPLOYEE)
        ids = [e.id for e in employees]
        df = tasks_to_df(svc.get_tasks(s, month=month, user_ids=ids))
        reviews = {
            uid: (r.state, r.comment, r.reviewer.full_name if r.reviewer else "")
            for uid, r in svc.list_reviews(s, month).items()
        }
        first, _ = svc.month_bounds(month)
        trend = [
            {"Month": svc.month_bounds(m)[0].strftime("%b %Y"), "Hours": summarize(tasks_to_df(svc.get_tasks(s, month=m, user_ids=ids)))["hours"]}
            for m in reversed(svc.recent_months(6, today=first))
        ]
    # Inactive employees only show up if they logged work this month.
    employees = [e for e in employees if e.is_active or e.id in set(df["user_id"])]
    return employees, df, reviews, pd.DataFrame(trend)


def _overview(employees, df: pd.DataFrame, reviews) -> pd.DataFrame:
    rows = []
    for e in employees:
        stats = summarize(df[df["user_id"] == e.id])
        rows.append(
            {
                "Employee": e.full_name + ("" if e.is_active else " (inactive)"),
                "user_id": e.id,
                "Tasks": stats["tasks"],
                "Completed": stats["completed"],
                "In Progress": stats["in_progress"],
                "Hours": stats["hours"],
                "Completion": stats["completion_rate"],
                "Overdue": int(df[(df["user_id"] == e.id) & df["Overdue"]].shape[0]),
                "Review": reviews.get(e.id, (DRAFT,))[0],
            }
        )
    return pd.DataFrame(rows)


def _review_actions(admin, employee, month: str, state: str) -> None:
    if state == SUBMITTED:
        with st.form(f"review_{employee.id}_{month}"):
            comment = st.text_area("Comment", placeholder="Optional for approval, required when requesting changes")
            c1, c2 = st.columns(2)
            approve = c1.form_submit_button("Approve", type="primary", icon=":material/check:", width="stretch")
            send_back = c2.form_submit_button("Request changes", icon=":material/undo:", width="stretch")
        if approve or send_back:
            try:
                with get_session() as s:
                    svc.review_month(s, admin, employee.id, month, approve=approve, comment=comment)
                flash(f"{employee.full_name}'s report {'approved' if approve else 'sent back'}.")
                st.rerun()
            except svc.ServiceError as e:
                st.error(str(e))
    elif state == APPROVED:
        with st.popover("Reopen this report", icon=":material/lock_open:"):
            with st.form(f"reopen_{employee.id}_{month}", border=False):
                comment = st.text_area("Why does it need changes?")
                if st.form_submit_button("Send back to employee"):
                    try:
                        with get_session() as s:
                            svc.review_month(s, admin, employee.id, month, approve=False, comment=comment)
                        flash(f"{employee.full_name}'s report reopened.")
                        st.rerun()
                    except svc.ServiceError as e:
                        st.error(str(e))
    else:
        st.caption("Not submitted yet - the employee can still edit this month.")


def _deletion_requests(admin) -> None:
    with get_session() as s:
        rows = [
            {
                "id": t.id,
                "Employee": t.owner.full_name,
                "Date": t.work_date,
                "Task": t.title,
                "Status": t.status,
                "Hours": t.hours,
                "Reason": t.deletion_reason,
                "Requested": t.deletion_requested_at.date(),
            }
            for t in svc.get_deletion_requests(s)
        ]
    if not rows:
        return
    with st.expander(f"Deletion requests · {len(rows)} pending", icon=":material/delete:", expanded=True):
        df = pd.DataFrame(rows)
        shown = df.drop(columns="id").assign(
            Date=[f"{d:%d %b %Y}" for d in df["Date"]], Requested=[f"{d:%d %b %Y}" for d in df["Requested"]]
        )
        selection = st.dataframe(
            style_table(shown),
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="multi-row",
            key="deletion_requests",
            column_config={
                "Task": st.column_config.TextColumn(width="large"),
            },
        )
        picked = [int(df.iloc[i]["id"]) for i in selection.selection.rows]
        st.caption("Select requests, then approve (task is deleted) or reject (task is kept).")
        c1, c2, _ = st.columns([1, 1, 2])
        approve = c1.button("Approve & delete", type="primary", icon=":material/delete:", disabled=not picked, width="stretch")
        reject = c2.button("Reject", icon=":material/block:", disabled=not picked, width="stretch")
        if approve or reject:
            try:
                with get_session() as s:
                    for task_id in picked:
                        svc.resolve_deletion_request(s, admin, task_id, approve=approve)
                flash(f"{'Deleted' if approve else 'Kept'} {len(picked)} task(s).")
                st.rerun()
            except svc.ServiceError as e:
                st.error(str(e))


def page() -> None:
    admin = current_user()
    page_header("Team review", "Track the team's month, approve reports and handle deletion requests.", org_name())
    _deletion_requests(admin)
    month = month_selector("team_month")
    employees, df, reviews, trend = _load(month)

    if not employees:
        st.info("No employees yet. Add them on the **Manage Users** page.", icon=":material/person_add:")
        return

    overview = _overview(employees, df, reviews)
    waiting = int((overview["Review"] == SUBMITTED).sum())
    if waiting:
        st.info(f"**{waiting}** report{'s' if waiting > 1 else ''} awaiting your review.", icon=":material/inbox:")

    metrics_row(summarize(df))
    st.dataframe(
        style_table(overview.drop(columns="user_id")),
        hide_index=True,
        width="stretch",
        column_config={
            "Completion": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
            "Overdue": st.column_config.NumberColumn(help="Assigned tasks past their due date"),
        },
    )

    tab_hours, tab_status, tab_trend = st.tabs(["Hours by employee", "Status breakdown", "6-month trend"])
    with tab_hours:
        st.plotly_chart(charts.hours_by_employee(overview), width="stretch")
    with tab_status:
        if df.empty:
            st.caption("No tasks this month.")
        else:
            st.plotly_chart(charts.status_breakdown(df, [e.full_name for e in employees]), width="stretch")
    with tab_trend:
        st.plotly_chart(charts.monthly_trend(trend), width="stretch")

    all_sections = [
        ReportSection(e.full_name, month, reviews.get(e.id, (DRAFT, ""))[0], df[df["user_id"] == e.id], reviews.get(e.id, (DRAFT, ""))[1])
        for e in employees
    ]
    st.download_button(
        "Download all reports (one sheet per employee)",
        build_workbook(all_sections, org_name()),
        file_name=f"team_{month}_progress.xlsx",
        mime=XLSX,
        icon=":material/download:",
    )

    st.divider()
    section("Employee report")
    # Put reports waiting for review first.
    ordered = sorted(employees, key=lambda e: reviews.get(e.id, (DRAFT,))[0] != SUBMITTED)
    by_id = {e.id: e for e in ordered}
    employee = by_id[
        st.selectbox(
            "Employee",
            list(by_id),
            format_func=lambda i: f"{by_id[i].full_name} · {REVIEW_BADGES[reviews.get(i, (DRAFT,))[0]][0]}",
            key=f"team_employee_{month}",
        )
    ]
    state, comment, reviewer = reviews.get(employee.id, (DRAFT, "", ""))
    emp_df = df[df["user_id"] == employee.id]

    review_badge(state)
    if comment:
        st.caption(f"Last comment from {reviewer}: “{comment}”")
    metrics_row(summarize(emp_df))
    weekly_view(month, emp_df)
    _review_actions(admin, employee, month, state)
    st.download_button(
        f"Download {employee.full_name}'s report",
        build_workbook([ReportSection(employee.full_name, month, state, emp_df, comment)], org_name()),
        file_name=f"{employee.username}_{month}_progress.xlsx",
        mime=XLSX,
        icon=":material/download:",
        disabled=emp_df.empty,
    )
