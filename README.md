# 🤝 Campus Catalyst — Volunteer Hours Tracker


A Python application for logging, approving and reporting student volunteer hours. It has a **Streamlit web app** (best for demos), a **Tkinter desktop app** and a **terminal (CLI) app**. All three share one tested core.

## ✨ Features
- **Roles and login:** admins approve or reject hours; volunteers log their own hours, which start as *Pending*. Passwords are stored as salted PBKDF2 hashes.
- **Full CRUD:** add, view, edit, delete (with confirmation) and withdraw records.
- **Search and filters** by keyword, category and status.
- **Analytics dashboard:** approved and pending hours, averages, category totals, monthly trend and leaderboard.
- **Volunteer goals:** progress towards 20 approved hours, badges and a downloadable certificate.
- **Bulk CSV import** with row-level error messages and automatic duplicate skipping.
- **Warnings** for overdue deadlines and unusually long sessions.
- **Reports:** export Markdown, TXT and CSV.
- **Strong validation:** names, categories, dates (no future dates), 24-hour times, and sessions of up to 12 hours. **Overnight shifts** are supported (22:00 → 02:00 = 4 h).
- **Reliable storage:** SQLite with indexes and atomic transactions. A failed save rolls back, and old JSON data migrates automatically.
- **Audit logging** with Python's `logging` module (rotating file in `logs/`).
- **Automated tests and CI** (GitHub Actions).

## 🚀 Quick start (web app)
```bash
git clone https://github.com/reshmithakanameni-hub/Campus_Catalyst-.git
cd Campus_Catalyst-/campus_catalyst
pip install -r requirements.txt
streamlit run streamlit_app.py
```
Open the link Streamlit prints (usually http://localhost:8501).

**Demo login:** `admin` / `admin123`. You can also register a volunteer account on the login screen.

| Role | Can do |
|---|---|
| **Admin** | Dashboard, approval queue (bulk approve/reject), search/edit/delete, add activity for anyone, import CSV, warnings, create users, export reports |
| **Volunteer** | Personal dashboard, goal progress, badges, log hours, withdraw pending entries, leaderboard, certificate |

A volunteer's records are matched by their registered full name.

## 🖥️ Other interfaces
```bash
python main.py          # Tkinter desktop app (falls back to CLI if Tkinter is missing)
python main.py --cli    # terminal menu
```
Tkinter comes with most Python installs. On some Linux systems install `python3-tk`.

## 📥 Sample data
| File | Purpose |
|---|---|
| `data/volunteers.csv` | 44 rows: 38 valid and 6 deliberately invalid, to show the import error log |
| `data/sample_volunteers.json` | The 38 valid records as JSON |
| `data/volunteers.db` | Working database, created at runtime (not committed) |

**CSV format.** Required columns: `volunteer_name, activity, category, service_date, start_time, end_time`. Optional: `status, supervisor, notes, deadline`. Dates are `YYYY-MM-DD`, times are `HH:MM`. Hours are always calculated from the times, never trusted from the file.

Categories: Community Service, Education, Environment, Healthcare, Fundraising, Campus Support, Other.

## 📏 Business rules
- Only **Approved** hours count towards totals and rankings; Pending hours are shown separately; Rejected records are kept for audit.
- A session must be longer than 0 and at most 12 hours. Sessions over 8 hours are flagged for review.
- Service dates cannot be in the future.
- Pending records past their deadline are flagged as overdue.
- Names are grouped case-insensitively.

## 🏗️ Architecture
```text
UI layer        streamlit_app.py · gui.py (Tkinter) · cli.py
Business layer  validators.py · analytics.py · insights.py · auth.py · reports.py
Data layer      models.py · storage.py (SQLiteStorage, JSON import/export) · log.py
```
```text
campus_catalyst/
├── main.py                    launcher (desktop / CLI)
├── streamlit_app.py           web app
├── campus_catalyst/           core package
│   ├── models.py  validators.py  storage.py  auth.py
│   ├── analytics.py  insights.py  reports.py  log.py
│   └── cli.py  gui.py
├── data/                      sample CSV/JSON
├── reports/                   generated exports
├── tests/                     unit tests
├── .github/workflows/tests.yml  CI
└── requirements.txt
```
The UI layers never touch the database directly; they go through the validators and storage classes, so the rules are enforced the same way everywhere.

## 🧪 Tests
```bash
python -m unittest discover -s tests -v
```
56 tests cover validation, hour calculation (including overnight), storage, SQLite rollback and migration, CSV import, authentication, analytics and reports. GitHub Actions runs them on every push.

## 🎬 Suggested demo (5–7 min)
1. Run `streamlit run streamlit_app.py` and log in as admin.
2. Import `data/volunteers.csv` and show the error log for the 6 invalid rows.
3. Open the dashboard; explain approved vs pending hours.
4. Approve a few entries from the approval queue.
5. Register a volunteer, log hours, and show goal progress and the certificate.
6. Show a validation error (future date or 13-hour session) and the exported report.

## 🔭 Future work
Multi-user concurrency with a server database (PostgreSQL), email notifications for approvals, and role-based permissions for supervisors.
