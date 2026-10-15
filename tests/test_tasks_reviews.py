from datetime import date

import pytest

from core import services as svc
from core.models import APPROVED, CHANGES_REQUESTED, COMPLETED, IN_PROGRESS, NOT_STARTED, SUBMITTED
from core.services import (
    ServiceError,
    add_task,
    assign_task,
    delete_task,
    get_assigned_tasks,
    get_tasks,
    is_overdue,
    month_bounds,
    recent_months,
    review_month,
    review_state,
    save_task_changes,
    submit_month,
    update_task,
    week_of_month,
    week_range,
)

OCT = "2026-10"
D = date(2026, 10, 14)


def test_date_helpers():
    assert month_bounds("2026-02") == (date(2026, 2, 1), date(2026, 2, 28))
    # 1 Oct 2026 is a Thursday: week 1 is Thu-Sun, week 2 starts Monday the 5th.
    assert week_of_month(date(2026, 10, 1)) == 1
    assert week_of_month(date(2026, 10, 4)) == 1
    assert week_of_month(date(2026, 10, 5)) == 2
    assert week_of_month(date(2026, 10, 31)) == 5
    assert week_range(OCT, 1) == (date(2026, 10, 1), date(2026, 10, 4))
    assert week_range(OCT, 5) == (date(2026, 10, 26), date(2026, 10, 31))
    assert recent_months(3, today=date(2026, 1, 20)) == ["2026-01", "2025-12", "2025-11"]


def test_add_and_list_tasks(session, alice, bob):
    add_task(session, alice.id, D, "Write docs", IN_PROGRESS)
    add_task(session, bob.id, D, "Fix bug", COMPLETED, hours=2)
    add_task(session, alice.id, date(2026, 9, 30), "Old task")
    assert [t.title for t in get_tasks(session, user_id=alice.id, month=OCT)] == ["Write docs"]
    assert len(get_tasks(session, month=OCT)) == 2


def test_task_validation(session, alice):
    with pytest.raises(ServiceError, match="required"):
        add_task(session, alice.id, D, "   ")
    with pytest.raises(ServiceError, match="Status"):
        add_task(session, alice.id, D, "x", "Done")
    add_task(session, alice.id, D, "Done without hours", COMPLETED)  # hours are no longer tracked
    with pytest.raises(ServiceError, match="between"):
        add_task(session, alice.id, D, "x", IN_PROGRESS, hours=-1)


def test_employee_cannot_touch_others_tasks(session, alice, bob):
    task = add_task(session, bob.id, D, "Bob's task")
    with pytest.raises(ServiceError, match="own tasks"):
        update_task(session, task.id, alice, status=IN_PROGRESS)
    with pytest.raises(ServiceError, match="own tasks"):
        svc.request_deletion(session, task.id, alice, "not mine")


def test_assigned_task_rules(session, admin, alice, bob):
    tasks = assign_task(session, admin, [alice.id, bob.id], "Quarterly audit", due_date=date(2026, 10, 20), today=D)
    assert len(tasks) == 2
    t = tasks[0]
    assert t.status == NOT_STARTED and t.assigned_by == admin.id and t.work_date == D

    # Employee may progress it but not rename or delete it.
    update_task(session, t.id, alice, status=COMPLETED, hours=3, notes="done")
    with pytest.raises(ServiceError, match="assigned"):
        update_task(session, t.id, alice, title="Something else")
    with pytest.raises(ServiceError, match="Only an admin"):
        delete_task(session, t.id, alice)

    # Admin can.
    update_task(session, t.id, admin, title="Q3 audit")
    assert len(get_assigned_tasks(session, open_only=True)) == 1
    delete_task(session, t.id, admin)
    assert len(get_assigned_tasks(session)) == 1


def test_assign_validation(session, admin, alice):
    with pytest.raises(ServiceError, match="Only admins"):
        assign_task(session, alice, [alice.id], "x", today=D)
    with pytest.raises(ServiceError, match="at least one"):
        assign_task(session, admin, [], "x", today=D)
    with pytest.raises(ServiceError, match="past"):
        assign_task(session, admin, [alice.id], "x", due_date=date(2026, 10, 1), today=D)


def test_overdue(session, admin, alice):
    (t,) = assign_task(session, admin, [alice.id], "x", due_date=date(2026, 10, 15), today=D)
    assert not is_overdue(t, today=date(2026, 10, 15))
    assert is_overdue(t, today=date(2026, 10, 16))
    update_task(session, t.id, alice, status=COMPLETED, hours=1)
    assert not is_overdue(t, today=date(2026, 10, 16))


def test_review_workflow(session, admin, alice):
    with pytest.raises(ServiceError, match="at least one task"):
        submit_month(session, alice.id, OCT)
    task = add_task(session, alice.id, D, "Report", IN_PROGRESS)
    submit_month(session, alice.id, OCT)
    assert review_state(session, alice.id, OCT) == SUBMITTED

    # Submitted month is locked for edits, additions and assignments.
    with pytest.raises(ServiceError, match="submitted"):
        update_task(session, task.id, alice, status=COMPLETED, hours=1)
    with pytest.raises(ServiceError, match="submitted"):
        add_task(session, alice.id, D, "Late addition")
    with pytest.raises(ServiceError, match="already submitted"):
        assign_task(session, admin, [alice.id], "x", today=D)
    with pytest.raises(ServiceError, match="already"):
        submit_month(session, alice.id, OCT)

    with pytest.raises(ServiceError, match="comment"):
        review_month(session, admin, alice.id, OCT, approve=False)
    review_month(session, admin, alice.id, OCT, approve=False, comment="Add hours")
    assert review_state(session, alice.id, OCT) == CHANGES_REQUESTED

    update_task(session, task.id, alice, status=COMPLETED, hours=4)
    submit_month(session, alice.id, OCT)
    with pytest.raises(ServiceError, match="Only admins"):
        review_month(session, alice, alice.id, OCT, approve=True)
    review_month(session, admin, alice.id, OCT, approve=True, comment="Nice")
    assert review_state(session, alice.id, OCT) == APPROVED

    # Admin can reopen an approved month.
    review_month(session, admin, alice.id, OCT, approve=False, comment="Reopening")
    assert review_state(session, alice.id, OCT) == CHANGES_REQUESTED


def test_moving_task_into_locked_month_is_blocked(session, alice):
    add_task(session, alice.id, date(2026, 9, 10), "Sept work")
    submit_month(session, alice.id, "2026-09")
    task = add_task(session, alice.id, D, "Oct work")
    with pytest.raises(ServiceError, match="September 2026"):
        update_task(session, task.id, alice, work_date=date(2026, 9, 11))


def test_save_task_changes_is_atomic(session, admin, alice):
    keep = add_task(session, alice.id, D, "Keep")
    (assigned,) = assign_task(session, admin, [alice.id], "Assigned", today=D)
    with pytest.raises(ServiceError):
        save_task_changes(
            session,
            alice,
            alice.id,
            added=[{"work_date": D, "title": "New"}],
            updated={keep.id: {"title": "Renamed"}, assigned.id: {"title": "Hijacked"}},  # not allowed
        )
    titles = sorted(t.title for t in get_tasks(session, user_id=alice.id))
    assert titles == ["Assigned", "Keep"]

    save_task_changes(session, alice, alice.id, added=[{"work_date": D, "title": "New"}], updated={keep.id: {"title": "Renamed"}})
    titles = sorted(t.title for t in get_tasks(session, user_id=alice.id))
    assert titles == ["Assigned", "New", "Renamed"]


def test_employee_can_create_but_not_delete(session, alice):
    task = add_task(session, alice.id, D, "My own task", IN_PROGRESS)
    assert task.assigned_by is None
    with pytest.raises(ServiceError, match="Only an admin"):
        delete_task(session, task.id, alice)


def test_deletion_request_approved(session, admin, alice):
    task = add_task(session, alice.id, D, "Duplicate")
    with pytest.raises(ServiceError, match="reason"):
        svc.request_deletion(session, task.id, alice, "  ")
    svc.request_deletion(session, task.id, alice, "Logged twice")
    with pytest.raises(ServiceError, match="already waiting"):
        svc.request_deletion(session, task.id, alice, "again")
    assert [t.id for t in svc.get_deletion_requests(session)] == [task.id]
    with pytest.raises(ServiceError, match="Only admins"):
        svc.resolve_deletion_request(session, alice, task.id, approve=True)
    svc.resolve_deletion_request(session, admin, task.id, approve=True)
    assert get_tasks(session, user_id=alice.id) == []
    assert svc.get_deletion_requests(session) == []


def test_deletion_request_rejected_or_cancelled(session, admin, alice):
    task = add_task(session, alice.id, D, "Keep me")
    svc.request_deletion(session, task.id, alice, "oops")
    svc.resolve_deletion_request(session, admin, task.id, approve=False)
    assert task.deletion_requested_at is None and task.deletion_reason == ""
    assert len(get_tasks(session, user_id=alice.id)) == 1

    svc.request_deletion(session, task.id, alice, "oops again")
    svc.cancel_deletion_request(session, task.id, alice)
    assert svc.get_deletion_requests(session) == []
    with pytest.raises(ServiceError, match="no longer exists"):
        svc.resolve_deletion_request(session, admin, task.id, approve=True)


def test_deletion_request_respects_month_lock(session, admin, alice):
    first = add_task(session, alice.id, D, "First")
    second = add_task(session, alice.id, D, "Second")
    later = add_task(session, alice.id, D, "Later")
    svc.request_deletion(session, first.id, alice, "mistake")
    svc.request_deletion(session, second.id, alice, "duplicate")
    submit_month(session, alice.id, OCT)

    # No new requests once the month is locked...
    with pytest.raises(ServiceError, match="submitted"):
        svc.request_deletion(session, later.id, alice, "late")
    # ...but the reviewing admin can still approve one while it's submitted,
    svc.resolve_deletion_request(session, admin, first.id, approve=True)
    # and not once the month is approved.
    review_month(session, admin, alice.id, OCT, approve=True)
    with pytest.raises(ServiceError, match="already approved"):
        svc.resolve_deletion_request(session, admin, second.id, approve=True)
    review_month(session, admin, alice.id, OCT, approve=False, comment="reopen")
    svc.resolve_deletion_request(session, admin, second.id, approve=True)
    assert [t.title for t in get_tasks(session, user_id=alice.id)] == ["Later"]


def test_migration_adds_new_columns(tmp_path):
    from sqlalchemy import inspect, text

    from core.db import init_db, make_engine

    engine = make_engine(f"sqlite:///{(tmp_path / 'old.db').as_posix()}")
    with engine.begin() as conn:  # a tasks table from before deletion requests existed
        conn.execute(text("CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT)"))
        conn.execute(text("INSERT INTO tasks (title) VALUES ('old row')"))
    init_db(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("tasks")}
    assert {"deletion_requested_at", "deletion_reason"} <= cols
    with engine.connect() as conn:
        assert conn.execute(text("SELECT title FROM tasks")).scalar() == "old row"


def test_admin_can_assign_to_self_and_work_on_it(session, admin, alice):
    tasks = assign_task(session, admin, [admin.id, alice.id], "Plan Q4 goals", today=D)
    mine = next(t for t in tasks if t.user_id == admin.id)
    update_task(session, mine.id, admin, status=COMPLETED, hours=2)
    assert [t.title for t in get_tasks(session, user_id=admin.id)] == ["Plan Q4 goals"]
    submit_month(session, admin.id, OCT)
    review_month(session, admin, admin.id, OCT, approve=True)
    assert review_state(session, admin.id, OCT) == APPROVED


def test_delete_user_removes_their_data_and_keeps_others(session, admin, alice, bob):
    from core.models import MonthlyReview, Task, User

    second_admin = svc.create_user(session, "boss2", "Second Boss", "adminpass2", "admin")
    add_task(session, alice.id, D, "Alice's own task")
    assign_task(session, second_admin, [alice.id, bob.id], "From second admin", today=D)
    submit_month(session, bob.id, OCT)
    review_month(session, second_admin, bob.id, OCT, approve=True, allow_open_assigned=True)
    submit_month(session, alice.id, OCT)

    assert svc.user_footprint(session, alice.id) == {"tasks": 2, "reviews": 1, "assigned_to_others": 0, "reviewed": 0}
    removed = svc.delete_user(session, alice.id, actor=admin)
    assert removed["tasks"] == 2
    assert session.get(User, alice.id) is None
    assert get_tasks(session, user_id=alice.id) == []
    assert svc.get_review(session, alice.id, OCT) is None

    # Deleting the second admin keeps Bob's task and approved report, minus the link to them.
    svc.delete_user(session, second_admin.id, actor=admin)
    (bob_task,) = get_tasks(session, user_id=bob.id)
    assert bob_task.assigned_by is None
    bob_review = svc.get_review(session, bob.id, OCT)
    assert bob_review.state == APPROVED and bob_review.reviewer_id is None
    assert session.query(Task).count() == 1 and session.query(MonthlyReview).count() == 1


def test_delete_user_guards(session, admin, alice):
    with pytest.raises(ServiceError, match="Only admins"):
        svc.delete_user(session, admin.id, actor=alice)
    with pytest.raises(ServiceError, match="your own account"):
        svc.delete_user(session, admin.id, actor=admin)
    other = svc.create_user(session, "boss2", "Second Boss", "adminpass2", "admin")
    svc.set_user_active(session, admin.id, False, actor=other)
    with pytest.raises(ServiceError, match="one active admin"):
        svc.delete_user(session, other.id, actor=admin)  # admin is inactive but object still admin
    with pytest.raises(ServiceError, match="not found"):
        svc.delete_user(session, 9999, actor=other)


def test_approval_warns_about_open_assigned_tasks(session, admin, alice):
    add_task(session, alice.id, D, "Own task", IN_PROGRESS)  # own open tasks don't block
    (assigned,) = assign_task(session, admin, [alice.id], "Audit", today=D)
    submit_month(session, alice.id, OCT)
    assert [t.title for t in svc.open_assigned_tasks(session, alice.id, OCT)] == ["Audit"]

    with pytest.raises(ServiceError, match="1 assigned task"):
        review_month(session, admin, alice.id, OCT, approve=True)
    assert review_state(session, alice.id, OCT) == SUBMITTED  # nothing changed

    # Sending back still works without confirmation; then the employee completes it.
    review_month(session, admin, alice.id, OCT, approve=False, comment="Finish the audit")
    update_task(session, assigned.id, alice, status=COMPLETED, hours=2)
    submit_month(session, alice.id, OCT)
    assert svc.open_assigned_tasks(session, alice.id, OCT) == []
    review_month(session, admin, alice.id, OCT, approve=True)
    assert review_state(session, alice.id, OCT) == APPROVED


def test_approve_anyway_with_open_assigned_tasks(session, admin, alice):
    assign_task(session, admin, [alice.id], "Audit", today=D)
    submit_month(session, alice.id, OCT)
    review_month(session, admin, alice.id, OCT, approve=True, allow_open_assigned=True)
    assert review_state(session, alice.id, OCT) == APPROVED
