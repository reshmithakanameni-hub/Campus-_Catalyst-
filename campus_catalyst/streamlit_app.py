"""Campus Catalyst - web app (Streamlit). Pure Python; no HTML/CSS is written.

Run from the project root:  streamlit run streamlit_app.py
Demo admin login: admin / admin123   (volunteers can register on the login screen)

Admins approve/reject hours, edit and delete records, import CSV files and export reports.
Volunteers log their own hours (always Pending until approved), track their goal and earn a certificate.
"""
import tempfile
from datetime import date, time, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from campus_catalyst.analytics import build_summary, get_warnings, search_records
from campus_catalyst.auth import AuthError, UserStore, DEFAULT_ADMIN
from campus_catalyst.insights import (GOAL_HOURS, approved_hours, badge_for, certificate_text,
                                      goal_progress, leaderboard, monthly_hours, records_for)
from campus_catalyst.log import get_logger
from campus_catalyst.reports import export_markdown, export_text
from campus_catalyst.storage import StorageError, SQLiteStorage, VolunteerStorage, merge_records
from campus_catalyst.validators import CATEGORIES, STATUS_CHOICES, validate_record_payload

st.set_page_config(page_title="Campus Catalyst", page_icon="🤝", layout="wide")

ROOT = Path(__file__).resolve().parent
storage = SQLiteStorage(ROOT / "data" / "volunteers.db")
users = UserStore(ROOT / "data" / "users.json")
SAMPLE_CSV = ROOT / "data" / "volunteers.csv"
REPORT_DIR = ROOT / "reports"
log = get_logger("web")          # audit trail: logs/campus_catalyst.log


# ---------------------------------------------------------------- helpers
def load_records():
    """Read from disk on every run so several open browser tabs never overwrite each other."""
    try:
        records = storage.load()
    except StorageError as exc:
        st.error(str(exc))
        return []
    if storage.recovery_message:
        st.warning(storage.recovery_message)
    return records


def save(records):
    try:
        storage.save(records)
        return True
    except StorageError as exc:
        st.error(str(exc))
        return False


def to_frame(records):
    columns = ["record_id", "service_date", "volunteer_name", "activity", "category",
               "start_time", "end_time", "hours", "status", "supervisor", "deadline", "notes"]
    return pd.DataFrame([r.to_dict() for r in records], columns=columns)


def hhmm(text, fallback):
    try:
        return datetime.strptime(text, "%H:%M").time()
    except (ValueError, TypeError):
        return fallback


def activity_form(key, volunteer_name=None, existing=None, admin=False):
    """Shared add/edit form. Returns a validated record on submit, else None."""
    e = existing
    with st.form(key):
        a, b = st.columns(2)
        if volunteer_name:
            a.text_input("Volunteer", value=volunteer_name, disabled=True)
            name = volunteer_name
        else:
            name = a.text_input("Volunteer name *", value=e.volunteer_name if e else "")
        activity = b.text_input("Activity *", value=e.activity if e else "")
        category = a.selectbox("Category *", CATEGORIES, index=CATEGORIES.index(e.category) if e else 0)
        if admin:
            status = b.selectbox("Status", STATUS_CHOICES, index=STATUS_CHOICES.index(e.status) if e else 0)
        else:
            b.text_input("Status", value="Pending (admin approves)", disabled=True)
            status = "Pending"
        service_date = a.date_input("Service date *", max_value=date.today(),
                                    value=date.fromisoformat(e.service_date) if e else date.today())
        supervisor = b.text_input("Supervisor", value=e.supervisor if e else "")
        start = a.time_input("Start time *", value=hhmm(e.start_time, time(9, 0)) if e else time(9, 0))
        end = b.time_input("End time *", value=hhmm(e.end_time, time(11, 0)) if e else time(11, 0))
        notes = st.text_area("Notes", value=e.notes if e else "", max_chars=500)
        submitted = st.form_submit_button("Save changes" if e else "Save record", type="primary")
    if not submitted:
        return None
    payload = {"volunteer_name": name, "activity": activity, "category": category,
               "service_date": service_date.isoformat(), "start_time": start.strftime("%H:%M"),
               "end_time": end.strftime("%H:%M"), "status": status, "supervisor": supervisor,
               "notes": notes, "deadline": e.deadline if e else "",
               "record_id": e.record_id if e else ""}
    try:
        return validate_record_payload(payload)       # same rules as the CLI and Tkinter apps
    except ValueError as exc:
        st.error(str(exc))
        return None


def records_table(found):
    st.dataframe(to_frame(found), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------- admin pages
def admin_dashboard(user, records):
    st.header("Admin Dashboard")
    if not records:
        st.info("No records yet. Import the sample CSV from the Import CSV page.")
        return
    s = build_summary(records)
    c = st.columns(5)
    c[0].metric("Approved hours", f"{s['total_hours']:.2f}")
    c[1].metric("Pending hours", f"{s['pending_hours']:.2f}")
    c[2].metric("Awaiting approval", s["pending_count"])
    c[3].metric("Volunteers", s["volunteer_count"])
    c[4].metric("Avg hours / record", f"{s['average_hours']:.2f}")
    left, right = st.columns(2)
    with left:
        st.subheader("Approved hours by category")
        if s["category_totals"]:
            st.bar_chart(pd.Series(s["category_totals"], name="Hours"))
    with right:
        st.subheader("Approved hours by month")
        trend = monthly_hours(records)
        if trend:
            st.line_chart(pd.Series(trend, name="Hours"))
    n_warn = len(get_warnings(records))
    if n_warn:
        st.warning(f"{n_warn} warnings need attention (see Warnings page).")


def admin_queue(user, records):
    st.header("Approval Queue")
    pending = sorted([r for r in records if r.status == "Pending"], key=lambda r: r.service_date)
    if not pending:
        st.success("Nothing waiting for approval.")
        return
    st.caption(f"{len(pending)} records waiting. Tick the ones to act on.")
    frame = to_frame(pending)[["record_id", "service_date", "volunteer_name", "activity", "hours", "deadline"]]
    frame.insert(0, "select", False)
    edited = st.data_editor(frame, hide_index=True, use_container_width=True,
                            disabled=[c for c in frame.columns if c != "select"], key="queue_editor")
    chosen_ids = set(edited.loc[edited["select"], "record_id"])
    a, b, _ = st.columns([1, 1, 3])
    for label, new_status, col in (("Approve selected", "Approved", a), ("Reject selected", "Rejected", b)):
        if col.button(label, disabled=not chosen_ids):
            for r in records:
                if r.record_id in chosen_ids:
                    r.status = new_status
            if save(records):
                log.info("%s set %d record(s) to %s: %s", user["username"], len(chosen_ids),
                         new_status, ", ".join(sorted(chosen_ids)))
                st.rerun()


def admin_records(user, records):
    st.header("All Records")
    f1, f2, f3 = st.columns([2, 1, 1])
    keyword = f1.text_input("Search", placeholder="name, activity, supervisor, notes, ID")
    category = f2.selectbox("Category", ["All"] + CATEGORIES)
    status = f3.selectbox("Status", ["All"] + STATUS_CHOICES)
    try:    # status/category are filtered by the SQLite indexes; only the keyword scans text
        found = search_records(storage.query(status=status, category=category), keyword)
    except StorageError:
        found = search_records(records, keyword, category, status)
    st.caption(f"{len(found)} of {len(records)} records")
    records_table(found)
    if not found:
        return
    st.subheader("Edit or delete")
    labels = {f"{r.record_id} - {r.volunteer_name} - {r.activity} ({r.service_date})": r for r in found}
    chosen = labels[st.selectbox("Choose record", list(labels))]
    updated = activity_form(f"edit_{chosen.record_id}", existing=chosen, admin=True)
    if updated:
        records[records.index(chosen)] = updated
        if save(records):
            log.info("%s edited record %s", user["username"], chosen.record_id)
            st.success("Record updated.")
            st.rerun()
    confirm = st.checkbox("I want to delete this record")
    if st.button("Delete record", disabled=not confirm):
        records.remove(chosen)
        if save(records):
            log.info("%s deleted record %s", user["username"], chosen.record_id)
            st.rerun()


def admin_add(user, records):
    st.header("Add Activity for a Volunteer")
    record = activity_form("admin_add", admin=True)
    if record:
        merge_records(records, [record])
        if save(records):
            log.info("%s added record %s for %s", user["username"], record.record_id, record.volunteer_name)
            st.success(f"Saved {record.record_id}: {record.hours:.2f} hours for {record.volunteer_name}.")


def admin_import(user, records):
    st.header("Import Dataset (CSV)")
    st.caption("Required columns: volunteer_name, activity, category, service_date, start_time, end_time")
    upload = st.file_uploader("Choose a CSV file", type="csv")
    use_sample = SAMPLE_CSV.is_file() and st.button("Import bundled sample (data/volunteers.csv)")
    if not (upload or use_sample):
        return
    tmp_path = None
    if upload:
        with tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False) as tmp:
            tmp.write(upload.getvalue())
        tmp_path = Path(tmp.name)
    try:
        imported, errors = storage.import_csv(tmp_path or SAMPLE_CSV)
    except StorageError as exc:
        st.error(str(exc))
        return
    finally:
        if tmp_path:
            tmp_path.unlink(missing_ok=True)
    added, duplicates = merge_records(records, imported)
    if save(records):
        st.success(f"Added {len(added)} records, skipped {duplicates} duplicates, "
                   f"rejected {len(errors)} invalid rows.")
    if errors:
        with st.expander("Row error log", expanded=True):
            st.code("\n".join(errors))


def admin_warnings(user, records):
    st.header("Warnings")
    warnings = get_warnings(records)
    if not warnings:
        st.success("No overdue deadlines or unusually long sessions.")
    for w in warnings:
        (st.error if w.startswith("OVERDUE") else st.warning)(w)


def admin_users(user, records):
    st.header("Users")
    st.dataframe(pd.DataFrame([{"username": u, "full_name": d["full_name"], "role": d["role"]}
                               for u, d in users.users.items()]), hide_index=True, use_container_width=True)
    st.subheader("Create an account")
    with st.form("new_user"):
        a, b = st.columns(2)
        username, full_name = a.text_input("Username"), b.text_input("Full name")
        password, role = a.text_input("Password", type="password"), b.selectbox("Role", ["volunteer", "admin"])
        if st.form_submit_button("Create user"):
            try:
                users.create_user(username, password, full_name, role)
                st.success("User created.")
                st.rerun()
            except AuthError as exc:
                st.error(str(exc))


def admin_export(user, records):
    st.header("Export Reports")
    if not records:
        st.info("Nothing to export yet.")
        return
    paths = {n: REPORT_DIR / n for n in ("volunteer_report.md", "volunteer_audit.txt", "volunteer_records.csv")}
    export_markdown(records, paths["volunteer_report.md"])
    export_text(records, paths["volunteer_audit.txt"])
    VolunteerStorage.export_csv(records, paths["volunteer_records.csv"])
    st.caption(f"Copies are also saved in the {REPORT_DIR.name}/ folder.")
    mimes = {"md": "text/markdown", "txt": "text/plain", "csv": "text/csv"}
    for name, path in paths.items():
        st.download_button(f"Download {name}", path.read_bytes(), file_name=name,
                           mime=mimes[name.rsplit('.', 1)[1]])


# ---------------------------------------------------------------- volunteer pages
def vol_dashboard(user, records):
    mine = records_for(records, user["full_name"])
    hours = approved_hours(mine)
    st.header(f"Welcome, {user['full_name']}")
    c = st.columns(4)
    c[0].metric("Approved hours", f"{hours:.2f}")
    c[1].metric("Pending hours", f"{sum(r.hours for r in mine if r.status == 'Pending'):.2f}")
    c[2].metric("Sessions", len(mine))
    c[3].metric("Badge", badge_for(hours))
    st.progress(goal_progress(hours), text=f"Goal: {hours:g} / {GOAL_HOURS:g} approved hours for a certificate")
    trend = monthly_hours(mine)
    if trend:
        st.subheader("My approved hours by month")
        st.bar_chart(pd.Series(trend, name="Hours"))
    else:
        st.info("No approved hours yet. Log your first activity on the Log Hours page.")
    try:
        text = certificate_text(user["full_name"], records)
        st.download_button("🎓 Download my certificate", text, file_name="certificate.txt")
    except ValueError as exc:
        st.caption(str(exc))


def vol_log(user, records):
    st.header("Log Volunteer Hours")
    st.caption("New entries start as Pending until an admin approves them.")
    record = activity_form("vol_add", volunteer_name=user["full_name"])
    if record:
        added, dup = merge_records(records, [record])
        if dup:
            st.warning("You already logged this exact session.")
        elif save(records):
            st.success(f"Saved {record.hours:.2f} hours. Waiting for approval.")


def vol_records(user, records):
    st.header("My Records")
    mine = sorted(records_for(records, user["full_name"]), key=lambda r: r.service_date, reverse=True)
    if not mine:
        st.info("No records yet.")
        return
    records_table(mine)
    deletable = {f"{r.record_id} - {r.activity} ({r.service_date})": r for r in mine if r.status == "Pending"}
    if deletable:
        st.subheader("Withdraw a pending entry")
        chosen = deletable[st.selectbox("Choose entry", list(deletable))]
        if st.button("Withdraw entry"):
            records.remove(chosen)
            if save(records):
                log.info("%s withdrew record %s", user["username"], chosen.record_id)
                st.rerun()


# ---------------------------------------------------------------- shared pages
def page_leaderboard(user, records):
    st.header("Leaderboard")
    ranked = leaderboard(records, 10)
    if not ranked:
        st.info("No approved hours yet.")
        return
    frame = pd.DataFrame(ranked, columns=["Volunteer", "Approved hours"])
    frame.insert(0, "Rank", range(1, len(frame) + 1))
    frame["Badge"] = frame["Approved hours"].map(badge_for)
    st.dataframe(frame, hide_index=True, use_container_width=True)
    st.bar_chart(frame.set_index("Volunteer")["Approved hours"])


def page_account(user, records):
    st.header("My Account")
    st.write(f"**{user['full_name']}** (`{user['username']}`), role: **{user['role']}**")
    with st.form("pw"):
        old = st.text_input("Current password", type="password")
        new = st.text_input("New password (6+ characters)", type="password")
        if st.form_submit_button("Change password"):
            try:
                users.change_password(user["username"], old, new)
                st.success("Password changed.")
            except AuthError as exc:
                st.error(str(exc))


ADMIN_PAGES = {"Dashboard": admin_dashboard, "Approval Queue": admin_queue, "All Records": admin_records,
               "Add Activity": admin_add, "Import CSV": admin_import, "Warnings": admin_warnings,
               "Leaderboard": page_leaderboard, "Users": admin_users, "Export": admin_export,
               "My Account": page_account}
VOLUNTEER_PAGES = {"My Dashboard": vol_dashboard, "Log Hours": vol_log, "My Records": vol_records,
                   "Leaderboard": page_leaderboard, "My Account": page_account}


# ---------------------------------------------------------------- login
def login_screen():
    st.title("🤝 Campus Catalyst")
    st.caption("Volunteer hours tracker for campus service")
    tab_in, tab_up = st.tabs(["Log in", "Register as volunteer"])
    with tab_in:
        with st.form("login"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Log in", type="primary"):
                try:
                    st.session_state.user = users.authenticate(username, password)
                    log.info("Login OK: %s", username)
                    st.rerun()
                except AuthError as exc:
                    log.warning("Login failed for username %r", username)
                    st.error(str(exc))
        st.caption(f"Demo admin account: `{DEFAULT_ADMIN[0]}` / `{DEFAULT_ADMIN[1]}`")
    with tab_up:
        with st.form("register"):
            full_name = st.text_input("Full name (as it should appear on records)")
            username = st.text_input("Choose a username")
            password = st.text_input("Choose a password (6+ characters)", type="password")
            if st.form_submit_button("Create account"):
                try:
                    users.create_user(username, password, full_name, "volunteer")
                    log.info("New volunteer account: %s", username)
                    st.success("Account created. Switch to the Log in tab.")
                except AuthError as exc:
                    st.error(str(exc))


# ---------------------------------------------------------------- app
user = st.session_state.get("user")
if not user:
    login_screen()
    st.stop()

pages = ADMIN_PAGES if user["role"] == "admin" else VOLUNTEER_PAGES
st.sidebar.title("🤝 Campus Catalyst")
st.sidebar.caption(f"{user['full_name']} · {user['role']}")
choice = st.sidebar.radio("Go to", list(pages))
if st.sidebar.button("Log out"):
    log.info("Logout: %s", user["username"])
    st.session_state.pop("user", None)
    st.rerun()
pages[choice](user, load_records())
