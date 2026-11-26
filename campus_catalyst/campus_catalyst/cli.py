import os
import sys
from pathlib import Path
from datetime import date

from .validators import (CATEGORIES, STATUS_CHOICES, clean_text, valid_category, valid_date,
                         valid_time, valid_status, calculate_hours, validate_record_payload)
from .analytics import build_summary, search_records, get_warnings
from .storage import SQLiteStorage, VolunteerStorage, StorageError, merge_records
from .reports import export_markdown, export_text

PAGE_SIZE = 15

if os.name == "nt":
    os.system("")  # enables ANSI colour codes in the Windows console


class Style:
    RESET = "\033[0m"; BOLD = "\033[1m"; CYAN = "\033[96m"; GREEN = "\033[92m"
    YELLOW = "\033[93m"; RED = "\033[91m"; MUTED = "\033[90m"


def paint(text, color):
    if os.getenv("NO_COLOR") or not sys.stdout.isatty():
        return str(text)
    return f"{color}{text}{Style.RESET}"


def divider():
    print(paint("  " + "─" * 66, Style.MUTED))


def ask(prompt, default=""):
    answer = input(f"  {prompt}" + (f" [{default}]" if default else "") + ": ").strip()
    return answer or default


def ask_valid(prompt, check, default=""):
    """Keep asking until `check` accepts the answer (it raises ValueError when invalid)."""
    while True:
        try:
            return check(ask(prompt, default))
        except ValueError as exc:
            print(paint(f"  ✗ {exc} Please try again.", Style.RED))


def paginate(items, size=PAGE_SIZE):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def banner():
    print("\n" + paint("  C A M P U S   C A T A L Y S T", Style.CYAN + Style.BOLD))
    print(paint("  VOLUNTEER HOURS TRACKER  •  v1.0", Style.MUTED))
    print(paint("  " + "═" * 66, Style.MUTED))


def pause():
    input("\n  Press Enter to continue...")


def add_record(records, storage):
    print(paint("\n  NEW VOLUNTEER ENTRY", Style.CYAN + Style.BOLD))
    print(paint("  Each field is checked as you type; invalid answers are asked again.", Style.MUTED))
    name = ask_valid("Volunteer name", lambda v: clean_text(v, "Volunteer name", 80))
    activity = ask_valid("Activity performed", lambda v: clean_text(v, "Activity", 120))
    print("  Categories: " + " / ".join(CATEGORIES))
    category = ask_valid("Category", valid_category)
    service_date = ask_valid("Service date YYYY-MM-DD", lambda v: valid_date(v, "Service date"),
                             date.today().isoformat())
    start = ask_valid("Start time HH:MM", lambda v: valid_time(v, "Start time"))
    while True:
        end = ask_valid("End time HH:MM", lambda v: valid_time(v, "End time"))
        try:
            calculate_hours(start, end)
            break
        except ValueError as exc:
            print(paint(f"  ✗ {exc} Please try again.", Style.RED))
    status = ask_valid("Status (" + " / ".join(STATUS_CHOICES) + ")", valid_status, "Pending")
    supervisor = ask_valid("Supervisor (optional)", lambda v: clean_text(v, "Supervisor", 80, False))
    notes = ask_valid("Notes (optional)", lambda v: clean_text(v, "Notes", 500, False))
    deadline = ask_valid("Approval deadline YYYY-MM-DD (optional)",
                         lambda v: valid_date(v, "Deadline", True, True))
    record = validate_record_payload({
        "volunteer_name": name, "activity": activity, "category": category,
        "service_date": service_date, "start_time": start, "end_time": end,
        "status": status, "supervisor": supervisor, "notes": notes, "deadline": deadline,
    })
    records.append(record)
    storage.save(records)
    print(paint(f"  ✓ Saved {record.record_id}: {record.hours:.2f} hours.", Style.GREEN))


def show_records(records, page_size=PAGE_SIZE):
    print(paint("\n  VOLUNTEER RECORDS", Style.CYAN + Style.BOLD))
    if not records:
        print("  No records match your search.")
        return
    pages = list(paginate(records, page_size))
    shown = 0
    for number, page in enumerate(pages, 1):
        print(f"  {'ID':<9} {'DATE':<12} {'VOLUNTEER':<20} {'HOURS':>7}  {'STATUS':<9} ACTIVITY")
        divider()
        for r in page:
            print(f"  {r.record_id:<9} {r.service_date:<12} {r.volunteer_name[:19]:<20} "
                  f"{r.hours:>6.2f}  {r.status:<9} {r.activity[:24]}")
        shown += len(page)
        print(paint(f"  Showing {shown} of {len(records)} record(s).", Style.MUTED))
        if number < len(pages):
            more = input(f"  Page {number}/{len(pages)} — press Enter for next page, or Q to stop: ")
            if more.strip().lower() == "q":
                break
            print()


def dashboard(records):
    s = build_summary(records)
    print(paint("\n  EXECUTIVE DASHBOARD", Style.CYAN + Style.BOLD)); divider()
    print(f"  Total records       {s['record_count']}")
    print(f"  Unique volunteers   {s['volunteer_count']}")
    print("  Approved hours      " + paint(f"{s['total_hours']:.2f}", Style.GREEN + Style.BOLD))
    print("  Pending hours       " + paint(f"{s['pending_hours']:.2f}", Style.YELLOW))
    print(f"  Average per approved record  {s['average_hours']:.2f}")
    print(f"  Status counts       Approved {s['approved_count']} | Pending {s['pending_count']} | Rejected {s['rejected_count']}")
    print("\n  APPROVED HOURS BY CATEGORY")
    if not s["category_totals"]:
        print("  No approved hours to summarize yet.")
    for category, hours in s["category_totals"].items():
        print(f"  {category:<20} {hours:>7.2f}  " + paint("█" * min(30, int(hours)), Style.CYAN))
    print("\n  TOP VOLUNTEERS")
    for name, hours in s["top_volunteers"]:
        print(f"  • {name}: {hours:.2f} hrs")


def find_record(records, rid):
    return next((r for r in records if r.record_id == rid.strip().upper()), None)


def edit_status(records, storage):
    record = find_record(records, ask("Record ID"))
    if not record:
        print(paint("  Record not found.", Style.RED)); return
    print(f"  {record.volunteer_name} — {record.activity} — {record.status}")
    record.status = ask_valid("New status (" + " / ".join(STATUS_CHOICES) + ")",
                              lambda v: valid_status(v, record.status))
    storage.save(records)
    print(paint("  ✓ Status updated.", Style.GREEN))


def delete_record(records, storage):
    record = find_record(records, ask("Record ID to delete"))
    if not record:
        print(paint("  Record not found.", Style.RED)); return
    if ask(f"Type DELETE to remove {record.volunteer_name}'s record") == "DELETE":
        records.remove(record)
        storage.save(records)
        print(paint("  ✓ Record deleted.", Style.GREEN))
    else:
        print("  Deletion cancelled.")


def import_dataset(records, storage):
    path = ask("CSV path", "data/volunteers.csv")
    imported, errors = storage.import_csv(path)
    added, duplicates = merge_records(records, imported)
    storage.save(records)
    print(paint(f"  Imported {len(added)} new valid row(s).", Style.GREEN))
    if duplicates:
        print(paint(f"  {duplicates} row(s) already in your records were skipped as duplicates.", Style.MUTED))
    if errors:
        print(paint(f"  {len(errors)} invalid row(s) skipped:", Style.YELLOW))
        for error in errors[:30]:
            print("  • " + error)
        if len(errors) > 30:
            print(f"  ... and {len(errors) - 30} more invalid rows.")


def export_reports(records):
    if not records:
        print("  No records to export."); return
    Path("reports").mkdir(exist_ok=True)
    export_markdown(records, "reports/volunteer_summary.md")
    export_text(records, "reports/volunteer_audit.txt")
    VolunteerStorage.export_csv(records, "reports/volunteer_records.csv")
    print(paint("  ✓ Markdown, TXT and CSV reports saved in reports/.", Style.GREEN))


def search_menu(records):
    keyword = ask("Keyword (name, activity, ID, supervisor)")
    category = ask("Category or All", "All")
    status = ask("Status or All", "All")
    if category.casefold() == "all":
        category = "All"
    else:
        try:
            category = valid_category(category)
        except ValueError:
            print(paint("  Unknown category — showing all categories.", Style.YELLOW)); category = "All"
    if status.casefold() == "all":
        status = "All"
    else:
        try:
            status = valid_status(status)
        except ValueError:
            print(paint("  Unknown status — showing all statuses.", Style.YELLOW)); status = "All"
    show_records(search_records(records, keyword, category, status))


MENU = """
  1  Add volunteer activity
  2  View all records
  3  Search and filter records
  4  Executive dashboard
  5  Update approval status
  6  Delete a record
  7  Import bulk CSV dataset
  8  View deadline and hour warnings
  9  Export reports (Markdown / TXT / CSV)
  0  Save and exit
"""


def run():
    storage = SQLiteStorage()
    try:
        records = storage.load()
    except StorageError as exc:
        print(paint(f"Could not load saved data: {exc}", Style.RED)); return
    try:
        while True:
            banner()
            if storage.recovery_message:
                print(paint("  ⚠ " + storage.recovery_message, Style.YELLOW))
                storage.recovery_message = ""
            warnings = get_warnings(records)
            print(f"  Welcome! {len(records)} record(s) loaded.")
            if warnings:
                print(paint(f"  ⚠ {len(warnings)} attention warning(s) — see option 8.", Style.YELLOW))
            print(MENU)
            choice = input("  Select an option: ").strip()
            try:
                if choice == "1": add_record(records, storage)
                elif choice == "2": show_records(search_records(records))
                elif choice == "3": search_menu(records)
                elif choice == "4": dashboard(records)
                elif choice == "5": edit_status(records, storage)
                elif choice == "6": delete_record(records, storage)
                elif choice == "7": import_dataset(records, storage)
                elif choice == "8":
                    print(paint("\n  DATA QUALITY & DEADLINE WARNINGS", Style.CYAN + Style.BOLD))
                    if warnings:
                        for warning in warnings:
                            print("  • " + warning)
                    else:
                        print(paint("  ✓ No overdue approvals or long sessions.", Style.GREEN))
                elif choice == "9": export_reports(records)
                elif choice == "0":
                    storage.save(records)
                    print(paint("\n  All changes saved. Thank you for supporting your community!\n", Style.GREEN))
                    break
                else:
                    print(paint("  Choose a valid menu option.", Style.YELLOW))
            except (ValueError, StorageError, OSError) as exc:
                print(paint(f"  ✗ {exc}", Style.RED))
            pause()
    except (KeyboardInterrupt, EOFError):
        try:
            storage.save(records)
            print(paint("\n\n  Interrupted — your records were saved. Goodbye!\n", Style.YELLOW))
        except StorageError as exc:
            print(paint(f"\n  Could not save on exit: {exc}", Style.RED))
