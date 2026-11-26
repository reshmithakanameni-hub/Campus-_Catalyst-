import csv
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from campus_catalyst.analytics import build_summary, get_warnings, search_records
from campus_catalyst.cli import paginate
from campus_catalyst.reports import export_markdown, md_cell
from campus_catalyst.storage import VolunteerStorage, StorageError, merge_records
from campus_catalyst.validators import calculate_hours, validate_record_payload

ROOT = Path(__file__).resolve().parent.parent
CSV_HEADER = ["volunteer_name", "activity", "category", "service_date", "start_time", "end_time",
              "status", "supervisor", "notes", "deadline"]


def sample(**changes):
    data = {"volunteer_name": "Aarav Sharma", "activity": "Library mentoring",
            "category": "Education", "service_date": date.today().isoformat(),
            "start_time": "09:00", "end_time": "11:30", "status": "Approved",
            "supervisor": "Ms. Rao", "notes": "", "deadline": ""}
    data.update(changes)
    return validate_record_payload(data)


def write_csv(folder, rows, header=CSV_HEADER):
    path = Path(folder) / "import.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return path


class ValidatorTests(unittest.TestCase):
    def test_hours(self): self.assertEqual(calculate_hours("09:00", "11:30"), 2.5)

    def test_boundary_twelve_hours_allowed(self): self.assertEqual(calculate_hours("08:00", "20:00"), 12.0)

    def test_end_before_start(self):
        with self.assertRaises(ValueError): calculate_hours("11:00", "10:00")

    def test_blank_name(self):
        with self.assertRaises(ValueError): sample(volunteer_name=" ")

    def test_invalid_status(self):
        with self.assertRaises(ValueError): sample(status="Done")

    def test_blank_status_defaults_to_pending(self):
        self.assertEqual(sample(status="").status, "Pending")

    def test_status_and_category_case_insensitive(self):
        record = sample(status="approved", category="education")
        self.assertEqual((record.status, record.category), ("Approved", "Education"))

    def test_overlong_session(self):
        with self.assertRaises(ValueError): calculate_hours("06:00", "19:00")

    def test_future_date_rejected(self):
        with self.assertRaises(ValueError):
            sample(service_date=(date.today() + timedelta(days=1)).isoformat())

    def test_bad_time_format(self):
        with self.assertRaises(ValueError): sample(start_time="9am")


class AnalyticsTests(unittest.TestCase):
    def test_approved_and_pending_totals(self):
        s = build_summary([sample(), sample(status="Pending")])
        self.assertEqual(s["record_count"], 2)
        self.assertEqual(s["total_hours"], 2.5)
        self.assertEqual(s["pending_hours"], 2.5)

    def test_keyword_search(self):
        self.assertEqual(len(search_records([sample(), sample(volunteer_name="Diya Patel")], "diya")), 1)

    def test_category_and_status_filters(self):
        records = [sample(), sample(category="Healthcare", status="Pending")]
        self.assertEqual(len(search_records(records, category="Healthcare")), 1)
        self.assertEqual(len(search_records(records, status="Approved")), 1)

    def test_top_volunteers_ignore_name_capitalisation(self):
        s = build_summary([sample(volunteer_name="Aarav Sharma"), sample(volunteer_name="aarav sharma")])
        self.assertEqual(s["volunteer_count"], 1)
        self.assertEqual(len(s["top_volunteers"]), 1)
        self.assertEqual(s["top_volunteers"][0][1], 5.0)

    def test_empty_summary(self):
        s = build_summary([])
        self.assertEqual((s["total_hours"], s["average_hours"]), (0.0, 0.0))


class WarningTests(unittest.TestCase):
    def yesterday(self): return (date.today() - timedelta(days=1)).isoformat()

    def test_pending_past_deadline_is_overdue(self):
        self.assertTrue(sample(status="Pending", deadline=self.yesterday()).is_overdue)

    def test_approved_never_overdue(self):
        self.assertFalse(sample(status="Approved", deadline=self.yesterday()).is_overdue)

    def test_no_deadline_not_overdue(self):
        self.assertFalse(sample(status="Pending").is_overdue)

    def test_future_deadline_not_overdue(self):
        future = (date.today() + timedelta(days=5)).isoformat()
        self.assertFalse(sample(status="Pending", deadline=future).is_overdue)

    def test_warnings_for_overdue_and_long_sessions(self):
        records = [sample(status="Pending", deadline=self.yesterday()),
                   sample(start_time="08:00", end_time="17:00")]
        warnings = get_warnings(records)
        self.assertEqual(len(warnings), 2)
        self.assertTrue(any(w.startswith("OVERDUE") for w in warnings))
        self.assertTrue(any(w.startswith("REVIEW") for w in warnings))

    def test_exactly_eight_hours_not_flagged(self):
        self.assertEqual(get_warnings([sample(start_time="08:00", end_time="16:00")]), [])


class StorageTests(unittest.TestCase):
    def test_json_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            store = VolunteerStorage(Path(folder) / "records.json")
            original = [sample()]
            store.save(original)
            self.assertEqual(store.load()[0].record_id, original[0].record_id)

    def test_missing_file_gives_empty_list(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(VolunteerStorage(Path(folder) / "none.json").load(), [])

    def test_corrupted_file_is_backed_up_and_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "records.json"
            path.write_text("{ this is not json", encoding="utf-8")
            store = VolunteerStorage(path)
            self.assertEqual(store.load(), [])
            self.assertTrue(store.recovery_message)
            self.assertFalse(path.exists())
            self.assertEqual(len(list(Path(folder).glob("*.bak"))), 1)

    def test_wrong_structure_is_recovered(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "records.json"
            path.write_text('{"a": 1}', encoding="utf-8")
            store = VolunteerStorage(path)
            self.assertEqual(store.load(), [])
            self.assertTrue(store.recovery_message)

    def test_record_missing_fields_is_recovered(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "records.json"
            path.write_text('[{"volunteer_name": "Only a name"}]', encoding="utf-8")
            store = VolunteerStorage(path)
            self.assertEqual(store.load(), [])
            self.assertTrue(store.recovery_message)


class ImportTests(unittest.TestCase):
    def test_valid_and_invalid_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            good = ["Diya Patel", "Park clean-up", "Environment", "2026-01-05", "09:00", "10:30", "Approved", "", "", ""]
            bad_time = ["Kabir", "Fundraiser", "Fundraising", "2026-01-05", "12:00", "11:00", "Pending", "", "", ""]
            bad_name = ["", "Tutoring", "Education", "2026-01-05", "09:00", "10:00", "Pending", "", "", ""]
            store = VolunteerStorage(Path(folder) / "r.json")
            imported, errors = store.import_csv(write_csv(folder, [good, bad_time, bad_name]))
            self.assertEqual(len(imported), 1)
            self.assertEqual(len(errors), 2)
            self.assertTrue(errors[0].startswith("Row 3"))
            self.assertTrue(errors[1].startswith("Row 4"))

    def test_blank_status_cell_imports_as_pending(self):
        with tempfile.TemporaryDirectory() as folder:
            row = ["Diya Patel", "Park clean-up", "Environment", "2026-01-05", "09:00", "10:30", "", "", "", ""]
            imported, errors = VolunteerStorage(Path(folder) / "r.json").import_csv(write_csv(folder, [row]))
            self.assertEqual(errors, [])
            self.assertEqual(imported[0].status, "Pending")

    def test_missing_required_columns(self):
        with tempfile.TemporaryDirectory() as folder:
            path = write_csv(folder, [["Diya", "Park"]], header=["volunteer_name", "activity"])
            with self.assertRaises(StorageError):
                VolunteerStorage(Path(folder) / "r.json").import_csv(path)

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(StorageError):
                VolunteerStorage(Path(folder) / "r.json").import_csv(Path(folder) / "nope.csv")

    def test_merge_skips_duplicates_and_fixes_clashing_ids(self):
        existing = [sample()]
        same_session = sample()                      # identical session -> duplicate
        same_session.record_id = "NEWID001"
        clashing = sample(volunteer_name="Diya Patel")
        clashing.record_id = existing[0].record_id   # new session, but ID already used
        added, duplicates = merge_records(existing, [same_session, clashing])
        self.assertEqual((len(added), duplicates), (1, 1))
        self.assertEqual(len({r.record_id for r in existing}), 2)
        self.assertTrue(all(r.record_id for r in existing))

    def test_reimporting_own_export_adds_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            store = VolunteerStorage(Path(folder) / "r.json")
            records = [sample(), sample(volunteer_name="Diya Patel")]
            export = Path(folder) / "export.csv"
            VolunteerStorage.export_csv(records, export)
            imported, errors = store.import_csv(export)
            added, duplicates = merge_records(records, imported)
            self.assertEqual((errors, len(added), duplicates), ([], 0, 2))

    def test_bundled_sample_dataset(self):
        """data/volunteers.csv: 38 valid rows, 6 intentionally invalid rows."""
        with tempfile.TemporaryDirectory() as folder:
            imported, errors = VolunteerStorage(Path(folder) / "r.json").import_csv(ROOT / "data" / "volunteers.csv")
            self.assertEqual(len(imported), 38)
            self.assertEqual(len(errors), 6)
            self.assertTrue(any(r.hours == 12.0 for r in imported))
            self.assertTrue(get_warnings(imported))


class ReportTests(unittest.TestCase):
    def test_pipe_character_is_escaped(self):
        self.assertEqual(md_cell("Food | Water"), "Food \\| Water")

    def test_markdown_table_survives_pipe_in_activity(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "report.md"
            export_markdown([sample(activity="Food | Water drive")], target)
            self.assertIn("Food \\| Water drive", target.read_text(encoding="utf-8"))


class PaginationTests(unittest.TestCase):
    def test_pages(self):
        pages = list(paginate(list(range(35)), 15))
        self.assertEqual([len(p) for p in pages], [15, 15, 5])

    def test_empty(self):
        self.assertEqual(list(paginate([], 15)), [])


if __name__ == "__main__":
    unittest.main()
