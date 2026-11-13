"""Unit checks for the airline fee profit calculations.

Run: python3 -m unittest test_fee_profits -v
No network: these test the build_* functions only, not the live EDGAR
pull (the Big 4 split is tested against a fixed EDGAR fixture).
"""
import unittest

from fee_profits import (
    BTS,
    ERAS,
    HANDLING_COST_RATES,
    build_big4_vs_rest,
    build_cumulative,
    build_eras,
    build_mix,
    build_per_airline,
    build_rows,
    build_sensitivity,
    majority_threshold_rate,
)

# EDGAR Big 4 rows as pulled live (ticker, year, revenue $B, op income $B);
# duplicated here so the split tests need no network.
BIG4_FIXTURE = [
    ("DAL", 2023, 58.05, 5.52), ("UAL", 2023, 53.72, 4.21),
    ("AAL", 2023, 52.79, 3.03), ("LUV", 2023, 26.09, 0.22),
    ("DAL", 2024, 61.64, 6.00), ("UAL", 2024, 57.06, 5.10),
    ("AAL", 2024, 54.21, 2.61), ("LUV", 2024, 27.48, 0.32),
    ("DAL", 2025, 63.36, 5.82), ("UAL", 2025, 59.07, 4.71),
    ("AAL", 2025, 54.63, 1.47), ("LUV", 2025, 28.06, 0.43),
]


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


class TestCumulativeAndEras(unittest.TestCase):
    def setUp(self):
        self.rows = build_rows()
        self.cum = build_cumulative(self.rows)
        self.eras = {e["era"]: e for e in build_eras(self.rows)}

    def test_cumulative_shape_and_gap_identity(self):
        self.assertEqual(len(self.cum), len(self.rows))
        for c, row in zip(self.cum, self.rows):
            self.assertEqual(c["year"], row["year"])
        last = self.cum[-1]
        # gap between cumulative op and cumulative ex-fee op IS cum fees
        self.assertAlmostEqual(
            last["cumulative_op_profit_$B"]
            - last["cumulative_op_profit_ex_fees_$B"],
            last["cumulative_fees_$B"], places=1)

    def test_full_period_hand_math(self):
        last = self.cum[-1]
        self.assertEqual(last["cumulative_fees_$B"], 51.1)
        self.assertEqual(last["cumulative_op_profit_$B"], 3.0)
        self.assertEqual(last["cumulative_net_income_$B"], -0.9)
        self.assertEqual(last["cumulative_op_profit_ex_fees_$B"], -48.1)

    def test_cumulative_fees_monotonic_and_trough(self):
        fees = [c["cumulative_fees_$B"] for c in self.cum]
        self.assertEqual(fees, sorted(fees))
        trough = min(self.cum, key=lambda c: c["cumulative_op_profit_$B"])
        self.assertEqual(trough["year"], 2021)
        self.assertEqual(trough["cumulative_op_profit_$B"], -43.0)

    def test_era_totals_match_yearly_rows(self):
        self.assertEqual([e for e in self.eras], [e[0] for e in ERAS])
        for label, years in ERAS:
            sel = [r for r in self.rows if r["year"] in years]
            e = self.eras[label]
            self.assertAlmostEqual(
                e["operating_profit_$B"],
                round(sum(r["operating_profit_$B"] for r in sel), 1),
                places=1)
            self.assertAlmostEqual(
                e["reported_fees_total_$B"],
                round(sum(r["reported_fees_total_$B"] for r in sel), 1),
                places=1)
            self.assertAlmostEqual(
                e["op_profit_ex_fees_$B"],
                round(e["operating_profit_$B"]
                      - e["reported_fees_total_$B"], 1), places=1)

    def test_recovery_era_hand_math(self):
        rec = self.eras["2023-2025"]
        self.assertEqual(rec["operating_profit_$B"], 38.1)
        self.assertEqual(rec["reported_fees_total_$B"], 25.0)
        self.assertEqual(rec["fees_share_of_op_profit_%"], 65.6)
        self.assertEqual(rec["op_profit_ex_fees_$B"], 13.1)
        self.assertEqual(rec["net_income_$B"], 20.5)

    def test_loss_era_has_no_profit_share(self):
        self.assertEqual(self.eras["2020-2021"]["operating_profit_$B"], -63.8)
        self.assertEqual(self.eras["2020-2021"]["fees_share_of_op_profit_%"], "")

    def test_single_year_eras_match_rows(self):
        for yr in (2019, 2022):
            e = self.eras[str(yr)]
            r = next(r for r in self.rows if r["year"] == yr)
            self.assertEqual(e["operating_profit_$B"],
                             r["operating_profit_$B"])
            self.assertEqual(e["reported_fees_total_$B"],
                             r["reported_fees_total_$B"])


class TestPerAirline(unittest.TestCase):
    def setUp(self):
        self.rows = build_rows()
        self.pa = build_per_airline(self.rows)
        self.by_year = {p["year"]: p for p in self.pa}

    def test_shape_matches_rows(self):
        self.assertEqual(len(self.pa), len(self.rows))
        for p, row in zip(self.pa, self.rows):
            self.assertEqual(p["year"], row["year"])
            self.assertEqual(p["airlines_reporting"],
                             row["airlines_reporting"])

    def test_per_airline_times_count_recovers_totals(self):
        for p, row in zip(self.pa, self.rows):
            n = row["airlines_reporting"]
            self.assertAlmostEqual(
                p["op_profit_per_airline_$B"] * n,
                row["operating_profit_$B"], delta=0.02)
            self.assertAlmostEqual(
                p["fees_per_airline_$B"] * n,
                row["reported_fees_total_$B"], delta=0.02)
            self.assertAlmostEqual(
                p["revenue_per_airline_$B"] * n,
                row["operating_revenue_$B"], delta=0.02)

    def test_ex_fee_identity_per_airline(self):
        for p in self.pa:
            self.assertAlmostEqual(
                p["op_profit_per_airline_$B"]
                - p["fees_per_airline_$B"],
                p["op_profit_ex_fees_per_airline_$B"], delta=0.002)

    def test_2019_hand_math(self):
        p = self.by_year[2019]
        # 196.2/21, 20.8/21, 12.2/21, 8.6/21
        self.assertAlmostEqual(p["revenue_per_airline_$B"], 9.343,
                               places=3)
        self.assertAlmostEqual(p["op_profit_per_airline_$B"], 0.990,
                               places=3)
        self.assertAlmostEqual(
            p["op_profit_ex_fees_per_airline_$B"], 0.581, places=3)
        self.assertAlmostEqual(p["fees_per_airline_$B"], 0.410, places=3)
        self.assertEqual(p["op_profit_per_airline_vs_2019_%"], 0.0)
        self.assertEqual(p["fees_per_airline_vs_2019_%"], 0.0)

    def test_2025_hand_math_and_vs_2019(self):
        p = self.by_year[2025]
        # 252.6/25, 11.4/25, 2.9/25, 8.5/25
        self.assertAlmostEqual(p["revenue_per_airline_$B"], 10.104,
                               places=3)
        self.assertAlmostEqual(p["op_profit_per_airline_$B"], 0.456,
                               places=3)
        self.assertAlmostEqual(
            p["op_profit_ex_fees_per_airline_$B"], 0.116, places=3)
        self.assertAlmostEqual(p["fees_per_airline_$B"], 0.340, places=3)
        self.assertEqual(p["op_profit_per_airline_vs_2019_%"], -54.0)
        self.assertEqual(p["fees_per_airline_vs_2019_%"], -17.0)

    def test_2022_ex_fee_per_airline_is_near_zero(self):
        # 0.1 ex-fee profit spread over 25 carriers
        self.assertAlmostEqual(
            self.by_year[2022]["op_profit_ex_fees_per_airline_$B"],
            0.004, places=3)

    def test_fees_per_airline_fell_while_op_share_rose(self):
        # The v6 point: fees per carrier are lower in 2025 than 2019
        # even though fees are a larger share of operating profit.
        r19 = next(r for r in self.rows if r["year"] == 2019)
        r25 = next(r for r in self.rows if r["year"] == 2025)
        self.assertLess(self.by_year[2025]["fees_per_airline_$B"],
                        self.by_year[2019]["fees_per_airline_$B"])
        self.assertGreater(r25["fees_share_of_op_profit_%"],
                           r19["fees_share_of_op_profit_%"])


class TestBig4VsRest(unittest.TestCase):
    def setUp(self):
        self.rows = build_rows()
        self.split = build_big4_vs_rest(self.rows, BIG4_FIXTURE)
        self.by_year = {s["year"]: s for s in self.split}

    def test_only_years_in_both_sources(self):
        self.assertEqual([s["year"] for s in self.split], [2023, 2024, 2025])
        for s in self.split:
            self.assertEqual(s["big4_carriers"], 4)

    def test_big4_plus_rest_recovers_industry(self):
        for s in self.split:
            self.assertAlmostEqual(
                s["big4_revenue_$B"] + s["rest_revenue_$B"],
                s["industry_revenue_$B"], places=2)
            self.assertAlmostEqual(
                s["big4_op_profit_$B"] + s["rest_op_profit_$B"],
                s["industry_op_profit_$B"], places=2)
            row = next(r for r in self.rows if r["year"] == s["year"])
            self.assertEqual(s["rest_carriers_reporting"],
                             row["airlines_reporting"] - 4)

    def test_2025_hand_math(self):
        s = self.by_year[2025]
        # Big 4: 63.36+59.07+54.63+28.06 = 205.12; 5.82+4.71+1.47+0.43 = 12.43
        self.assertAlmostEqual(s["big4_revenue_$B"], 205.12, places=2)
        self.assertAlmostEqual(s["big4_op_profit_$B"], 12.43, places=2)
        self.assertEqual(s["big4_op_margin_%"], 6.1)
        self.assertEqual(s["big4_share_of_industry_revenue_%"], 81.2)
        self.assertEqual(s["big4_share_of_industry_op_profit_%"], 109.0)
        # Rest: 252.6-205.12 = 47.48; 11.4-12.43 = -1.03
        self.assertAlmostEqual(s["rest_revenue_$B"], 47.48, places=2)
        self.assertAlmostEqual(s["rest_op_profit_$B"], -1.03, places=2)
        self.assertEqual(s["rest_op_margin_%"], -2.2)
        self.assertEqual(s["rest_carriers_reporting"], 21)

    def test_2023_rest_barely_positive_2024_negative(self):
        s23 = self.by_year[2023]
        self.assertAlmostEqual(s23["big4_op_profit_$B"], 12.98, places=2)
        self.assertAlmostEqual(s23["rest_op_profit_$B"], 0.22, places=2)
        self.assertEqual(s23["big4_share_of_industry_op_profit_%"], 98.3)
        self.assertEqual(s23["rest_op_margin_%"], 0.5)
        s24 = self.by_year[2024]
        self.assertAlmostEqual(s24["rest_op_profit_$B"], -0.53, places=2)
        self.assertEqual(s24["big4_share_of_industry_op_profit_%"], 103.9)

    def test_profit_share_can_exceed_100(self):
        # Not an error: a share above 100% means the rest lost money.
        for yr in (2024, 2025):
            self.assertGreater(
                self.by_year[yr]["big4_share_of_industry_op_profit_%"], 100)
            self.assertLess(self.by_year[yr]["rest_op_profit_$B"], 0)

    def test_revenue_share_stable_near_81(self):
        shares = [s["big4_share_of_industry_revenue_%"] for s in self.split]
        self.assertTrue(all(80.0 < x < 82.0 for x in shares))

    def test_years_outside_industry_or_big4_are_skipped(self):
        extra = BIG4_FIXTURE + [("DAL", 2019, 47.0, 5.0),
                                 ("XXX", 2030, 1.0, 1.0)]
        split = build_big4_vs_rest(self.rows, extra)
        # 2019 has no full Big 4 set in the fixture but DAL alone would
        # aggregate; only assert the out-of-range year is dropped and
        # the three EDGAR years stay intact.
        self.assertNotIn(2030, [s["year"] for s in split])
        self.assertEqual(
            {s["year"]: s["big4_op_profit_$B"] for s in split
             if s["year"] in self.by_year},
            {y: s["big4_op_profit_$B"] for y, s in self.by_year.items()})


if __name__ == "__main__":
    unittest.main()
