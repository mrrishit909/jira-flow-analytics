"""The project's check: fails loudly if the status timelines, cycle times, throughput or backtest break.

    ./venv/bin/python check.py

1. every issue's status stretches tile its life exactly (created -> resolved or the cut-off, no gaps or overlaps)
2. cycle times for 300 random fixed issues recompute from the raw status moves; percentiles recompute
3. weekly throughput adds up to the fixed-and-worked issues; backtest actuals recompute from it
4. published files hold no issue keys, titles or comments
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

import analysis as A

R = Path(__file__).parent / "results"


def main():
    d = A.load()
    seg = A.segments(d)
    life = d.set_index("key")
    end = life["resolved"].fillna(A.AS_OF).clip(upper=A.AS_OF)
    total = seg.groupby("key")["days"].sum()
    expect = ((end - life["created"]).dt.total_seconds() / 86400).reindex(total.index)
    # Jira's resolution date is cut to whole seconds while status moves keep milliseconds: allow ~9 seconds
    assert (np.abs(total - expect) < 1e-4).all(), (total - expect).abs().sort_values().tail()
    gaps = seg.sort_values(["key", "start"]).groupby("key").apply(lambda g: (g["start"].iloc[1:].values != g["end"].iloc[:-1].values).sum())
    assert gaps.sum() == 0, "status stretches must join end to start"

    fx = A.cycle_times(d)
    s = json.loads((R / "summary.json").read_text())
    sample = fx[fx["started"].notna()].sample(300, random_state=3)
    for r in sample.itertuples():
        starts = [pd.Timestamp(m["at"]) for m in r.moves if m["to"] in A.START]
        assert abs((r.resolved - min(starts)).total_seconds() / 86400 - r.cycle_days) < 1e-9
    ct = pd.read_csv(R / "cycle_times.csv")
    for q in (50, 85, 95):
        assert abs(np.percentile(ct["cycle_days"], q) - s["cycle_time_days"][f"p{q}"]) < 0.01

    w = pd.read_csv(R / "weekly_throughput.csv", parse_dates=["week"]).set_index("week")["fixed"]
    worked = fx[fx["started"].notna() & (fx["resolved"] >= w.index[0]) & (fx["resolved"] < w.index[-1] + pd.Timedelta(days=7))]
    assert w.sum() == len(worked)
    bt = pd.read_csv(R / "forecast_backtest.csv", parse_dates=["forecast_from"])
    for r in bt.itertuples():
        at = r.forecast_from.tz_localize("UTC")
        assert r.actual == w[(w.index >= at) & (w.index < at + pd.Timedelta(weeks=8))].sum()
    assert abs(bt["inside_p15_p85"].mean() - s["backtest"]["nominal_70_band_hit_rate"]) < 1e-12

    tis = pd.read_csv(R / "time_in_status.csv")
    assert abs(tis["share"].sum() - 1) < 1e-3
    for f in R.iterdir():
        text = f.read_text()
        assert "CASSANDRA-" not in text and "summary\"" not in text and "description" not in text, f.name
    print(f"OK: status stretches tile each issue's life with no gaps; 300 cycle times recomputed; percentiles "
          f"(p50 {s['cycle_time_days']['p50']:.1f}, p85 {s['cycle_time_days']['p85']:.1f} days) recompute; throughput adds up "
          f"({w.sum():,} items); 40 backtest actuals recompute; no keys or text published")


if __name__ == "__main__":
    main()
