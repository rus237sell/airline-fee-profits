"""Unit checks for the airline fee profit calculations.

Run: python3 -m unittest test_fee_profits -v
No network: these test build_rows / build_mix / build_sensitivity only,
not the live EDGAR pull.
"""
import unittest

from fee_profits import (
    BTS,
    HANDLING_COST_RATES,
    build_mix,
    build_rows,
    build_sensitivity,
    majority_threshold_rate,
)


class TestBuildRows(unittest.TestCase):
    def setUp(self):
        self.rows = build_rows()

    def test_series_is_continuous_2019_2025(self):
        self.assertEqual([r["year"] for r in self.rows],
                         list(range(2019, 2026)))

    def test_fees_are_baggage_plus_change(self):
        for raw, row in zip(BTS, self.rows):
            self.assertAlmostEqual(
                row["reported_fees_total_$B"], raw[4] + raw[5], places=1)

    def test_ex_fee_is_op_minus_fees(self):
        for row in self.rows:
            self.assertAlmostEqual(
                row["op_profit_ex_fees_$B"],
                row["operating_profit_$B"] - row["reported_fees_total_$B"],
                places=1)

    def test_2022_extreme_case(self):
        r = next(r for r in self.rows if r["year"] == 2022)
        self.assertEqual(r["fees_share_of_op_profit_%"], 98.7)
        self.assertEqual(r["op_profit_ex_fees_$B"], 0.1)

    def test_loss_years_have_no_profit_share(self):
        for yr in (2020, 2021):
            r = next(r for r in self.rows if r["year"] == yr)
            self.assertEqual(r["fees_share_of_op_profit_%"], "")


class TestFeeMix(unittest.TestCase):
    def setUp(self):
        self.mix = build_mix(build_rows())

    def test_shares_sum_to_100(self):
        for m in self.mix:
            self.assertAlmostEqual(
                m["baggage_share_of_fees_%"] + m["change_share_of_fees_%"],
                100.0, places=1)

    def test_2025_mix_flip(self):
        m = next(m for m in self.mix if m["year"] == 2025)
        self.assertEqual(m["baggage_vs_2019_%"], 27.6)
        self.assertEqual(m["change_vs_2019_%"], -60.7)
        self.assertEqual(m["baggage_share_of_fees_%"], 87.1)


class TestSensitivity(unittest.TestCase):
    def setUp(self):
        self.rows = build_rows()
        self.sens = build_sensitivity(self.rows)
        self.by = {}
        for s in self.sens:
            self.by.setdefault(s["year"], {})[
                s["handling_cost_%_of_baggage_fees"]] = s

    def test_shape(self):
        self.assertEqual(len(self.sens),
                         len(self.rows) * len(HANDLING_COST_RATES))

    def test_zero_rate_matches_flat_expense_cut(self):
        for row in self.rows:
            s = self.by[row["year"]][0]
            self.assertAlmostEqual(s["net_fee_contribution_$B"],
                                   row["reported_fees_total_$B"], places=2)
            self.assertAlmostEqual(s["op_profit_ex_net_fees_$B"],
                                   row["op_profit_ex_fees_$B"], places=1)

    def test_higher_cost_means_lower_net_and_higher_adjusted_profit(self):
        for yr, by_rate in self.by.items():
            nets = [by_rate[r]["net_fee_contribution_$B"]
                    for r in HANDLING_COST_RATES]
            adj = [by_rate[r]["op_profit_ex_net_fees_$B"]
                   for r in HANDLING_COST_RATES]
            self.assertEqual(nets, sorted(nets, reverse=True))
            self.assertEqual(adj, sorted(adj))

    def test_2025_at_50_percent_hand_math(self):
        # fees 8.5 - 50% x baggage 7.4 = 4.8 net; 11.4 - 4.8 = 6.6 adjusted
        s = self.by[2025][50]
        self.assertAlmostEqual(s["assumed_handling_cost_$B"], 3.7, places=2)
        self.assertAlmostEqual(s["net_fee_contribution_$B"], 4.8, places=2)
        self.assertAlmostEqual(s["op_profit_ex_net_fees_$B"], 6.6, places=2)
        self.assertAlmostEqual(s["net_fees_share_of_op_profit_%"], 42.1,
                               places=1)

    def test_2022_at_50_percent_hand_math(self):
        # fees 7.8 - 50% x baggage 6.8 = 4.4 net; 7.9 - 4.4 = 3.5 adjusted
        s = self.by[2022][50]
        self.assertAlmostEqual(s["net_fee_contribution_$B"], 4.4, places=2)
        self.assertAlmostEqual(s["op_profit_ex_net_fees_$B"], 3.5, places=2)

    def test_loss_years_have_no_net_share(self):
        for yr in (2020, 2021):
            for s in self.by[yr].values():
                self.assertEqual(s["net_fees_share_of_op_profit_%"], "")

    def test_majority_thresholds(self):
        by_year = {r["year"]: r for r in self.rows}
        # (8.5 - 5.7) / 7.4 = 37.8%; (8.2 - 6.6) / 7.1 = 22.5%
        self.assertAlmostEqual(majority_threshold_rate(by_year[2025]),
                               37.8, places=1)
        self.assertAlmostEqual(majority_threshold_rate(by_year[2023]),
                               22.5, places=1)
        self.assertIsNone(majority_threshold_rate(by_year[2020]))

    def test_threshold_actually_crosses_half(self):
        # At each profit year's threshold rate, net share should be ~50%.
        for row in self.rows:
            rate = majority_threshold_rate(row)
            if rate is None or not (0 <= rate <= 100):
                continue
            s = build_sensitivity([row], rates=(rate,))[0]
            self.assertAlmostEqual(s["net_fees_share_of_op_profit_%"],
                                   50.0, delta=1.0)


if __name__ == "__main__":
    unittest.main()
