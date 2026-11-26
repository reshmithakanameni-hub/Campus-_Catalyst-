"""Extra analytics used by the web app: per-volunteer views, trends, goals and certificates."""
from collections import defaultdict
from datetime import date

GOAL_HOURS = 20.0     # approved hours a volunteer needs for a certificate
BADGES = [(100, "Platinum"), (50, "Gold"), (30, "Silver"), (GOAL_HOURS, "Bronze")]


def records_for(records, full_name):
    key = full_name.casefold().strip()
    return [r for r in records if r.volunteer_name.casefold().strip() == key]


def approved_hours(records):
    return round(sum(r.hours for r in records if r.status == "Approved"), 2)


def monthly_hours(records):
    """Approved hours per month, as an ordered {'YYYY-MM': hours} dict."""
    totals = defaultdict(float)
    for r in records:
        if r.status == "Approved":
            totals[r.service_date[:7]] += r.hours
    return {month: round(h, 2) for month, h in sorted(totals.items())}


def leaderboard(records, limit=10):
    names, totals = {}, defaultdict(float)
    for r in records:
        if r.status == "Approved":
            key = r.volunteer_name.casefold()
            names.setdefault(key, r.volunteer_name)
            totals[key] += r.hours
    ranked = sorted(((names[k], round(h, 2)) for k, h in totals.items()), key=lambda x: (-x[1], x[0]))
    return ranked[:limit]


def badge_for(hours):
    for threshold, name in BADGES:
        if hours >= threshold:
            return name
    return "None yet"


def goal_progress(hours, goal=GOAL_HOURS):
    return min(hours / goal, 1.0) if goal else 0.0


def certificate_text(full_name, records, today=None):
    """Plain-text certificate; only possible once the goal is reached."""
    mine = records_for(records, full_name)
    hours = approved_hours(mine)
    if hours < GOAL_HOURS:
        raise ValueError(f"{GOAL_HOURS:g} approved hours are needed for a certificate; "
                         f"{full_name} has {hours:g}.")
    approved = [r for r in mine if r.status == "Approved"]
    first, last = min(r.service_date for r in approved), max(r.service_date for r in approved)
    lines = ["=" * 56, "CAMPUS CATALYST - CERTIFICATE OF VOLUNTEER SERVICE", "=" * 56, "",
             f"This certifies that  {full_name}", "",
             f"completed {hours:g} approved volunteer hours across {len(approved)} sessions",
             f"between {first} and {last}.", f"Badge earned: {badge_for(hours)}", "",
             "Activities:"]
    lines += [f"  - {r.service_date}  {r.activity} ({r.category}) - {r.hours:g} h" for r in
              sorted(approved, key=lambda r: r.service_date)]
    lines += ["", f"Issued on {(today or date.today()).isoformat()}", "=" * 56]
    return "\n".join(lines) + "\n"
