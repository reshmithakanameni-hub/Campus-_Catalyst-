from pathlib import Path
from datetime import datetime
from .analytics import build_summary


def md_cell(value):
    """Make text safe inside a Markdown table cell."""
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def export_markdown(records, destination):
    s = build_summary(records)
    lines = ["# Campus Catalyst — Volunteer Hours Report",
             f"\nGenerated: {datetime.now():%Y-%m-%d %H:%M}", "\n## Executive summary",
             f"- Total records: {s['record_count']}", f"- Unique volunteers: {s['volunteer_count']}",
             f"- Approved service hours: {s['total_hours']:.2f}", f"- Pending hours: {s['pending_hours']:.2f}",
             f"- Average approved hours per approved record: {s['average_hours']:.2f}",
             f"- Approved / Pending / Rejected: {s['approved_count']} / {s['pending_count']} / {s['rejected_count']}",
             "\n## Approved hours by category", "| Category | Hours |", "|---|---:|"]
    lines += [f"| {md_cell(cat)} | {hours:.2f} |" for cat, hours in s["category_totals"].items()]
    lines += ["\n## Top volunteers", "| Volunteer | Approved hours |", "|---|---:|"]
    lines += [f"| {md_cell(name)} | {hours:.2f} |" for name, hours in s["top_volunteers"]]
    lines += ["\n## Activity records", "| ID | Date | Volunteer | Activity | Category | Hours | Status |",
              "|---|---|---|---|---|---:|---|"]
    for r in sorted(records, key=lambda x: x.service_date, reverse=True):
        lines.append(f"| {r.record_id} | {r.service_date} | {md_cell(r.volunteer_name)} | {md_cell(r.activity)} "
                     f"| {md_cell(r.category)} | {r.hours:.2f} | {r.status} |")
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    Path(destination).write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_text(records, destination):
    s = build_summary(records)
    lines = ["CAMPUS CATALYST — VOLUNTEER HOURS AUDIT", "=" * 48,
             f"Generated: {datetime.now():%Y-%m-%d %H:%M}",
             f"Records: {s['record_count']} | Volunteers: {s['volunteer_count']}",
             f"Approved hours: {s['total_hours']:.2f} | Pending hours: {s['pending_hours']:.2f}",
             f"Average approved hours: {s['average_hours']:.2f}", "", "RECORDS", "-" * 48]
    for r in sorted(records, key=lambda x: x.service_date, reverse=True):
        lines.append(f"{r.record_id} | {r.service_date} | {r.volunteer_name} | {r.activity} | {r.hours:.2f} hrs | {r.status}")
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    Path(destination).write_text("\n".join(lines) + "\n", encoding="utf-8")
