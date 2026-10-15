"""Admin view: team overview, charts, and approving monthly reports."""

import pandas as pd
import streamlit as st

from core import services as svc
from core.config import org_name
from core.db import get_session
from core.models import APPROVED, DRAFT, SUBMITTED
from core.reports import ReportSection, build_workbook, summarize, tasks_to_df
from views import charts
from views.common import REVIEW_BADGES, current_user, flash, metrics_row, month_selector, weekly_view
from views.ui import attention, card, card_title, header_rule, page_header, status_pill, style_table

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _load(month: str):
    with get_session() as s:
        people = svc.list_users(s)
        ids = [p.id for p in people]
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
    # Active employees always show; admins and inactive people only when they logged work this month.
    worked = set(df["user_id"])
    people = [p for p in people if p.id in worked or (p.is_active and not p.is_admin)]
    return people, df, reviews, pd.DataFrame(trend)


def _overview(people, df: pd.DataFrame, reviews) -> pd.DataFrame:
    rows = []
    for p in people:
        stats = summarize(df[df["user_id"] == p.id])
        suffix = " (admin)" if p.is_admin else ("" if p.is_active else " (inactive)")
        rows.append(
            {
                "Employee": p.full_name + suffix,
                "user_id": p.id,
                "Tasks": stats["tasks"],
                "Completed": stats["completed"],
                "In Progress": stats["in_progress"],
                "Hours": stats["hours"],
                "Completion": stats["completion_rate"],
                "Overdue": int(df[(df["user_id"] == p.id) & df["Overdue"]].shape[0]),
                "Review": reviews.get(p.id, (DRAFT,))[0],
            }
        )
    return pd.DataFrame(rows)


def _review_actions(admin, employee, month: str, state: str) -> None:
    if state == SUBMITTED:
        with st.form(f"review_{employee.id}_{month}", border=False):
            comment = st.text_area(
                "Comment", placeholder="Optional for approval, required when requesting changes", height=90
            )
            c1, c2, _ = st.columns([1, 1, 2])
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
        st.caption("Not submitted yet. The employee can still edit this month.")


def _deletion_requests(admin, rows: list[dict]) -> None:
    with card("deletions"):
        card_title("Deletion requests", "Approve to delete the task, or reject to keep it.")
        df = pd.DataFrame(rows)
        shown = df.drop(columns="id").assign(
            Date=[f"{d:%d %b %Y}" for d in df["Date"]],
            Requested=[f"{d:%d %b %Y}" for d in df["Requested"]],
            Hours=pd.to_numeric(df["Hours"], errors="coerce"),
        )
        selection = st.dataframe(
            style_table(shown),
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="multi-row",
            key="deletion_requests",
            column_config={"Task": st.column_config.TextColumn(width="large")},
        )
        picked = [int(df.iloc[i]["id"]) for i in selection.selection.rows]
        c1, c2, c3 = st.columns([1, 1, 3], vertical_alignment="center")
        approve = c1.button("Approve & delete", type="primary", icon=":material/delete:", disabled=not picked, width="stretch")
        reject = c2.button("Reject", icon=":material/block:", disabled=not picked, width="stretch")
        c3.caption(f"{len(picked)} selected" if picked else "Select rows in the table first.")
        if approve or reject:
            try:
                with get_session() as s:
                    for task_id in picked:
                        svc.resolve_deletion_request(s, admin, task_id, approve=approve)
                flash(f"{'Deleted' if approve else 'Kept'} {len(picked)} task(s).")
                st.rerun()
            except svc.ServiceError as e:
                st.error(str(e))


def _pending_deletions() -> list[dict]:
    with get_session() as s:
        return [
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


def page() -> None:
    admin = current_user()
    month_col, export_col = page_header(
        "Team review", "Track the month, approve reports and handle requests.", org_name(), controls=2, ratio=3.2
    )
    with month_col:
        month = month_selector("team_month", label_visibility="collapsed")
    people, df, reviews, trend = _load(month)
    with export_col:
        sections = [
            ReportSection(p.full_name, month, reviews.get(p.id, (DRAFT, ""))[0], df[df["user_id"] == p.id], reviews.get(p.id, (DRAFT, ""))[1])
            for p in people
        ]
        org = org_name()
        st.download_button(
            "Export team",
            # Built on click, without a rerun: a rerun would invalidate the other download links.
            lambda: build_workbook(sections, org),
            on_click="ignore",
            file_name=f"team_{month}_progress.xlsx",
            mime=XLSX,
            icon=":material/download:",
            width="stretch",
            disabled=not people,
            help="One Excel sheet per person",
        )
    header_rule()

    if not people:
        st.info("No employees yet. Add them on the **Manage users** page.", icon=":material/person_add:")
        return

    overview = _overview(people, df, reviews)
    deletions = _pending_deletions()
    waiting = int((overview["Review"] == SUBMITTED).sum())
    overdue = int(overview["Overdue"].sum())
    attention(
        [s for s in (
            f"{waiting} report{'s' if waiting != 1 else ''} awaiting review" if waiting else "",
            f"{len(deletions)} deletion request{'s' if len(deletions) != 1 else ''}" if deletions else "",
            f"{overdue} overdue task{'s' if overdue != 1 else ''}" if overdue else "",
        ) if s]
    )

    metrics_row(summarize(df))

    with card("overview"):
        card_title("Team overview", svc.month_label(month))
        st.dataframe(
            style_table(overview.drop(columns="user_id")),
            hide_index=True,
            width="stretch",
            column_config={
                "Completion": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
                "Overdue": st.column_config.NumberColumn(help="Assigned tasks past their due date"),
            },
        )

    left, right = st.columns([1.15, 1])
    with left, card("hours"):
        card_title("Hours by person", "Total hours logged this month")
        charts.show(charts.hours_by_employee(overview))
    with right, card("status"):
        card_title("Task status", "Tasks per person by status")
        if df.empty:
            st.caption("No tasks this month.")
        else:
            charts.show(charts.status_breakdown(df, [p.full_name for p in people]))

    with card("trend"):
        card_title("Team hours", "Last 6 months")
        charts.show(charts.monthly_trend(trend))

    if deletions:
        _deletion_requests(admin, deletions)

    with card("review"):
        # Reports waiting for review first.
        ordered = sorted(people, key=lambda p: reviews.get(p.id, (DRAFT,))[0] != SUBMITTED)
        by_id = {p.id: p for p in ordered}
        head, pick = st.columns([2, 1.3], vertical_alignment="center")
        with head:
            card_title("Review a report", "Weekly breakdown, approval and export for one person")
        with pick:
            employee = by_id[
                st.selectbox(
                    "Person",
                    list(by_id),
                    # Name only: a label that changes on approve/send-back would reset the
                    # picker to another person. The review state is shown as a pill below.
                    format_func=lambda i: by_id[i].full_name,
                    key=f"team_employee_{month}",
                    label_visibility="collapsed",
                )
            ]
        state, comment, reviewer = reviews.get(employee.id, (DRAFT, "", ""))
        emp_df = df[df["user_id"] == employee.id]

        stats = summarize(emp_df)
        st.markdown(
            f"{status_pill(REVIEW_BADGES[state][0], state)}&nbsp;&nbsp;"
            f"<span style='color:var(--pt-text-2)'>{stats['tasks']} tasks · {stats['completed']} completed · "
            f"{stats['hours']:g} h logged</span>",
            unsafe_allow_html=True,
        )
        if comment:
            st.caption(f"Last comment from {reviewer}: “{comment}”")
        weekly_view(month, emp_df)
        _review_actions(admin, employee, month, state)
        section_one = ReportSection(employee.full_name, month, state, emp_df, comment)
        st.download_button(
            f"Download {employee.full_name}'s report",
            lambda: build_workbook([section_one], org),
            on_click="ignore",
            file_name=f"{employee.username}_{month}_progress.xlsx",
            mime=XLSX,
            icon=":material/download:",
            disabled=emp_df.empty,
        )
