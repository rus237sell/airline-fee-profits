# Airline fee profits

**Goal:** Test how much of U.S. airline operating profit is really the two fees BTS reports separately (baggage fees and reservation change fees), and what profit looks like without them.

**Macro steps:**
1. Pulled BTS annual results for all U.S. scheduled passenger airlines (2019, 2020, 2023 to 2025): operating revenue, operating profit, net income, baggage fees, change fees.
2. Ran a counterfactual: operating profit minus reported fees, expenses held flat. That is an upper bound on the fees' contribution, since checked bags do cost something to handle and BTS does not split that cost out.
3. Pulled Big 4 (Delta, United, American, Southwest) revenue and operating income live from SEC EDGAR 10-K facts for margin context.
4. Wrote the industry table to `results.csv`, the Big 4 table to `big4_margins.csv`, and charted reported vs ex-fee operating profit (`results.png`).

**Versions:** v1, initial analysis.

**Short results:** Reported fees are only about 3.4% of revenue, but they equal 62% of operating profit in 2023, 62% in 2024, and 75% in 2025. Without them (expenses held flat), industry operating profit falls from $11.4B to $2.9B in 2025 and the operating margin thins from 4.5% to 1.1%. In each of 2023 to 2025, baggage plus change fees alone exceeded the industry's entire after-tax net income. In 2019 the same fees were 41% of a much larger $20.8B operating profit. Two offsets: the counterfactual overstates fee profit (bags are not costless), and it understates total ancillary dependence, because seat selection, food, and other ancillary revenue are not in the BTS fee lines at all. Big 4 context: combined operating margin was 6.1% in 2025 (Delta 9.2%, United 8.0%, American 2.7%, Southwest 1.5%).

Run: `python3 fee_profits.py`
