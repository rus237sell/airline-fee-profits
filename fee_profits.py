"""How much of U.S. airline operating profit is really fees?

Uses Bureau of Transportation Statistics (BTS) annual releases for all U.S.
scheduled passenger airlines. BTS reports exactly two passenger fees as
separate line items: baggage fees and reservation change fees. Seat
selection, food, and other ancillary revenue are bundled into other
categories and cannot be identified separately, so the fee totals here
are a floor for total ancillary revenue, not the whole thing.

Counterfactual: subtract the reported fees from operating profit, holding
expenses flat. That is an upper bound on the fees' profit contribution --
checked bags do cost something to handle and carry, and BTS does not
split that cost out. Read the ex-fee profit as "profit if the fee revenue
vanished and nothing else changed," not as a precise segment P&L.

Second cut: operating margins for the Big 4 carriers (Delta, United,
American, Southwest) pulled live from SEC EDGAR company facts (10-K
filings), to show how thin the underlying business runs.

Third cut: the fee mix itself. Baggage and change fees are tracked
separately (fee_mix.csv / fee_mix.png) because they moved in opposite
directions after 2019 -- change fees collapsed when most large carriers
dropped them on standard tickets in 2020 and never came back, while
baggage fees kept climbing. The headline fee total hides that split.

Fourth cut (v4): the handling-cost sensitivity. The flat-expense
counterfactual is stress-tested by assuming handling a checked bag costs
0 / 25 / 50 / 75% of the baggage fee collected (change fees carry no
comparable handling cost). If the fees vanished, that handling cost
would vanish too, so the net fee contribution is fees minus the avoided
cost, and adjusted ex-fee profit is operating profit minus that net
contribution (sensitivity.csv / sensitivity.png). This turns the single
upper-bound number into a range and shows at what assumed cost rate the
"net fees are a majority of operating profit" reading stops holding.

Fifth cut (v5): the cumulative / era lens. Single-year shares hide what
the pandemic did to the period total: yearly rows are cumulated
(cumulative.csv / cumulative.png) and grouped into eras (eras.csv --
2019, the 2020-2021 loss years, 2022, and the 2023-2025 recovery).
Over 2019-2025 the industry collected $51.1B of reported fees against
just $3.0B of cumulative operating profit and -$0.9B of cumulative net
income, so the ex-fee cumulative operating result is -$48.1B: the fee
lines are not just a share of one good year, they are most of the
bridge between a deeply loss-making seven years and a barely positive
one. The recovery era alone is cleaner: 2023-2025 fees were $25.0B,
65.6% of the $38.1B operating profit for those three years.
"""

import csv
import json
import os
import urllib.request

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# BTS annual results, all U.S. scheduled passenger airlines ($B).
# Sources in SOURCES.md. Continuous 2019-2025 series; the 2020-2021 loss
# years are kept as stress cases, not part of the profit-year trend chart.
# ---------------------------------------------------------------------------
BTS = [
    # year, op_revenue, op_profit, net_income, baggage_fees, change_fees, n_airlines
    (2019, 196.2, 20.8, 14.8, 5.8, 2.8, 21),
    (2020, 77.3, -46.5, -35.0, 2.8, 0.9, 23),
    (2021, 130.0, -17.3, -2.8, 5.3, 0.7, 25),
    (2022, 211.2, 7.9, 1.6, 6.8, 1.0, 25),
    (2023, 236.3, 13.2, 7.8, 7.1, 1.1, 26),
    (2024, 247.2, 13.5, 6.7, 7.3, 1.0, 25),
    (2025, 252.6, 11.4, 6.0, 7.4, 1.1, 25),
]

BIG4 = {  # ticker -> (CIK, name)
    "DAL": (27904, "Delta"),
    "UAL": (100517, "United"),
    "AAL": (6201, "American"),
    "LUV": (92380, "Southwest"),
}

# Assumed baggage-handling cost, as a % of baggage fees collected.
HANDLING_COST_RATES = (0, 25, 50, 75)


def build_rows(bts=BTS):
    """Industry table: reported results plus the flat-expense ex-fee cut."""
    rows = []
    for year, rev, op, net, bag, change, n in bts:
        fees = round(bag + change, 1)
        rows.append({
            "year": year,
            "airlines_reporting": n,
            "operating_revenue_$B": rev,
            "operating_profit_$B": op,
            "net_income_$B": net,
            "baggage_fees_$B": bag,
            "change_fees_$B": change,
            "reported_fees_total_$B": fees,
            "fees_share_of_revenue_%": round(fees / rev * 100, 1),
            "fees_share_of_op_profit_%": (round(fees / op * 100, 1)
                                          if op > 0 else ""),
            "op_profit_ex_fees_$B": round(op - fees, 1),
            "op_margin_%": round(op / rev * 100, 1),
            "op_margin_ex_fees_%": round((op - fees) / rev * 100, 1),
            "note": ("counterfactual holds expenses flat: upper bound on fee "
                     "contribution" if op > 0 else
                     "loss year: fees did not offset the operating loss"),
        })
    return rows


def build_mix(rows):
    """Fee mix: baggage vs change fees, shares and 2019-indexed change."""
    base = next(r for r in rows if r["year"] == 2019)
    mix = []
    for r in rows:
        total = r["reported_fees_total_$B"]
        mix.append({
            "year": r["year"],
            "baggage_fees_$B": r["baggage_fees_$B"],
            "change_fees_$B": r["change_fees_$B"],
            "reported_fees_total_$B": total,
            "baggage_share_of_fees_%": round(
                r["baggage_fees_$B"] / total * 100, 1) if total else "",
            "change_share_of_fees_%": round(
                r["change_fees_$B"] / total * 100, 1) if total else "",
            "baggage_vs_2019_%": round(
                (r["baggage_fees_$B"] / base["baggage_fees_$B"] - 1) * 100, 1),
            "change_vs_2019_%": round(
                (r["change_fees_$B"] / base["change_fees_$B"] - 1) * 100, 1),
        })
    return mix


def build_sensitivity(rows, rates=HANDLING_COST_RATES):
    """Handling-cost sensitivity, long format (one row per year x rate).

    Avoided cost = rate% of baggage fees only. Net fee contribution =
    total fees - avoided cost. Adjusted ex-fee profit = operating
    profit - net contribution, so at 0% it equals the flat-expense
    ex-fee profit in results.csv and it rises as the assumed cost rises.
    """
    out = []
    for r in rows:
        fees = r["reported_fees_total_$B"]
        op = r["operating_profit_$B"]
        rev = r["operating_revenue_$B"]
        for rate in rates:
            avoided = round(r["baggage_fees_$B"] * rate / 100, 2)
            net = round(fees - avoided, 2)
            adj = round(op - net, 2)
            out.append({
                "year": r["year"],
                "handling_cost_%_of_baggage_fees": rate,
                "assumed_handling_cost_$B": avoided,
                "net_fee_contribution_$B": net,
                "net_fees_share_of_op_profit_%": (
                    round(net / op * 100, 1) if op > 0 else ""),
                "op_profit_ex_net_fees_$B": adj,
                "op_margin_ex_net_fees_%": round(adj / rev * 100, 1),
            })
    return out


ERAS = (
    ("2019", (2019,)),
    ("2020-2021", (2020, 2021)),
    ("2022", (2022,)),
    ("2023-2025", (2023, 2024, 2025)),
    ("2019-2025", (2019, 2020, 2021, 2022, 2023, 2024, 2025)),
)


def build_cumulative(rows):
    """Cumulative totals in year order (fees gap = op minus ex-fee op)."""
    out = []
    cum_fees = cum_op = cum_net = 0.0
    for r in rows:
        cum_fees = round(cum_fees + r["reported_fees_total_$B"], 1)
        cum_op = round(cum_op + r["operating_profit_$B"], 1)
        cum_net = round(cum_net + r["net_income_$B"], 1)
        cum_ex = round(cum_op - cum_fees, 1)
        out.append({
            "year": r["year"],
            "cumulative_fees_$B": cum_fees,
            "cumulative_op_profit_$B": cum_op,
            "cumulative_net_income_$B": cum_net,
            "cumulative_op_profit_ex_fees_$B": cum_ex,
        })
    return out


def build_eras(rows, eras=ERAS):
    """Era totals: same flat-expense cut, grouped instead of yearly."""
    by_year = {r["year"]: r for r in rows}
    out = []
    for label, years in eras:
        sel = [by_year[y] for y in years if y in by_year]
        if not sel:
            continue
        op = round(sum(r["operating_profit_$B"] for r in sel), 1)
        fees = round(sum(r["reported_fees_total_$B"] for r in sel), 1)
        net = round(sum(r["net_income_$B"] for r in sel), 1)
        out.append({
            "era": label,
            "years": len(sel),
            "operating_profit_$B": op,
            "reported_fees_total_$B": fees,
            "net_income_$B": net,
            "fees_share_of_op_profit_%": (
                round(fees / op * 100, 1) if op > 0 else ""),
            "op_profit_ex_fees_$B": round(op - fees, 1),
            "fees_minus_net_income_$B": round(fees - net, 1),
        })
    return out


def majority_threshold_rate(row):
    """Handling-cost rate (%) at which net fees = 50% of operating profit.

    Solves (fees - rate * baggage) / op_profit = 0.5 for the rate.
    Returns None for loss years. A negative value means net fees were
    already below half of operating profit at a 0% handling cost.
    """
    op = row["operating_profit_$B"]
    if op <= 0 or not row["baggage_fees_$B"]:
        return None
    rate = (row["reported_fees_total_$B"] - 0.5 * op) / row["baggage_fees_$B"]
    return round(rate * 100, 1)


def edgar_big4(years=(2023, 2024, 2025)):
    """Live SEC EDGAR company facts: revenue + operating income by year.

    Returns rows of (ticker, year, revenue_$B, op_income_$B) or [] if
    EDGAR is unreachable -- the BTS analysis stands on its own.
    """
    rows = []
    for ticker, (cik, _name) in BIG4.items():
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
        req = urllib.request.Request(
            url, headers={"User-Agent": "airline-fee-profits research"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                facts = json.loads(resp.read())["facts"]["us-gaap"]
        except Exception:
            return []
        picked = {}
        for tag, key in (("RevenueFromContractWithCustomerExcludingAssessedTax", "rev"),
                         ("OperatingIncomeLoss", "op")):
            if tag not in facts:
                continue
            units = facts[tag]["units"]
            series = units.get("USD", [])
            for r in series:
                if (r.get("form") == "10-K" and r.get("fp") == "FY"
                        and str(r.get("frame", "")).startswith("CY")
                        and r["end"][5:7] == "12"):
                    yr = int(r["end"][:4])
                    if yr in years:
                        picked.setdefault(yr, {})[key] = r["val"] / 1e9
        for yr in years:
            if yr in picked and "rev" in picked[yr] and "op" in picked[yr]:
                rows.append((ticker, yr, round(picked[yr]["rev"], 2),
                             round(picked[yr]["op"], 2)))
    return rows


def main():
    rows = build_rows()

    with open(os.path.join(HERE, "results.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # ---- fee mix: baggage vs change fees (they diverged after 2019) ----
    mix = build_mix(rows)
    with open(os.path.join(HERE, "fee_mix.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(mix[0].keys()))
        w.writeheader()
        w.writerows(mix)

    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    yrs_mix = [str(m["year"]) for m in mix]
    ax.bar(yrs_mix, [m["baggage_fees_$B"] for m in mix],
           color="#1f4e79", label="Baggage fees")
    ax.bar(yrs_mix, [m["change_fees_$B"] for m in mix],
           bottom=[m["baggage_fees_$B"] for m in mix],
           color="#c9a227", label="Reservation change fees")
    for i, m in enumerate(mix):
        ax.text(i, m["reported_fees_total_$B"] + 0.25,
                f"{m['baggage_share_of_fees_%']:.0f}% bags",
                ha="center", fontsize=8)
    ax.set_ylabel("$B")
    ax.set_title("U.S. airlines: reported fee mix (BTS)\n"
                 "baggage share of baggage + change fees, labelled")
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "fee_mix.png"), dpi=120)
    plt.close(fig)

    # ---- handling-cost sensitivity (v4) ----
    sens = build_sensitivity(rows)
    with open(os.path.join(HERE, "sensitivity.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sens[0].keys()))
        w.writeheader()
        w.writerows(sens)

    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    for r in rows:
        if r["operating_profit_$B"] <= 0:
            continue
        ys = [s["net_fees_share_of_op_profit_%"] for s in sens
              if s["year"] == r["year"]]
        ax.plot(HANDLING_COST_RATES, ys, marker="o",
                label=f"{r['year']} (fees ${r['reported_fees_total_$B']:.1f}B)")
    ax.axhline(50, color="#b00020", linestyle="--", linewidth=1,
               label="Net fees = 50% of operating profit")
    ax.set_xlabel("Assumed baggage-handling cost (% of baggage fees)")
    ax.set_ylabel("Net fees as % of operating profit")
    ax.set_xticks(list(HANDLING_COST_RATES))
    ax.set_title("U.S. airlines: how much of the fee headline survives\n"
                 "a baggage-handling cost? (profit years only)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "sensitivity.png"), dpi=120)
    plt.close(fig)

    # ---- cumulative / era lens (v5) ----
    cum = build_cumulative(rows)
    with open(os.path.join(HERE, "cumulative.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(cum[0].keys()))
        w.writeheader()
        w.writerows(cum)

    eras = build_eras(rows)
    with open(os.path.join(HERE, "eras.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(eras[0].keys()))
        w.writeheader()
        w.writerows(eras)

    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    yrs_c = [str(c["year"]) for c in cum]
    ax.plot(yrs_c, [c["cumulative_op_profit_$B"] for c in cum],
            marker="o", color="#1f4e79",
            label="Cumulative operating profit (reported)")
    ax.plot(yrs_c, [c["cumulative_op_profit_ex_fees_$B"] for c in cum],
            marker="o", color="#b00020",
            label="Cumulative operating profit ex fees (expenses flat)")
    ax.axhline(0, color="#555555", linewidth=0.8)
    ax.set_ylabel("$B, cumulative from 2019")
    ax.set_title("U.S. airlines: cumulative operating profit with and\n"
                 "without reported baggage + change fees (BTS)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "cumulative.png"), dpi=120)
    plt.close(fig)

    # ---- chart: operating profit vs ex-fee operating profit (profit years) --
    trend = [r for r in rows if r["operating_profit_$B"] > 0]
    yrs = [str(r["year"]) for r in trend]
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    x = range(len(yrs))
    ax.bar([i - 0.2 for i in x], [r["operating_profit_$B"] for r in trend],
           width=0.4, color="#1f4e79", label="Operating profit (reported)")
    ax.bar([i + 0.2 for i in x], [r["op_profit_ex_fees_$B"] for r in trend],
           width=0.4, color="#b00020",
           label="Ex-fee operating profit (expenses held flat)")
    for i, r in enumerate(trend):
        ax.text(i, max(r["operating_profit_$B"],
                       r["op_profit_ex_fees_$B"]) + 0.6,
                f"fees ${r['reported_fees_total_$B']:.1f}B",
                ha="center", fontsize=9)
    ax.set_xticks(list(x))
    ax.set_xticklabels(yrs)
    ax.set_ylabel("$B")
    ax.set_title("U.S. airlines: operating profit with and without\n"
                 "reported baggage + change fees (BTS)")
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(HERE, "results.png"), dpi=120)
    plt.close(fig)

    # ---- printed findings ----
    print("U.S. scheduled passenger airlines (BTS annual releases)")
    print(f"{'year':<6}{'op profit':>10}{'fees':>8}{'fees/op profit':>16}"
          f"{'ex-fee profit':>15}{'ex-fee margin':>15}")
    for r in rows:
        share = (f"{r['fees_share_of_op_profit_%']}%"
                 if r["fees_share_of_op_profit_%"] != "" else "n/a (loss)")
        print(f"{r['year']:<6}{r['operating_profit_$B']:>10.1f}"
              f"{r['reported_fees_total_$B']:>8.1f}{share:>16}"
              f"{r['op_profit_ex_fees_$B']:>15.1f}"
              f"{r['op_margin_ex_fees_%']:>14.1f}%")
    print()
    recent = [r for r in rows if r["year"] >= 2023]
    for r in recent:
        print(f"{r['year']}: reported fees (${r['reported_fees_total_$B']:.1f}B) "
              f"exceed the industry's after-tax net income "
              f"(${r['net_income_$B']:.1f}B).")
    r2022 = next(r for r in rows if r["year"] == 2022)
    print(f"2022: reported fees (${r2022['reported_fees_total_$B']:.1f}B) were "
          f"{r2022['fees_share_of_op_profit_%']:.1f}% of the $7.9B operating "
          f"profit -- ex-fee operating profit was just "
          f"${r2022['op_profit_ex_fees_$B']:.1f}B in the first profit year "
          f"after the pandemic losses.")
    m19 = next(m for m in mix if m["year"] == 2019)
    m25 = next(m for m in mix if m["year"] == 2025)
    print()
    print("Fee mix (baggage vs change):")
    print(f"  2019: bags ${m19['baggage_fees_$B']:.1f}B "
          f"({m19['baggage_share_of_fees_%']:.1f}% of fees), change "
          f"${m19['change_fees_$B']:.1f}B ({m19['change_share_of_fees_%']:.1f}%)")
    print(f"  2025: bags ${m25['baggage_fees_$B']:.1f}B "
          f"({m25['baggage_share_of_fees_%']:.1f}% of fees), change "
          f"${m25['change_fees_$B']:.1f}B ({m25['change_share_of_fees_%']:.1f}%)")
    print(f"  2019->2025: baggage {m25['baggage_vs_2019_%']:+.1f}%, change "
          f"{m25['change_vs_2019_%']:+.1f}%; total fees "
          f"${m19['reported_fees_total_$B']:.1f}B -> "
          f"${m25['reported_fees_total_$B']:.1f}B -- the fee story is now "
          f"almost entirely baggage.")
    print()
    print("Handling-cost sensitivity (cost = % of baggage fees):")
    for yr in (2022, 2023, 2024, 2025):
        sel = {s["handling_cost_%_of_baggage_fees"]: s for s in sens
               if s["year"] == yr}
        row = next(r for r in rows if r["year"] == yr)
        print(f"  {yr}: at 50% cost, net fees "
              f"${sel[50]['net_fee_contribution_$B']:.2f}B "
              f"({sel[50]['net_fees_share_of_op_profit_%']:.1f}% of op "
              f"profit), adjusted ex-fee profit "
              f"${sel[50]['op_profit_ex_net_fees_$B']:.2f}B "
              f"({sel[50]['op_margin_ex_net_fees_%']:.1f}% margin); "
              f"net fees fall to half of op profit at a "
              f"{majority_threshold_rate(row):.1f}% handling cost.")
    print()
    print("Cumulative / era lens:")
    full = next(e for e in eras if e["era"] == "2019-2025")
    rec = next(e for e in eras if e["era"] == "2023-2025")
    print(f"  2019-2025: cumulative fees "
          f"${full['reported_fees_total_$B']:.1f}B vs cumulative operating "
          f"profit ${full['operating_profit_$B']:.1f}B and cumulative net "
          f"income ${full['net_income_$B']:.1f}B -- cumulative operating "
          f"profit ex fees is ${full['op_profit_ex_fees_$B']:.1f}B.")
    print(f"  2023-2025 recovery: fees ${rec['reported_fees_total_$B']:.1f}B "
          f"were {rec['fees_share_of_op_profit_%']:.1f}% of the "
          f"${rec['operating_profit_$B']:.1f}B operating profit; ex-fee "
          f"operating profit was ${rec['op_profit_ex_fees_$B']:.1f}B.")
    print()
    print("Caveats: fee counterfactual holds expenses flat (upper bound);")
    print("the sensitivity relaxes that for baggage handling only --")
    print("seat/food/other ancillary revenue is NOT in the BTS fee lines,")
    print("so total ancillary dependence is larger than shown.")

    # ---- Big 4 context from SEC EDGAR ----
    big4 = edgar_big4()
    if big4:
        with open(os.path.join(HERE, "big4_margins.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ticker", "year", "revenue_$B", "operating_income_$B",
                        "operating_margin_%"])
            for t, yr, rev, op in big4:
                w.writerow([t, yr, rev, op, round(op / rev * 100, 1)])
        print()
        print("Big 4 operating margins (SEC EDGAR 10-K facts):")
        for yr in (2023, 2024, 2025):
            sel = [b for b in big4 if b[1] == yr]
            if sel:
                tot_rev = sum(b[2] for b in sel)
                tot_op = sum(b[3] for b in sel)
                per = ", ".join(f"{b[0]} {b[3]/b[2]*100:.1f}%" for b in sel)
                print(f"  {yr}: combined {tot_op/tot_rev*100:.1f}% "
                      f"(${tot_op:.2f}B on ${tot_rev:.1f}B) -- {per}")
    else:
        print()
        print("Big 4 EDGAR pull unavailable this run; BTS results stand alone.")
    print()
    print("Sources: SOURCES.md (results.csv, results.png, fee_mix.csv, "
          "fee_mix.png, sensitivity.csv, sensitivity.png, cumulative.csv, "
          "cumulative.png, eras.csv written).")


if __name__ == "__main__":
    main()
