import unittest
from datetime import date

from campus_catalyst.insights import (badge_for, certificate_text, goal_progress,
                                      leaderboard, monthly_hours, records_for)
from campus_catalyst.validators import validate_record_payload


def rec(name, day, start, end, status="Approved", activity="Cleanup"):
    return validate_record_payload({"volunteer_name": name, "activity": activity, "category": "Environment",
                                    "service_date": day, "start_time": start, "end_time": end,
                                    "status": status})


class InsightTests(unittest.TestCase):
    def setUp(self):
        self.records = [rec("Asha K", "2025-01-10", "09:00", "12:00"),
                        rec("asha k", "2025-01-20", "09:00", "11:00"),
                        rec("Asha K", "2025-02-02", "09:00", "10:00", status="Pending"),
                        rec("Ravi", "2025-02-03", "09:00", "12:00")]

    def test_records_for_is_case_insensitive(self):
        self.assertEqual(len(records_for(self.records, " ASHA k ")), 3)

    def test_monthly_hours_counts_only_approved(self):
        self.assertEqual(monthly_hours(self.records), {"2025-01": 5.0, "2025-02": 3.0})

    def test_leaderboard_groups_names(self):
        self.assertEqual(leaderboard(self.records), [("Asha K", 5.0), ("Ravi", 3.0)])

    def test_badges_and_progress(self):
        self.assertEqual([badge_for(h) for h in (5, 20, 30, 50, 100)],
                         ["None yet", "Bronze", "Silver", "Gold", "Platinum"])
        self.assertEqual(goal_progress(10), 0.5)
        self.assertEqual(goal_progress(99), 1.0)

    def test_certificate_requires_goal(self):
        with self.assertRaises(ValueError):
            certificate_text("Asha K", self.records)
        many = [rec("Sam", f"2025-03-{d:02d}", "08:00", "12:00") for d in range(1, 7)]  # 24 h
        text = certificate_text("Sam", many, today=date(2025, 4, 1))
        self.assertIn("24 approved volunteer hours", text)
        self.assertIn("Bronze", text)


if __name__ == "__main__":
    unittest.main()
