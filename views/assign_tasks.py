"""Admin view: assign tasks to employees and track them."""

from datetime import date

import pandas as pd
import streamlit as st

from core import services as svc
from core.config import org_name
from core.db import get_session
from core.models import ROLE_EMPLOYEE
from views.common import current_user, flash
from views.ui import page_header, section, style_table


def _assign_form(admin, employees) -> None:
    with st.form("assign", clear_on_submit=True):
        names = {e.id: e.full_name for e in employees}
        chosen = st.multiselect(
            "Assign to", list(names), format_func=names.get, placeholder="Choose one or more employees"
        )
        title = st.text_input("Task", max_chars=300)
        due = st.date_input("Due date (optional)", value=None, min_value=date.today(), format="DD/MM/YYYY")
        notes = st.text_area("Notes for the employee (optional)")
        if st.form_submit_button("Assign task", type="primary", icon=":material/assignment_add:"):
            try:
                with get_session() as s:
                    tasks = svc.assign_task(s, admin, chosen, title, due_date=due, notes=notes)
                flash(f"Assigned to {len(tasks)} employee{'s' if len(tasks) > 1 else ''}.")
                st.rerun()
            except svc.ServiceError as e:
                st.error(str(e))


def _tracker(admin) -> None:
    c1, c2 = st.columns([1, 2])
    open_only = c1.toggle("Open tasks only", value=True)
    with get_session() as s:
        tasks = svc.get_assigned_tasks(s, open_only=open_only)
        rows = [
            {
                "id": t.id,
                "Employee": t.owner.full_name,
                "Task": t.title,
                "Status": t.status,
                "Hours": t.hours,
                "Assigned": t.work_date,
                "Due": t.due_date,
                "Overdue": "Overdue" if svc.is_overdue(t) else "",
                "Assigned By": t.assigner.full_name if t.assigner else "",
            }
            for t in tasks
        ]
    names = sorted({r["Employee"] for r in rows})
    who = c2.multiselect("Employee", names, placeholder="All employees")
    if who:
        rows = [r for r in rows if r["Employee"] in who]
    if not rows:
        st.caption("No assigned tasks to show.")
        return

    df = pd.DataFrame(rows)
    st.caption(f"{len(df)} task(s) · {int((df['Overdue'] != '').sum())} overdue. Select rows to remove them.")
    shown = df.drop(columns="id").assign(
        Assigned=[f"{d:%d %b %Y}" for d in df["Assigned"]],
        Due=[f"{d:%d %b %Y}" if pd.notna(d) and d else "" for d in df["Due"]],
    )
    selection = st.dataframe(
        style_table(shown),
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="multi-row",
        key="assigned_table",
        column_config={
            "Task": st.column_config.TextColumn(width="large"),
        },
    )
    picked = [int(df.iloc[i]["id"]) for i in selection.selection.rows]
    if picked and st.button(f"Remove {len(picked)} selected task(s)", icon=":material/delete:"):
        try:
            with get_session() as s:
                for task_id in picked:
                    svc.delete_task(s, task_id, admin)
            flash(f"Removed {len(picked)} task(s).")
            st.rerun()
        except svc.ServiceError as e:
            st.error(str(e))


def page() -> None:
    admin = current_user()
    page_header("Assign tasks", "Give work to one or more employees, with an optional due date, and track it to completion.", org_name())
    with get_session() as s:
        employees = svc.list_users(s, include_inactive=False, role=ROLE_EMPLOYEE)
    if not employees:
        st.info("No active employees yet. Add them on the **Manage Users** page.", icon=":material/person_add:")
    else:
        _assign_form(admin, employees)
    section("Assigned tasks")
    _tracker(admin)
