"""Step 2: flow metrics for Apache Cassandra's Jira, the numbers an agile delivery lead reports.

    ./venv/bin/python analysis.py

Definitions (Kanban flow metrics):
  cycle time   first move into a working state (In Progress, Patch Available or Review In Progress) -> resolved, Fixed issues
  lead time    created -> resolved, Fixed issues
  throughput   Fixed issues resolved per week
  WIP          issues sitting in a working or review state on a given day
  flow eff.    share of an issue's life spent in hands-on states rather than waiting
Forecast: Monte Carlo resampling of the last 26 weeks' throughput, backtested at 40 past dates.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
AS_OF = pd.Timestamp("2026-10-01", tz="UTC")
START = {"In Progress", "Patch Available", "Review In Progress"}
ACTIVE = {"In Progress", "Review In Progress", "Testing", "Requires Testing"}          # someone is working on it
WAITING = {"Patch Available", "Needs Committer", "Ready to Commit", "Changes Suggested", "Needs Reviewer", "Awaiting Feedback"}
BACKLOG = {"Triage Needed", "Open"}
WIP_STATES = ACTIVE | WAITING


def load():
    d = pd.DataFrame(json.loads((HERE / "data" / "raw" / "issues.json").read_text()))
    d["created"] = pd.to_datetime(d["created"], utc=True)
    d["resolved"] = pd.to_datetime(d["resolved"], utc=True)
    d.loc[d["resolved"] > AS_OF, ["resolved", "resolution"]] = [pd.NaT, None]           # resolved after the cut-off = open
    # A few issues sit in Resolved/Closed with an empty resolution field: closed, not open. Date them by their last
    # move into that status; their resolution stays empty, so they never count as Fixed.
    closed = d["resolved"].isna() & d["status"].isin(["Resolved", "Closed"])
    last_close = d.loc[closed, "moves"].apply(lambda ms: max((pd.Timestamp(m["at"]).tz_convert("UTC") for m in ms
                                                               if m["to"] in ("Resolved", "Closed")), default=pd.NaT))
    d.loc[closed, "resolved"] = last_close
    return d


def segments(d):
    """One row per (issue, status stretch): from when it entered the status until it left (or resolution / AS_OF)."""
    rows = []
    for r in d.itertuples():
        moves = sorted(r.moves, key=lambda m: m["at"])
        status = moves[0]["from"] if moves else r.status
        t = r.created
        end = r.resolved if pd.notna(r.resolved) else AS_OF
        for m in moves:
            at = pd.Timestamp(m["at"]).tz_convert("UTC")
            if at > AS_OF:
                break
            rows.append((r.key, status, t, at))
            status, t = m["to"], at
        if status != "Resolved" and status != "Closed":
            rows.append((r.key, status, t, end))
    s = pd.DataFrame(rows, columns=["key", "status", "start", "end"])
    s["days"] = (s["end"] - s["start"]).dt.total_seconds().clip(lower=0) / 86400
    return s


def cycle_times(d):
    fixed = d[(d["resolution"] == "Fixed") & d["resolved"].notna()].copy()
    def first_start(moves):
        ts = [pd.Timestamp(m["at"]).tz_convert("UTC") for m in moves if m["to"] in START]
        return min(ts) if ts else pd.NaT
    fixed["started"] = fixed["moves"].apply(first_start)
    fixed["cycle_days"] = (fixed["resolved"] - fixed["started"]).dt.total_seconds() / 86400
    fixed["lead_days"] = (fixed["resolved"] - fixed["created"]).dt.total_seconds() / 86400
    return fixed


def forecast(weekly, at, horizon=8, history=26, block=1, n=10000, rng=None):
    """Monte Carlo: build `horizon` weeks of throughput by resampling the `history` weeks before `at`, either single
    weeks (block=1) or runs of `block` consecutive weeks, which keeps release-cycle bursts together."""
    past = weekly[(weekly.index < at) & (weekly.index >= at - pd.Timedelta(weeks=history))].values
    starts = rng.integers(0, len(past) - block + 1, size=(n, -(-horizon // block)))
    sims = np.stack([past[starts + k] for k in range(block)], axis=2).reshape(n, -1)[:, :horizon].sum(axis=1)
    return np.percentile(sims, [5, 10, 15, 50, 85, 90, 95]), sims


def backtest(weekly, rng, **kw):
    rows = []
    for at in pd.date_range(pd.Timestamp("2022-06-06", tz="UTC"), weekly.index[-1] - pd.Timedelta(weeks=8), periods=40).normalize():
        at = weekly.index[weekly.index.get_indexer([at], method="nearest")[0]]
        b, _ = forecast(weekly, at, rng=rng, **kw)
        actual = int(weekly[(weekly.index >= at) & (weekly.index < at + pd.Timedelta(weeks=8))].sum())
        rows.append({"forecast_from": at.strftime("%Y-%m-%d"), "p5": b[0], "p10": b[1], "p15": b[2], "p50": b[3], "p85": b[4],
                     "p90": b[5], "p95": b[6], "actual": actual,
                     "inside_p15_p85": bool(b[2] <= actual <= b[4]), "inside_p10_p90": bool(b[1] <= actual <= b[5]),
                     "inside_p5_p95": bool(b[0] <= actual <= b[6])})
    return pd.DataFrame(rows)


def main():
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    rng = np.random.default_rng(0)
    d = load()
    seg = segments(d)
    fx = cycle_times(d)
    win = fx[(fx["resolved"] >= "2022-01-01") & fx["started"].notna()].copy()

    funnel = {"issues downloaded (resolved since 2021 or still open)": int(len(d)),
              "resolved as Fixed by 30 Sep 2026": int(len(fx)), "of which resolved 2022 onward": int((fx["resolved"] >= "2022-01-01").sum()),
              "... and passed through a working state (cycle time defined)": int(len(win)), "still open": int(d["resolved"].isna().sum()),
              "Fixed since 2022 straight from triage/backlog (batch closes, left out of throughput)": int(((fx["resolved"] >= "2022-01-01") & fx["started"].isna()).sum())}

    pct = lambda s: {f"p{q}": float(np.percentile(s, q)) for q in (50, 70, 85, 95)}
    win["year"] = win["resolved"].dt.year
    by_year = win.groupby("year").agg(n=("cycle_days", "size"), median=("cycle_days", "median"),
                                      p85=("cycle_days", lambda s: np.percentile(s, 85)), lead_median=("lead_days", "median"))
    by_year.round(2).to_csv(out / "cycle_time_by_year.csv")
    by_type = win.groupby("type").agg(n=("cycle_days", "size"), median=("cycle_days", "median"),
                                      p85=("cycle_days", lambda s: np.percentile(s, 85))).query("n >= 30")
    by_type.round(2).to_csv(out / "cycle_time_by_type.csv")
    win[["resolved", "cycle_days", "type"]].assign(resolved=lambda x: x["resolved"].dt.strftime("%Y-%m-%d")).round(3).to_csv(
        out / "cycle_times.csv", index=False)                                        # one row per issue: date, days, type (no titles)

    s = seg.merge(win[["key", "started"]], on="key")
    s = s[s["start"] >= s["started"]]                                          # only the part of each issue's life inside its cycle time
    tis = s.groupby("status")["days"].agg(["sum", "count"])
    tis["share"] = tis["sum"] / tis["sum"].sum()
    tis["kind"] = np.where(tis.index.isin(ACTIVE), "working", np.where(tis.index.isin(WAITING), "waiting", "other"))
    per_issue = s.assign(work=s["status"].isin(ACTIVE) * s["days"]).groupby("key").agg(work=("work", "sum"), total=("days", "sum"))
    eff = (per_issue["work"] / per_issue["total"]).where(per_issue["total"] > 0)
    tis.sort_values("sum", ascending=False).round(4).to_csv(out / "time_in_status.csv")

    weeks = pd.date_range(pd.Timestamp("2021-01-04", tz="UTC"), AS_OF, freq="W-MON")
    worked = fx[fx["started"].notna()]          # same population as cycle time: excludes batch closes straight from triage
    weekly = worked.set_index("resolved").resample("W-MON", label="left", closed="left")["key"].count().reindex(weeks, fill_value=0)
    weekly = weekly[weekly.index + pd.Timedelta(days=7) <= AS_OF]                    # complete weeks only
    weekly.rename("fixed").to_csv(out / "weekly_throughput.csv", index_label="week")

    days = pd.date_range(pd.Timestamp("2022-01-01", tz="UTC"), AS_OF - pd.Timedelta(days=1), freq="D")
    wseg = seg[seg["status"].isin(WIP_STATES)]
    wip = pd.Series([int(((wseg["start"] <= t) & (wseg["end"] > t)).sum()) for t in days], index=days)
    fseg = wseg[wseg["key"].isin(fx.loc[fx["started"].notna(), "key"])]                # only items that were eventually fixed
    wip_fixed = pd.Series([int(((fseg["start"] <= t) & (fseg["end"] > t)).sum()) for t in days], index=days)
    wip.resample("W-MON").mean().round(2).rename("wip").to_csv(out / "weekly_wip.csv", index_label="week")
    w2 = fx[(fx["resolved"] >= "2022-01-01")]
    tp_per_day = len(w2[w2["started"].notna()]) / len(days)
    little = {"avg_wip": float(wip.mean()), "throughput_per_day": tp_per_day,
              "implied_avg_cycle_days": float(wip.mean() / tp_per_day), "measured_avg_cycle_days": float(win["cycle_days"].mean()),
              "avg_wip_items_that_were_fixed": float(wip_fixed.mean()),
              "implied_avg_cycle_days_fixed_only": float(wip_fixed.mean() / tp_per_day),
              "note": "Little's Law: average WIP = throughput x average time in WIP; WIP here counts only working/review states"}

    open_ = d[d["resolved"].isna() & d["status"].isin(WIP_STATES)].copy()
    entered = seg[seg["status"].isin(WIP_STATES)].groupby("key")["start"].min()
    open_["age_days"] = (AS_OF - open_["key"].map(entered)).dt.total_seconds() / 86400
    p85 = float(np.percentile(win["cycle_days"], 85))
    aging = open_.groupby("status").agg(items=("key", "size"), median_age=("age_days", "median"),
                                        over_p85=("age_days", lambda a: int((a > p85).sum())))
    aging.round(1).to_csv(out / "wip_aging.csv")
    open_[["status", "age_days"]].round(1).to_csv(out / "wip_ages.csv", index=False)

    cal = []
    for name, kw in {"last 13 weeks": dict(history=13), "last 26 weeks": dict(history=26), "last 52 weeks": dict(history=52),
                     "last 52 weeks, 4-week blocks": dict(history=52, block=4)}.items():
        b = backtest(weekly, rng, **kw)
        cal.append({"history": name, "nominal_70_p15_p85": b["inside_p15_p85"].mean(), "nominal_80_p10_p90": b["inside_p10_p90"].mean(),
                    "nominal_90_p5_p95": b["inside_p5_p95"].mean()})
        if name == "last 26 weeks":
            bt = b
    cal = pd.DataFrame(cal)
    cal.round(3).to_csv(out / "forecast_calibration.csv", index=False)
    bt.round(1).to_csv(out / "forecast_backtest.csv", index=False)
    band, sims = forecast(weekly, weekly.index[-1] + pd.Timedelta(weeks=1), history=26, rng=rng)
    hist = np.bincount(sims.astype(int))
    pd.DataFrame({"fixed_in_8_weeks": np.arange(len(hist)), "share": hist / hist.sum()}).query("share > 0").round(5).to_csv(out / "forecast_distribution.csv", index=False)

    summary = {"as_of": str(AS_OF.date()), "funnel": funnel, "cycle_time_days": pct(win["cycle_days"]), "lead_time_days": pct(win["lead_days"]),
               "flow_efficiency_median": float(eff.median()), "flow_efficiency_mean": float(eff.mean()),
               "waiting_share_of_cycle_time": float(tis.loc[tis["kind"] == "waiting", "sum"].sum() / tis["sum"].sum()),
               "throughput_last_26_weeks": {"mean": float(weekly.iloc[-26:].mean()), "median": float(weekly.iloc[-26:].median())},
               "forecast_next_8_weeks": {"p5": float(band[0]), "p15": float(band[2]), "p50": float(band[3]), "p85": float(band[4]), "p95": float(band[6])},
               "forecast_method": "Monte Carlo from the last 26 weeks' weekly throughput",
               "backtest": {"forecasts": int(len(bt)), "nominal_70_band_hit_rate": float(bt["inside_p15_p85"].mean()),
                            "nominal_90_band_hit_rate": float(bt["inside_p5_p95"].mean())},
               "little": little, "open_in_progress_or_review": int(len(open_)), "open_older_than_p85": int((open_["age_days"] > p85).sum())}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
    print(json.dumps(summary, indent=1, default=float))
    print(by_year.round(1).to_string())
    print(by_type.round(1).to_string())
    print(tis.sort_values("sum", ascending=False).round(3).to_string())
    print(aging.round(1).to_string())
    print(cal.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
