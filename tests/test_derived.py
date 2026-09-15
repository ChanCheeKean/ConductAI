import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "data" / "generator"))

import derived


class DerivedTests(unittest.TestCase):
    def test_business_day_sla_skips_veterans_day_and_thanksgiving(self):
        self.assertEqual(derived.latest_safe_decision("2026-11-11", "2026-11-11"), "2026-11-25")
        self.assertEqual(derived.latest_safe_decision("2026-11-12", "2026-11-12"), "2026-11-27")

    def test_money_and_time_alignment(self):
        self.assertEqual(str(derived.pct_fee(6200, 5)), "310.00")
        self.assertEqual(str(derived.pct_fee(1850, "1.72")), "31.82")
        self.assertEqual(derived.desktop_true_utc("2026-11-10T14:18:02", "America/Phoenix", 9), "2026-11-10T21:17:53Z")

    def test_wpm_and_policy_version(self):
        words = [{"start_s": 0.0, "end_s": 1.0}, {"start_s": 1.0, "end_s": 2.0}]
        self.assertEqual(derived.words_per_minute(words), 60.0)
        self.assertEqual(derived.cli_policy_version("2026-09-30"), "v5")
        self.assertEqual(derived.cli_policy_version("2026-10-01"), "v6")


if __name__ == "__main__":
    unittest.main()
