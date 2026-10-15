"""Admin view: assign tasks to anyone in the team (admins included) and track them."""

from datetime import date

import pandas as pd
import streamlit as st

from core import services as svc
from core.config import org_name
from core.db import get_session
from views.common import current_user, flash
from views.ui import card, card_title, page_header, style_table


def _assign_form(admin, people) -> None:
    with card("assign_form"):
        card_title("New assignment", "Assign to one or more people. Admins see their tasks under My report.")
        with st.form("assign", clear_on_submit=True, border=False):
            names = {
                p.id: p.full_name + (" (you)" if p.id == admin.id else " (admin)" if p.is_admin else "")
                for p in people
            }
            title = st.text_input("Task", max_chars=300, placeholder="e.g. Prepare the Q3 client summary")
            c1, c2 = st.columns([2, 1])
            chosen = c1.multiselect("Assign to", list(names), format_func=names.get, placeholder="Choose people")
            due = c2.date_input("Due date (optional)", value=None, min_value=date.today(), format="DD/MM/YYYY")
            notes = st.text_area("Notes (optional)", height=80)
            if st.form_submit_button("Assign task", type="primary", icon=":material/assignment_add:"):
                try:
                    with get_session() as s:
                        tasks = svc.assign_task(s, admin, chosen, title, due_date=due, notes=notes)
                    flash(f"Assigned to {len(tasks)} {'person' if len(tasks) == 1 else 'people'}.")
                    st.rerun()
                except svc.ServiceError as e:
                    st.error(str(e))


def _tracker(admin) -> None:
    with card("assigned"):
        head, toggle, who_col = st.columns([2, 1, 1.6], vertical_alignment="center")
        with head:
            card_title("Assigned tasks", "Select rows to remove them.")
        open_only = toggle.toggle("Open only", value=True)
        with get_session() as s:
            tasks = svc.get_assigned_tasks(s, open_only=open_only)
            rows = [
                {
                    "id": t.id,
                    "Person": t.owner.full_name,
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
        names = sorted({r["Person"] for r in rows})
        who = who_col.multiselect("Person", names, placeholder="Everyone", label_visibility="collapsed")
        if who:
            rows = [r for r in rows if r["Person"] in who]
        if not rows:
            st.caption("No assigned tasks to show.")
            return

        df = pd.DataFrame(rows)
        shown = df.drop(columns="id").assign(
            Assigned=[f"{d:%d %b %Y}" for d in df["Assigned"]],
            Due=[f"{d:%d %b %Y}" if pd.notna(d) and d else "" for d in df["Due"]],
            Hours=pd.to_numeric(df["Hours"], errors="coerce"),
        )
        selection = st.dataframe(
            style_table(shown),
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="multi-row",
            key="assigned_table",
            column_config={"Task": st.column_config.TextColumn(width="large")},
        )
        picked = [int(df.iloc[i]["id"]) for i in selection.selection.rows]
        c1, c2 = st.columns([1, 3], vertical_alignment="center")
        remove = c1.button("Remove selected", icon=":material/delete:", disabled=not picked, width="stretch")
        c2.caption(f"{len(df)} task(s) · {int((df['Overdue'] != '').sum())} overdue")
        if remove:
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
    page_header("Assign tasks", "Give work to people in the team, with an optional due date, and track it.", org_name())
    with get_session() as s:
        people = svc.list_users(s, include_inactive=False)
    _assign_form(admin, people)
    _tracker(admin)
