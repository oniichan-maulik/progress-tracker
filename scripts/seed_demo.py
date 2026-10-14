"""Fill the database with a fictional demo team for screenshots and live demos.

    python -m scripts.seed_demo            # adds demo data to an empty database
    python -m scripts.seed_demo --reset    # DELETES all data first

Demo logins (all passwords are "demo1234"): admin, priya, rahul, sara, tom
"""

import argparse
import random
import sys
from datetime import date, timedelta

from sqlalchemy import func, select

from core import services as svc
from core.config import database_url
from core.db import init_db, make_engine
from core.models import COMPLETED, IN_PROGRESS, NOT_STARTED, ROLE_ADMIN, ROLE_EMPLOYEE, UNDER_REVIEW, Base, Task, User
from sqlalchemy.orm import sessionmaker

PASSWORD = "demo1234"
TEAM = [("priya", "Priya Sharma"), ("rahul", "Rahul Mehta"), ("sara", "Sara Khan"), ("tom", "Tom Fernandes")]
WORK = [
    "Prepare weekly client update",
    "Fix login timeout bug",
    "Review pull requests",
    "Update inventory spreadsheet",
    "Write API documentation",
    "Design onboarding email",
    "Clean up customer database",
    "Prepare monthly sales deck",
    "Test new checkout flow",
    "Research competitor pricing",
    "Migrate reports to new template",
    "Team sync and planning",
    "Optimise slow dashboard query",
    "Draft vendor contract summary",
]


def seed(session, today: date, rng: random.Random) -> None:
    admin = svc.create_user(session, "admin", "Anita Desai", PASSWORD, ROLE_ADMIN)
    employees = [svc.create_user(session, u, n, PASSWORD, ROLE_EMPLOYEE) for u, n in TEAM]
    months = list(reversed(svc.recent_months(4, today=today)))

    for month in months:
        first, last = svc.month_bounds(month)
        last = min(last, today)
        current = month == svc.month_key(today)
        for emp in employees:
            day = first
            while day <= last:
                if day.weekday() < 5 and rng.random() < 0.45:
                    recent = current and (today - day).days < 5
                    status = rng.choice([IN_PROGRESS, UNDER_REVIEW, NOT_STARTED]) if recent else (
                        COMPLETED if rng.random() < 0.85 else UNDER_REVIEW
                    )
                    hours = round(rng.choice([0.5, 1, 1.5, 2, 3, 4, 6]), 2) if status != NOT_STARTED else None
                    svc.add_task(session, emp.id, day, rng.choice(WORK), status, hours, commit=False)
                day += timedelta(days=1)
            session.commit()
            if not current:
                svc.submit_month(session, emp.id, month)
                if month != months[-2] or emp is not employees[0]:
                    svc.review_month(session, admin, emp.id, month, approve=True, comment=rng.choice(["Good work.", "", "Thanks!"]))

    # Leave one report waiting for review, and assign some open work.
    if today.day > 3:
        svc.submit_month(session, employees[1].id, svc.month_key(today))
    others = [e.id for e in employees if e is not employees[1]]
    svc.assign_task(session, admin, others[:2], "Quarterly security training", due_date=today + timedelta(days=7), today=today)
    svc.assign_task(session, admin, [others[2]], "Update client contact list", due_date=today + timedelta(days=3), today=today)
    sara_task = session.scalars(
        select(Task).where(Task.user_id == employees[2].id, Task.assigned_by.is_(None)).order_by(Task.id.desc())
    ).first()
    if sara_task:  # one pending deletion request for the admin to handle
        svc.request_deletion(session, sara_task.id, employees[2], "Logged twice by mistake")
    overdue = session.scalars(select(Task).where(Task.user_id == others[0], Task.status != COMPLETED)).first()
    if overdue:  # make one assigned task overdue so the warning shows up
        overdue.assigned_by, overdue.due_date = admin.id, today - timedelta(days=2)
        session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="drop ALL existing data before seeding")
    args = parser.parse_args()

    url = database_url()
    engine = make_engine(url)
    if args.reset:
        Base.metadata.drop_all(engine)
    init_db(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        if session.scalar(select(func.count()).select_from(User)):
            sys.exit("Database already has users. Use --reset to wipe it and seed demo data.")
        seed(session, date.today(), random.Random(42))
    print(f"Demo data written to {url.split('@')[-1]}")
    print(f"Log in as admin / {PASSWORD}  (employees: {', '.join(u for u, _ in TEAM)})")


if __name__ == "__main__":
    main()
