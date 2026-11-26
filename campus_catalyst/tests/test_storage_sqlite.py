import json
import logging
import tempfile
import unittest
from datetime import date
from pathlib import Path

from campus_catalyst.analytics import search_records
from campus_catalyst.log import get_logger
from campus_catalyst.storage import SQLiteStorage, StorageError, VolunteerStorage
from campus_catalyst.validators import calculate_hours, validate_record_payload


def rec(**changes):
    data = {"volunteer_name": "Aarav Sharma", "activity": "Mentoring", "category": "Education",
            "service_date": date.today().isoformat(), "start_time": "09:00", "end_time": "11:00",
            "status": "Approved"}
    data.update(changes)
    return validate_record_payload(data)


class SQLiteStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "v.db"

    def test_round_trip(self):
        store = SQLiteStorage(self.db)
        records = [rec(), rec(volunteer_name="Diya", activity="Cleanup", category="Environment")]
        store.save(records)
        loaded = SQLiteStorage(self.db).load()
        self.assertEqual([r.to_dict() for r in loaded], [r.to_dict() for r in records])

    def test_indexed_query_filters(self):
        store = SQLiteStorage(self.db)
        store.save([rec(), rec(volunteer_name="Diya", status="Pending", activity="B")])
        self.assertEqual(len(store.query(status="Pending")), 1)
        self.assertEqual(len(store.query(volunteer="aarav sharma")), 1)   # case-insensitive
        self.assertEqual(len(store.query(status="All")), 2)

    def test_indexed_filter_then_keyword_search(self):
        store = SQLiteStorage(self.db)
        store.save([rec(activity="Library help"), rec(volunteer_name="Diya", activity="Library tidy", status="Pending"),
                    rec(volunteer_name="Ravi", activity="Tree planting", category="Environment")])
        found = search_records(store.query(status="Approved", category="All"), "library")
        self.assertEqual([r.activity for r in found], ["Library help"])

    def test_indexes_exist(self):
        store = SQLiteStorage(self.db)
        with store._connect() as db:
            names = {row[1] for row in db.execute("PRAGMA index_list(records)")}
        self.assertIn("idx_records_status", names)
        self.assertIn("idx_records_volunteer_name", names)

    def test_migrates_legacy_json(self):
        legacy = Path(self.tmp.name) / "old.json"
        VolunteerStorage(legacy).save([rec()])
        store = SQLiteStorage(self.db, legacy_json=legacy)
        self.assertEqual(len(store.load()), 1)

    def test_failed_save_rolls_back(self):
        store = SQLiteStorage(self.db)
        store.save([rec()])
        duplicate_id = [rec(activity="A"), rec(activity="B")]
        duplicate_id[1].record_id = duplicate_id[0].record_id      # primary-key clash
        with self.assertRaises(StorageError):
            store.save(duplicate_id)
        self.assertEqual(len(store.load()), 1)                     # old data intact


class OvernightAndLoggingTests(unittest.TestCase):
    def test_overnight_shift(self):
        self.assertEqual(calculate_hours("22:00", "02:00"), 4.0)

    def test_overnight_over_limit_rejected(self):
        with self.assertRaises(ValueError):
            calculate_hours("08:00", "07:00")

    def test_logger_is_namespaced(self):
        self.assertEqual(get_logger("storage").name, "campus_catalyst.storage")
        self.assertIsInstance(get_logger("x"), logging.Logger)


if __name__ == "__main__":
    unittest.main()
