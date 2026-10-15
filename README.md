# Progress Tracker

A small-team progress reporting app. Employees log daily tasks in an Excel-like grid, review their month week by week, and submit it; the head team assigns work, reviews and approves monthly reports, and exports everything to styled Excel workbooks.

Built for organisations of ~1-10 people. Runs locally on SQLite, or online for free on Streamlit Community Cloud + Supabase Postgres - same code, one setting.

![tests](https://github.com/oniichan-maulik/progress-tracker/actions/workflows/tests.yml/badge.svg)

## Features

**Employees**
- Create their own tasks (an "Add a task" form, or new rows straight in the grid)
- Excel-style grid: **Date · Task · Status · Hours · Notes**, edited inline
- Deleting a task needs admin approval: employees send a deletion request with a reason
- Change their own password from **My account**
- Status workflow: `Not Started → In Progress → Under Review → Completed` (completed tasks require hours)
- Weekly breakdown of each month with per-week subtotals
- "Assigned to you" panel with due dates and overdue warnings
- Submit the month for review; it locks until approved or sent back
- Download the month as a formatted `.xlsx`

**Admins (head team)**
- Team dashboard: tasks, completion rate, hours and review state per employee
- Charts: hours by employee, status breakdown, 6-month trend
- Approve reports or request changes with a comment; reopen approved months
- Approve or reject employees' task deletion requests
- Assign tasks (to one or many employees) with optional due dates; track and remove them
- Manage users: create accounts, reset passwords, change roles, deactivate, or permanently delete (with a typed-username confirmation)
- Assign tasks to themselves too, and log their own work under **My report**
- Export one employee's month, or the whole team (one sheet per employee)

**Under the hood**
- bcrypt-hashed passwords, no public sign-up (first run creates the admin)
- Business rules live in a UI-independent service layer; grid saves are atomic
- 47 pytest tests including headless UI tests via Streamlit `AppTest`; CI on GitHub Actions

## Architecture

```mermaid
flowchart LR
    UI["Streamlit pages<br/>views/"] --> SVC["Service layer<br/>core/services.py<br/>(rules, permissions, locking)"]
    UI --> RPT["Reports<br/>core/reports.py<br/>(pandas, openpyxl)"]
    SVC --> ORM["SQLAlchemy models<br/>core/models.py"]
    ORM --> DB[("SQLite (local)<br/>or Postgres (Supabase)")]
```

| Table | Purpose |
|---|---|
| `users` | username, full name, bcrypt hash, role (`admin`/`employee`), active flag |
| `tasks` | owner, date, task, status, hours, notes, `assigned_by`, `due_date`, deletion request fields |
| `monthly_reviews` | per employee per month: `Draft` / `Submitted` / `Approved` / `Changes Requested`, reviewer, comment |

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
streamlit run app.py
```

Open http://localhost:8501. On first launch you'll be asked to create the admin account. Data is stored in `data/progress.db`.

**Demo data** (fictional team, for screenshots):

```bash
python -m scripts.seed_demo            # into an empty database
python -m scripts.seed_demo --reset    # wipes ALL data first
```

Log in as `admin` / `demo1234` (employees: `priya`, `rahul`, `sara`, `tom` - same password).

**Tests:** `pytest`

## Configuration

Settings come from environment variables or `.streamlit/secrets.toml` (see `secrets.toml.example`):

| Setting | Default | |
|---|---|---|
| `ORG_NAME` | `My Organization` | Shown in the title and Excel reports |
| `DATABASE_URL` | `sqlite:///data/progress.db` | Any SQLAlchemy URL; `postgres://` is accepted |

## Deploy free online (Streamlit Cloud + Supabase)

Streamlit Cloud's disk is wiped on restart, so the online version keeps its data in Postgres.

1. **Supabase:** create a free project → *Project settings → Database → Connection string*, copy the **Session pooler** URI and put your database password in it.
2. **GitHub:** push this repo (public or private).
3. **Streamlit Cloud:** *New app* → pick the repo, main file `app.py`, Python 3.11 → *Advanced settings → Secrets*:
   ```toml
   ORG_NAME = "Acme Corp"
   DATABASE_URL = "postgresql://postgres.xxxx:PASSWORD@aws-0-region.pooler.supabase.com:5432/postgres"
   ```
4. Deploy. Tables are created automatically; the first visitor creates the admin account - **do this right away** so nobody else can.

## Docker

```bash
docker build -t progress-tracker .
docker run -p 8501:8501 -v progress-data:/app/data progress-tracker
# or point at Postgres:  -e DATABASE_URL=postgresql://...
```

## Project layout

```
app.py                  login, first-run setup, role-based navigation
core/                   config, models, db, auth, services (rules), reports (Excel)
views/                  my_report, team_review, assign_tasks, manage_users, charts
scripts/seed_demo.py    demo data
tests/                  service, report and UI tests
```
