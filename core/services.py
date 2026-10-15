"""Business rules: users, tasks, assignment and the monthly review workflow.

Every function takes an open Session and commits its own changes. Rule
violations raise ServiceError with a message that is safe to show to users.
"""

import calendar
from collections.abc import Iterable
from datetime import date, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from core.auth import hash_password, validate_password, verify_password
from core.models import (
    APPROVED,
    CHANGES_REQUESTED,
    COMPLETED,
    DRAFT,
    LOCKED_STATES,
    NOT_STARTED,
    ROLE_ADMIN,
    ROLES,
    STATUSES,
    SUBMITTED,
    MonthlyReview,
    Task,
    User,
    utcnow,
)


class ServiceError(Exception):
    """A rule was broken; the message is meant for the end user."""


# ---------------------------------------------------------------- dates


def month_key(d: date) -> str:
    return d.strftime("%Y-%m")


def month_bounds(month: str) -> tuple[date, date]:
    year, mon = map(int, month.split("-"))
    return date(year, mon, 1), date(year, mon, calendar.monthrange(year, mon)[1])


def month_label(month: str) -> str:
    return month_bounds(month)[0].strftime("%B %Y")


def recent_months(count: int, today: date | None = None) -> list[str]:
    """The current month and the `count - 1` before it, newest first."""
    d = (today or date.today()).replace(day=1)
    months = []
    for _ in range(count):
        months.append(month_key(d))
        d = (d - timedelta(days=1)).replace(day=1)
    return months


def week_of_month(d: date) -> int:
    """Week number within the month; weeks start on Monday, week 1 holds the 1st."""
    return (d.day + d.replace(day=1).weekday() - 1) // 7 + 1


def week_range(month: str, week: int) -> tuple[date, date]:
    first, last = month_bounds(month)
    monday = first - timedelta(days=first.weekday()) + timedelta(weeks=week - 1)
    return max(monday, first), min(monday + timedelta(days=6), last)


# ---------------------------------------------------------------- users


def has_admin(session: Session) -> bool:
    return session.scalar(select(func.count()).where(User.role == ROLE_ADMIN)) > 0


def get_user(session: Session, user_id: int) -> User | None:
    return session.get(User, user_id)


def list_users(session: Session, include_inactive: bool = True, role: str | None = None) -> list[User]:
    stmt = select(User).order_by(User.full_name)
    if not include_inactive:
        stmt = stmt.where(User.is_active)
    if role:
        stmt = stmt.where(User.role == role)
    return list(session.scalars(stmt))


def create_user(session: Session, username: str, full_name: str, password: str, role: str) -> User:
    username = username.strip().lower()
    full_name = full_name.strip()
    if not username or not username.replace("_", "").replace(".", "").isalnum():
        raise ServiceError("Username may only contain letters, numbers, '.' and '_'.")
    if not full_name:
        raise ServiceError("Full name is required.")
    if role not in ROLES:
        raise ServiceError(f"Unknown role '{role}'.")
    try:
        validate_password(password)
    except ValueError as e:
        raise ServiceError(str(e)) from None
    if session.scalar(select(User).where(User.username == username)):
        raise ServiceError(f"Username '{username}' is already taken.")
    user = User(username=username, full_name=full_name, password_hash=hash_password(password), role=role)
    session.add(user)
    session.commit()
    return user


def _active_admin_count(session: Session) -> int:
    return session.scalar(select(func.count()).where(User.role == ROLE_ADMIN, User.is_active))


def _require_user(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise ServiceError("User not found.")
    return user


def set_user_active(session: Session, user_id: int, active: bool, actor: User) -> None:
    user = _require_user(session, user_id)
    if not active and user.id == actor.id:
        raise ServiceError("You can't deactivate your own account.")
    if not active and user.is_admin and user.is_active and _active_admin_count(session) <= 1:
        raise ServiceError("At least one active admin is required.")
    user.is_active = active
    session.commit()


def set_user_role(session: Session, user_id: int, role: str, actor: User) -> None:
    user = _require_user(session, user_id)
    if role not in ROLES:
        raise ServiceError(f"Unknown role '{role}'.")
    if user.id == actor.id and role != user.role:
        raise ServiceError("You can't change your own role.")
    user.role = role
    session.commit()


def reset_password(session: Session, user_id: int, new_password: str) -> None:
    user = _require_user(session, user_id)
    try:
        validate_password(new_password)
    except ValueError as e:
        raise ServiceError(str(e)) from None
    user.password_hash = hash_password(new_password)
    session.commit()


def change_own_password(session: Session, user_id: int, current: str, new_password: str) -> None:
    """Self-service change: the current password must be correct and the new one different."""
    user = _require_user(session, user_id)
    if not verify_password(current, user.password_hash):
        raise ServiceError("Your current password is incorrect.")
    if new_password == current:
        raise ServiceError("The new password must be different from the current one.")
    reset_password(session, user_id, new_password)


def user_footprint(session: Session, user_id: int) -> dict[str, int]:
    """What a permanent delete would remove or detach, for the confirmation warning."""
    return {
        "tasks": session.scalar(select(func.count()).select_from(Task).where(Task.user_id == user_id)),
        "reviews": session.scalar(
            select(func.count()).select_from(MonthlyReview).where(MonthlyReview.user_id == user_id)
        ),
        "assigned_to_others": session.scalar(
            select(func.count()).select_from(Task).where(Task.assigned_by == user_id, Task.user_id != user_id)
        ),
        "reviewed": session.scalar(
            select(func.count()).select_from(MonthlyReview).where(
                MonthlyReview.reviewer_id == user_id, MonthlyReview.user_id != user_id
            )
        ),
    }


def delete_user(session: Session, user_id: int, actor: User) -> dict[str, int]:
    """Permanently delete a user with their tasks and monthly reports.

    Tasks they assigned to others and reports they reviewed are kept; only the
    link to the deleted user is cleared.
    """
    if not actor.is_admin:
        raise ServiceError("Only admins can delete users.")
    user = _require_user(session, user_id)
    if user.id == actor.id:
        raise ServiceError("You can't delete your own account.")
    if user.is_admin and user.is_active and _active_admin_count(session) <= 1:
        raise ServiceError("At least one active admin is required.")

    footprint = user_footprint(session, user_id)
    try:
        session.execute(update(Task).where(Task.assigned_by == user_id).values(assigned_by=None))
        session.execute(update(MonthlyReview).where(MonthlyReview.reviewer_id == user_id).values(reviewer_id=None))
        session.execute(delete(Task).where(Task.user_id == user_id))
        session.execute(delete(MonthlyReview).where(MonthlyReview.user_id == user_id))
        session.delete(user)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return footprint


# ---------------------------------------------------------------- reviews


def get_review(session: Session, user_id: int, month: str) -> MonthlyReview | None:
    return session.scalar(
        select(MonthlyReview).where(MonthlyReview.user_id == user_id, MonthlyReview.month == month)
    )


def review_state(session: Session, user_id: int, month: str) -> str:
    review = get_review(session, user_id, month)
    return review.state if review else DRAFT


def is_month_locked(session: Session, user_id: int, month: str) -> bool:
    return review_state(session, user_id, month) in LOCKED_STATES


def _ensure_unlocked(session: Session, user_id: int, d: date) -> None:
    month = month_key(d)
    if is_month_locked(session, user_id, month):
        raise ServiceError(
            f"{month_label(month)} is {review_state(session, user_id, month).lower()} and can't be changed."
        )


def submit_month(session: Session, user_id: int, month: str) -> MonthlyReview:
    first, last = month_bounds(month)
    task_count = session.scalar(
        select(func.count()).where(Task.user_id == user_id, Task.work_date.between(first, last))
    )
    if not task_count:
        raise ServiceError("Add at least one task before submitting the month.")
    review = get_review(session, user_id, month)
    if review and review.state in LOCKED_STATES:
        raise ServiceError(f"This month is already {review.state.lower()}.")
    if review is None:
        review = MonthlyReview(user_id=user_id, month=month)
        session.add(review)
    review.state = SUBMITTED
    review.submitted_at = utcnow()
    session.commit()
    return review


def review_month(
    session: Session, reviewer: User, user_id: int, month: str, approve: bool, comment: str = ""
) -> MonthlyReview:
    if not reviewer.is_admin:
        raise ServiceError("Only admins can review reports.")
    review = get_review(session, user_id, month)
    allowed = (SUBMITTED,) if approve else (SUBMITTED, APPROVED)
    if review is None or review.state not in allowed:
        raise ServiceError("This report isn't waiting for review." if approve else "This report can't be sent back.")
    if not approve and not comment.strip():
        raise ServiceError("Add a comment explaining what needs to change.")
    review.state = APPROVED if approve else CHANGES_REQUESTED
    review.comment = comment.strip()
    review.reviewer_id = reviewer.id
    review.reviewed_at = utcnow()
    session.commit()
    return review


def list_reviews(session: Session, month: str) -> dict[int, MonthlyReview]:
    rows = session.scalars(select(MonthlyReview).where(MonthlyReview.month == month))
    return {r.user_id: r for r in rows}


# ---------------------------------------------------------------- tasks


def _finish(session: Session, commit: bool) -> None:
    if commit:
        session.commit()
    else:
        session.flush()


def _clean_task_fields(title: str, status: str, hours: float | None) -> tuple[str, str, float | None]:
    title = (title or "").strip()
    if not title:
        raise ServiceError("Task description is required.")
    if status not in STATUSES:
        raise ServiceError(f"Status must be one of: {', '.join(STATUSES)}.")
    if hours is not None:
        hours = round(float(hours), 2)
        if hours < 0 or hours > 1000:
            raise ServiceError("Hours must be between 0 and 1000.")
    if status == COMPLETED and not hours:
        raise ServiceError(f"Enter the hours taken for completed task '{title}'.")
    return title, status, hours


def get_tasks(
    session: Session, user_id: int | None = None, month: str | None = None, user_ids: Iterable[int] | None = None
) -> list[Task]:
    stmt = select(Task).order_by(Task.work_date, Task.id)
    if user_id is not None:
        stmt = stmt.where(Task.user_id == user_id)
    if user_ids is not None:
        stmt = stmt.where(Task.user_id.in_(list(user_ids)))
    if month:
        first, last = month_bounds(month)
        stmt = stmt.where(Task.work_date.between(first, last))
    return list(session.scalars(stmt))


def add_task(
    session: Session,
    user_id: int,
    work_date: date,
    title: str,
    status: str = NOT_STARTED,
    hours: float | None = None,
    notes: str = "",
    commit: bool = True,
) -> Task:
    title, status, hours = _clean_task_fields(title, status, hours)
    _ensure_unlocked(session, user_id, work_date)
    task = Task(user_id=user_id, work_date=work_date, title=title, status=status, hours=hours, notes=notes or "")
    session.add(task)
    _finish(session, commit)
    return task


def _require_task_access(session: Session, task_id: int, actor: User) -> Task:
    task = session.get(Task, task_id)
    if task is None:
        raise ServiceError("Task not found.")
    if task.user_id != actor.id and not actor.is_admin:
        raise ServiceError("You can only change your own tasks.")
    return task


def update_task(session: Session, task_id: int, actor: User, commit: bool = True, **changes) -> Task:
    """Apply changes to work_date, title, status, hours and notes."""
    task = _require_task_access(session, task_id, actor)
    _ensure_unlocked(session, task.user_id, task.work_date)

    new_date = changes.get("work_date", task.work_date)
    if new_date != task.work_date:
        _ensure_unlocked(session, task.user_id, new_date)
    new_title = changes.get("title", task.title)
    if task.assigned_by and not actor.is_admin and (new_title or "").strip() != task.title:
        raise ServiceError(f"'{task.title}' was assigned to you, so its description can't be changed.")

    title, status, hours = _clean_task_fields(
        new_title, changes.get("status", task.status), changes.get("hours", task.hours)
    )
    task.work_date, task.title, task.status, task.hours = new_date, title, status, hours
    task.notes = changes.get("notes", task.notes) or ""
    _finish(session, commit)
    return task


def delete_task(session: Session, task_id: int, actor: User) -> None:
    """Admins delete directly; employees go through request_deletion instead."""
    if not actor.is_admin:
        raise ServiceError("Only an admin can delete tasks. Request deletion instead.")
    task = _require_task_access(session, task_id, actor)
    _ensure_unlocked(session, task.user_id, task.work_date)
    session.delete(task)
    session.commit()


def request_deletion(session: Session, task_id: int, actor: User, reason: str) -> Task:
    task = _require_task_access(session, task_id, actor)
    if task.deletion_requested_at:
        raise ServiceError(f"Deletion of '{task.title}' is already waiting for approval.")
    if not reason.strip():
        raise ServiceError("Give a reason so the admin can decide.")
    _ensure_unlocked(session, task.user_id, task.work_date)
    task.deletion_requested_at = utcnow()
    task.deletion_reason = reason.strip()
    session.commit()
    return task


def cancel_deletion_request(session: Session, task_id: int, actor: User) -> None:
    task = _require_task_access(session, task_id, actor)
    task.deletion_requested_at = None
    task.deletion_reason = ""
    session.commit()


def get_deletion_requests(session: Session, user_id: int | None = None) -> list[Task]:
    stmt = select(Task).where(Task.deletion_requested_at.is_not(None)).order_by(Task.deletion_requested_at)
    if user_id is not None:
        stmt = stmt.where(Task.user_id == user_id)
    return list(session.scalars(stmt))


def resolve_deletion_request(session: Session, admin: User, task_id: int, approve: bool) -> None:
    """Approve (delete the task) or reject (keep it) a pending deletion request.

    Approval is allowed while the month is submitted, since the admin is the
    reviewer, but not once it has been approved.
    """
    if not admin.is_admin:
        raise ServiceError("Only admins can approve deletions.")
    task = session.get(Task, task_id)
    if task is None or not task.deletion_requested_at:
        raise ServiceError("That deletion request no longer exists.")
    if approve:
        if review_state(session, task.user_id, task.month) == APPROVED:
            raise ServiceError(
                f"{month_label(task.month)} is already approved for {task.owner.full_name}. Reopen it first."
            )
        session.delete(task)
    else:
        task.deletion_requested_at = None
        task.deletion_reason = ""
    session.commit()


def save_task_changes(
    session: Session,
    actor: User,
    owner_id: int,
    added: list[dict],
    updated: dict[int, dict],
) -> None:
    """Apply a batch of grid edits atomically: either all of them are saved or none."""
    try:
        for task_id, changes in updated.items():
            update_task(session, task_id, actor, commit=False, **changes)
        for fields in added:
            add_task(session, owner_id, commit=False, **fields)
        session.commit()
    except Exception:
        session.rollback()
        raise


def assign_task(
    session: Session,
    admin: User,
    user_ids: Iterable[int],
    title: str,
    due_date: date | None = None,
    notes: str = "",
    today: date | None = None,
) -> list[Task]:
    if not admin.is_admin:
        raise ServiceError("Only admins can assign tasks.")
    user_ids = list(dict.fromkeys(user_ids))
    if not user_ids:
        raise ServiceError("Choose at least one person.")
    title, _, _ = _clean_task_fields(title, NOT_STARTED, None)
    today = today or date.today()
    if due_date and due_date < today:
        raise ServiceError("Due date can't be in the past.")

    users = [_require_user(session, uid) for uid in user_ids]
    locked = [u.full_name for u in users if is_month_locked(session, u.id, month_key(today))]
    if locked:
        raise ServiceError(
            f"{month_label(month_key(today))} is already submitted for: {', '.join(locked)}. "
            "Send their report back first, or assign later."
        )
    tasks = [
        Task(
            user_id=u.id,
            work_date=today,
            title=title,
            status=NOT_STARTED,
            notes=notes or "",
            due_date=due_date,
            assigned_by=admin.id,
        )
        for u in users
    ]
    session.add_all(tasks)
    session.commit()
    return tasks


def get_assigned_tasks(session: Session, user_id: int | None = None, open_only: bool = False) -> list[Task]:
    stmt = select(Task).where(Task.assigned_by.is_not(None)).order_by(Task.due_date.is_(None), Task.due_date, Task.id)
    if user_id is not None:
        stmt = stmt.where(Task.user_id == user_id)
    if open_only:
        stmt = stmt.where(Task.status != COMPLETED)
    return list(session.scalars(stmt))


def is_overdue(task: Task, today: date | None = None) -> bool:
    return bool(task.due_date and task.status != COMPLETED and task.due_date < (today or date.today()))
