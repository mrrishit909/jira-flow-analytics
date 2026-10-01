"""Step 3: the standard flow-metrics charts.

    ./venv/bin/python charts.py   -> charts/01_cycle_scatter.png ... 05_wip_aging.png
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
R = HERE / "results"
INK, DIM, GRID, BG, BLUE, ORANGE, GRAY = "#f2f2f0", "#8a8a87", "#1d1d1d", "#0b0b0b", "#3987e5", "#d95926", "#9a9a96"
plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG, "text.color": INK,
    "axes.edgecolor": "#3a3a3a", "axes.labelcolor": DIM, "xtick.color": DIM, "ytick.color": DIM,
    "axes.grid": True, "axes.axisbelow": True, "grid.color": GRID, "grid.linewidth": 1,
    "axes.spines.top": False, "axes.spines.right": False,
    "font.family": ["Helvetica Neue", "Arial", "DejaVu Sans"], "font.size": 11, "axes.titlesize": 13,
    "axes.titlelocation": "left", "axes.titlepad": 12,
})


def save(fig, name):
    fig.tight_layout()
    fig.savefig(HERE / "charts" / name, dpi=150)
    plt.close(fig)


def main():
    (HERE / "charts").mkdir(exist_ok=True)
    s = json.loads((R / "summary.json").read_text())
    ct = pd.read_csv(R / "cycle_times.csv", parse_dates=["resolved"])
    fig, ax = plt.subplots(figsize=(10, 4.4))
    ax.scatter(ct["resolved"], ct["cycle_days"].clip(lower=0.01), s=5, alpha=0.35, color=BLUE, linewidths=0)
    ax.set_yscale("log")
    for q, color in [("p50", INK), ("p85", ORANGE), ("p95", GRAY)]:
        v = s["cycle_time_days"][q]
        ax.axhline(v, color=color, linewidth=1, linestyle="--")
        ax.text(ct["resolved"].max() + pd.Timedelta(days=15), v * 1.12, f"{q[1:]}%: {v:.0f} days", color=INK, va="bottom", fontsize=9)
    ax.set_xlim(ct["resolved"].min() - pd.Timedelta(days=10), ct["resolved"].max() + pd.Timedelta(days=110))
    ax.set_ylabel("cycle time, days (log scale)")
    ax.set_xlabel("date resolved (each dot is one fixed issue; under 15 minutes shown at the bottom)")
    ax.set_title(f"Cycle-time scatterplot: half of fixes take under {s['cycle_time_days']['p50']:.0f} days, 15% take over {s['cycle_time_days']['p85']:.0f}")
    save(fig, "01_cycle_scatter.png")

    t = pd.read_csv(R / "time_in_status.csv").sort_values("sum")
    t = t[t["share"] >= 0.005]
    fig, ax = plt.subplots(figsize=(10, 4.2))
    colors = t["kind"].map({"working": BLUE, "waiting": ORANGE, "other": GRAY})
    ax.barh(t["status"], 100 * t["share"], color=colors, height=0.6)
    for i, v in enumerate(t["share"]):
        ax.text(100 * v + 0.4, i, f"{100 * v:.0f}%", va="center", color=INK, fontsize=9)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("share of all cycle time, Fixed issues 2022-2026\nblue = someone working · orange = waiting · grey = back in backlog or reopened")
    ax.set_title("A third of all cycle time is patches waiting for a reviewer")
    save(fig, "02_time_in_status.png")

    w = pd.read_csv(R / "weekly_throughput.csv", parse_dates=["week"])
    w = w[w["week"] >= "2022-01-01"]
    fig, ax = plt.subplots(figsize=(10, 3.6))
    ax.bar(w["week"], w["fixed"], width=6, color=BLUE)
    roll = w.set_index("week")["fixed"].rolling(13).mean()
    ax.plot(roll.index, roll.values, color=ORANGE, linewidth=2, label="13-week average")
    ax.set_ylabel("issues fixed per week")
    ax.legend(frameon=False, labelcolor=INK, loc="upper right")
    ax.grid(axis="x", visible=False)
    ax.set_title("Weekly throughput: worked items fixed (batch closes from triage left out)")
    save(fig, "03_throughput.png")

    b = pd.read_csv(R / "forecast_backtest.csv", parse_dates=["forecast_from"])
    fig, ax = plt.subplots(figsize=(10, 4.0))
    ax.vlines(b["forecast_from"], b["p5"], b["p95"], color=GRAY, linewidth=6, alpha=0.35, label="forecast 5-95% range")
    ax.vlines(b["forecast_from"], b["p15"], b["p85"], color=BLUE, linewidth=6, alpha=0.8, label="forecast 15-85% range")
    inside = (b["actual"] >= b["p15"]) & (b["actual"] <= b["p85"])
    ax.scatter(b["forecast_from"][inside], b["actual"][inside], color=INK, s=22, zorder=3, label="actual, inside 15-85%")
    ax.scatter(b["forecast_from"][~inside], b["actual"][~inside], color=ORANGE, s=26, zorder=3, label="actual, outside")
    ax.set_ylabel("issues fixed in the next 8 weeks")
    ax.legend(frameon=False, labelcolor=INK, fontsize=8, loc="upper right", ncol=2)
    ax.grid(axis="x", visible=False)
    ax.set_title(f"Backtest: the 70% forecast range caught only {100 * s['backtest']['nominal_70_band_hit_rate']:.0f}% of 40 real outcomes")
    save(fig, "04_forecast_backtest.png")

    a = pd.read_csv(R / "wip_ages.csv")
    order = a.groupby("status")["age_days"].median().sort_values().index
    fig, ax = plt.subplots(figsize=(10, 3.9))
    rng = np.random.default_rng(0)
    for i, st in enumerate(order):
        v = a.loc[a["status"] == st, "age_days"].clip(lower=1)
        ax.scatter(v, i + rng.uniform(-0.25, 0.25, len(v)), s=10, alpha=0.6, color=BLUE, linewidths=0)
        ax.text(v.max() * 1.15, i, f"{len(v)}", va="center", color=DIM, fontsize=9)
    p85 = s["cycle_time_days"]["p85"]
    ax.axvline(p85, color=ORANGE, linewidth=1.5, linestyle="--")
    ax.text(p85 * 1.08, len(order) - 0.45, f"85% of fixes finish within {p85:.0f} days", color=ORANGE, fontsize=9)
    ax.set_xscale("log")
    ax.set_yticks(range(len(order)), order)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("days since the item entered work, as of 1 Oct 2026 (log scale)")
    ax.set_title(f"Ageing work in progress: {s['open_older_than_p85']} of {s['open_in_progress_or_review']} open items are older than 85% of fixes")
    save(fig, "05_wip_aging.png")
    print("charts written")


if __name__ == "__main__":
    main()
