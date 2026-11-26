from datetime import date, datetime
from .models import VolunteerRecord, VALID_STATUSES

CATEGORIES = ["Community Service", "Education", "Environment", "Healthcare",
              "Fundraising", "Campus Support", "Other"]
STATUS_CHOICES = ["Pending", "Approved", "Rejected"]


def clean_text(value, field, limit=120, required=True):
    value = " ".join(str(value or "").strip().split())
    if required and not value:
        raise ValueError(f"{field} cannot be blank.")
    if len(value) > limit:
        raise ValueError(f"{field} must be {limit} characters or fewer.")
    if any(ord(c) < 32 for c in value):
        raise ValueError(f"{field} contains unsupported characters.")
    return value


def valid_category(value):
    """Return the canonical category name (case-insensitive match)."""
    value = clean_text(value, "Category", 40)
    for category in CATEGORIES:
        if category.casefold() == value.casefold():
            return category
    raise ValueError("Choose a valid category: " + ", ".join(CATEGORIES))


def valid_status(value, default="Pending"):
    """Return the canonical status; a blank value falls back to the default."""
    value = clean_text(value or default, "Status", 12)
    for status in STATUS_CHOICES:
        if status.casefold() == value.casefold() and status in VALID_STATUSES:
            return status
    raise ValueError("Status must be Pending, Approved, or Rejected.")


def valid_date(value, field="Date", allow_future=False, optional=False):
    value = str(value or "").strip()
    if optional and not value:
        return ""
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field} must use YYYY-MM-DD format.")
    if not allow_future and parsed > date.today():
        raise ValueError(f"{field} cannot be in the future.")
    return parsed.isoformat()


def valid_time(value, field="Time"):
    try:
        return datetime.strptime(str(value).strip(), "%H:%M").strftime("%H:%M")
    except ValueError:
        raise ValueError(f"{field} must use 24-hour HH:MM format (example: 09:30).")


def calculate_hours(start_time, end_time):
    start = datetime.strptime(valid_time(start_time), "%H:%M")
    end = datetime.strptime(valid_time(end_time), "%H:%M")
    minutes = int((end - start).total_seconds() // 60)
    if minutes == 0:
        raise ValueError("Start and end time cannot be the same.")
    if minutes < 0:                       # overnight shift, e.g. 22:00 -> 02:00 = 4 hours
        minutes += 24 * 60
    if minutes > 720:
        raise ValueError("A single volunteer session cannot exceed 12 hours.")
    return round(minutes / 60, 2)


def validate_record_payload(data):
    name = clean_text(data.get("volunteer_name"), "Volunteer name", 80)
    activity = clean_text(data.get("activity"), "Activity", 120)
    category = valid_category(data.get("category"))
    service_date = valid_date(data.get("service_date"), "Service date")
    start = valid_time(data.get("start_time"), "Start time")
    end = valid_time(data.get("end_time"), "End time")
    hours = calculate_hours(start, end)
    status = valid_status(data.get("status"))
    supervisor = clean_text(data.get("supervisor"), "Supervisor", 80, False)
    notes = clean_text(data.get("notes"), "Notes", 500, False)
    deadline = valid_date(data.get("deadline"), "Deadline", True, True)
    return VolunteerRecord(name, activity, category, service_date, start, end, hours,
                           status, supervisor, notes, deadline, str(data.get("record_id") or ""))
