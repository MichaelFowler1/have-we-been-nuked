# Tests for the decision logic in nuked.py. No network needed.
# Run with:  python -m unittest

import datetime
import unittest

import nuked


class TestAssess(unittest.TestCase):
    # A typical station: mean 2000 cpm, std 100 cpm.

    def test_normal_reading(self):
        self.assertEqual(nuked.assess(2100, 2000, 100), "NORMAL")

    def test_spill_when_far_above_normal_variation(self):
        # 3200 is 12 sigmas out AND 1.6x the mean: both conditions met.
        self.assertEqual(nuked.assess(3200, 2000, 100), "SPILL")

    def test_many_sigmas_but_small_rise_is_not_a_spill(self):
        # A hyper-stable station (std 10): 2200 is 20 sigmas out but
        # only 1.1x the mean — the ratio guard keeps this NORMAL.
        self.assertEqual(nuked.assess(2200, 2000, 10), "NORMAL")

    def test_big_ratio_but_noisy_station_is_not_a_spill(self):
        # A noisy station (std 500): 3200 is 1.6x the mean but only
        # 2.4 sigmas out — within its own normal chaos.
        self.assertEqual(nuked.assess(3200, 2000, 500), "NORMAL")

    def test_nuke_at_ten_times_the_mean(self):
        self.assertEqual(nuked.assess(20000, 2000, 100), "NUKE")

    def test_nuke_even_on_a_noisy_station(self):
        # 10x the mean is catastrophic no matter the std.
        self.assertEqual(nuked.assess(20000, 2000, 99999), "NUKE")

    def test_zero_std_station_uses_ratio_alone(self):
        self.assertEqual(nuked.assess(3000, 2000, 0), "SPILL")
        self.assertEqual(nuked.assess(2100, 2000, 0), "NORMAL")

    def test_zero_mean_is_unknown(self):
        self.assertEqual(nuked.assess(1000, 0, 0), "UNKNOWN")


class TestHoursOld(unittest.TestCase):
    def test_reading_from_ninety_minutes_ago(self):
        now = datetime.datetime(2026, 7, 16, 1, 30, 0)
        self.assertEqual(nuked.hours_old("07/16/2026 00:00:00", now), 1.5)

    def test_reading_from_yesterday(self):
        now = datetime.datetime(2026, 7, 16, 12, 0, 0)
        self.assertEqual(nuked.hours_old("07/15/2026 12:00:00", now), 24.0)


class TestTotalCount(unittest.TestCase):
    def make_row(self, values):
        return dict(zip(nuked.COUNT_COLUMNS, values))

    def test_sums_all_channels(self):
        row = self.make_row(["100.00", "50.00", "25.00", "10.00",
                             "5.00", "5.00", "3.00", "2.00"])
        self.assertEqual(nuked.total_count(row), 200.0)

    def test_skips_blank_channels(self):
        row = self.make_row(["100.00", "", "25.00", "", "", "", "", ""])
        self.assertEqual(nuked.total_count(row), 125.0)

    def test_all_blank_returns_none(self):
        row = self.make_row([""] * 8)
        self.assertIsNone(nuked.total_count(row))


if __name__ == "__main__":
    unittest.main()
