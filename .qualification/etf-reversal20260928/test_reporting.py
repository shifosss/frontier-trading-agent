"""Whole-account weekly target denominators and nonreset calendar-year returns."""
import unittest
from run_study import add_reporting, weekly_targets


class ReportingTests(unittest.TestCase):
    def test_idle_loss_and_target_weeks_all_count(self):
        result = weekly_targets([{"return": x} for x in (0, -.02, -.01, .05, .10, .15, 0, -.03)])
        self.assertEqual(result["weeks"], 8)
        self.assertEqual([x["count"] for x in result["thresholds"]], [3, 2, 1])
        self.assertEqual([x["fraction"] for x in result["thresholds"]], [3/8, 2/8, 1/8])
        self.assertEqual(result["longest_losing_week_streak"], 2)
        self.assertEqual(result["median_return"], 0)
        self.assertEqual(result["worst_return"], -.03)

    def test_continuous_years_and_initialization_tail_tags(self):
        report = {"status": "complete", "period_returns": {"weekly": [
            {"last_session": "2016-12-30", "return": 0},
            {"last_session": "2017-01-06", "return": -.1},
            {"last_session": "2026-01-02", "return": .2}]}, "equity_curve": [
                {"session": "2016-12-30", "equity": 100},
                {"session": "2017-12-29", "equity": 90},
                {"session": "2026-01-02", "equity": 108}]}
        add_reporting(report, 100)
        self.assertEqual([r["scope"] for r in report["period_returns"]["weekly"]],
                         ["initialization", "entry_period", "entry_period_with_liquidation_tail"])
        self.assertEqual(report["entry_period_weekly_targets"]["weeks"], 2)
        self.assertAlmostEqual(report["annual_returns"][-1]["return"], .2)


if __name__ == "__main__":
    unittest.main()
