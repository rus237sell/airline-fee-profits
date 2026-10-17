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
    rows = []
    for year, rev, op, net, bag, change, n in BTS:
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

    with open(os.path.join(HERE, "results.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

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
    print()
    print("Caveats: fee counterfactual holds expenses flat (upper bound);")
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
    print("Sources: SOURCES.md (results.csv, results.png written).")


if __name__ == "__main__":
    main()
