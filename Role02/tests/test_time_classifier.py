import unittest

from time_classifier import classify_time


class TimeClassifierTest(unittest.TestCase):
    def test_modified_time_has_priority(self):
        result = classify_time(
            created_at="2026-10-12 12:00:00",
            modified_at="2026-03-19 15:06:33",
        )
        self.assertEqual(result.year_month, "2026-03")
        self.assertEqual(result.source, "modified_at")

    def test_created_time_fallback(self):
        result = classify_time(created_at="2026-10-12 12:00:00")
        self.assertEqual(result.month, 10)
        self.assertEqual(result.source, "created_at")

    def test_explicit_activity_time_has_priority(self):
        result = classify_time(
            activity_at="2026-05-01 09:00:00",
            modified_at="2026-06-01 09:00:00",
        )
        self.assertEqual(result.month_label, "2026년 5월")
        self.assertEqual(result.source, "activity_at")

    def test_dotted_date(self):
        result = classify_time(modified_at="2026.9.28 16:48")
        self.assertEqual(result.year_month, "2026-09")

    def test_unknown(self):
        result = classify_time(modified_at="not-a-date")
        self.assertTrue(result.needs_confirmation)
        self.assertEqual(result.month_label, "미분류")


if __name__ == "__main__":
    unittest.main()
