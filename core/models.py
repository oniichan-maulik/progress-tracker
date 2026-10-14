"""Database schema."""

from datetime import date, datetime, timezone

from sqlalchemy import Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

ROLE_ADMIN = "admin"
ROLE_EMPLOYEE = "employee"
ROLES = (ROLE_ADMIN, ROLE_EMPLOYEE)

NOT_STARTED = "Not Started"
IN_PROGRESS = "In Progress"
UNDER_REVIEW = "Under Review"
COMPLETED = "Completed"
STATUSES = (NOT_STARTED, IN_PROGRESS, UNDER_REVIEW, COMPLETED)

DRAFT = "Draft"
SUBMITTED = "Submitted"
APPROVED = "Approved"
CHANGES_REQUESTED = "Changes Requested"
REVIEW_STATES = (DRAFT, SUBMITTED, APPROVED, CHANGES_REQUESTED)
LOCKED_STATES = (SUBMITTED, APPROVED)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default=ROLE_EMPLOYEE)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    work_date: Mapped[date] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(20), default=NOT_STARTED)
    hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    due_date: Mapped[date | None] = mapped_column(nullable=True)
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    deletion_requested_at: Mapped[datetime | None] = mapped_column(nullable=True)
    deletion_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    owner: Mapped[User] = relationship(foreign_keys=[user_id])
    assigner: Mapped[User | None] = relationship(foreign_keys=[assigned_by])

    @property
    def month(self) -> str:
        return self.work_date.strftime("%Y-%m")


class MonthlyReview(Base):
    __tablename__ = "monthly_reviews"
    __table_args__ = (UniqueConstraint("user_id", "month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    month: Mapped[str] = mapped_column(String(7))  # "YYYY-MM"
    state: Mapped[str] = mapped_column(String(20), default=DRAFT)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    submitted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    reviewer: Mapped[User | None] = relationship(foreign_keys=[reviewer_id])
