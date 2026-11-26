from collections import defaultdict
from statistics import mean


def build_summary(records):
    approved = [r for r in records if r.status == "Approved"]
    pending = [r for r in records if r.status == "Pending"]
    rejected = [r for r in records if r.status == "Rejected"]
    by_category, by_volunteer, display_name = defaultdict(float), defaultdict(float), {}
    for r in approved:
        by_category[r.category] += r.hours
        key = r.volunteer_name.casefold()          # same person regardless of capitalisation
        display_name.setdefault(key, r.volunteer_name)
        by_volunteer[key] += r.hours
    top = sorted(((display_name[k], round(h, 2)) for k, h in by_volunteer.items()),
                 key=lambda x: (-x[1], x[0]))[:5]
    return {
        "record_count": len(records),
        "volunteer_count": len({r.volunteer_name.casefold() for r in records}),
        "total_hours": round(sum(r.hours for r in approved), 2),
        "pending_hours": round(sum(r.hours for r in pending), 2),
        "approved_count": len(approved), "pending_count": len(pending), "rejected_count": len(rejected),
        "average_hours": round(mean([r.hours for r in approved]), 2) if approved else 0.0,
        "category_totals": {k: round(v, 2) for k, v in sorted(by_category.items())},
        "top_volunteers": top,
    }


def search_records(records, keyword="", category="All", status="All"):
    keyword = keyword.casefold().strip()
    found = []
    for r in records:
        text = " ".join([r.record_id, r.volunteer_name, r.activity, r.category, r.supervisor, r.notes]).casefold()
        if keyword and keyword not in text:
            continue
        if category != "All" and r.category != category:
            continue
        if status != "All" and r.status != status:
            continue
        found.append(r)
    return sorted(found, key=lambda r: (r.service_date, r.volunteer_name.casefold()), reverse=True)


def get_warnings(records):
    warnings = []
    for r in records:
        if r.is_overdue:
            warnings.append(f"OVERDUE: {r.record_id} — {r.volunteer_name}; deadline {r.deadline}.")
        if r.hours > 8:
            warnings.append(f"REVIEW: {r.record_id} — {r.hours:.2f} hours in one session.")
    return warnings
