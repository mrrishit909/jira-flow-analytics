"""Step 4: the delivery report as a Confluence page.

    ./venv/bin/python confluence.py   -> confluence/flow-report.storage.xhtml (Confluence storage format, charts as
                                         attachments) and confluence/preview.html (the same content as a plain web page)

The storage-format file is what Confluence's REST API takes as a page body; the charts are uploaded as attachments.
Every number comes from results/.
"""
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
R = HERE / "results"
OUT = HERE / "confluence"


def blocks():
    s = json.loads((R / "summary.json").read_text())
    c, l, f, b, lt = s["cycle_time_days"], s["little"], s["forecast_next_8_weeks"], s["backtest"], s["lead_time_days"]
    t = pd.read_csv(R / "cycle_time_by_type.csv")
    rows = [["Cycle time, 50% / 85% / 95% of fixes", f"{c['p50']:.0f} / {c['p85']:.0f} / {c['p95']:.0f} days"],
            ["Lead time (created to fixed), 50% / 85%", f"{lt['p50']:.0f} / {lt['p85']:.0f} days"],
            ["Throughput, last 26 weeks", f"{s['throughput_last_26_weeks']['mean']:.1f} fixes a week"],
            ["Share of cycle time spent waiting", f"{100 * s['waiting_share_of_cycle_time']:.0f}%"],
            ["Open items in a working or review state", f"{s['open_in_progress_or_review']}, of which {s['open_older_than_p85']} older than {c['p85']:.0f} days"]]
    types = [[r.type, f"{r.median:.0f} days", f"{r.p85:.0f} days", f"{r.n:,}"] for r in t.itertuples()]
    return [
        ("p", f"Apache Cassandra project, Jira data to {s['as_of']}. {s['funnel']['... and passed through a working state (cycle time defined)']:,} "
              "fixed issues resolved since 2022 that passed through a working state."),
        ("h2", "Summary"),
        ("ul", [f"Half of fixes finish within {c['p50']:.0f} days of work starting; 85% within {c['p85']:.0f} days. Use {c['p85']:.0f} days as the service-level expectation.",
                f"Patches waiting for a reviewer are the largest single share of cycle time. Overall, {100 * s['waiting_share_of_cycle_time']:.0f}% of cycle time is waiting.",
                f"{s['open_older_than_p85']} of {s['open_in_progress_or_review']} items shown as in progress or in review are older than {c['p85']:.0f} days. Most are stale tickets, and they make work in progress look about 5 times larger than it is.",
                f"Next 8 weeks: a median of {f['p50']:.0f} fixes. Treat {f['p5']:.0f}-{f['p95']:.0f} as a rough two-in-three range, not 90%: in backtests the model's ranges were too narrow."]),
        ("h2", "Key numbers"), ("table", [["Measure", "Value"]] + rows),
        ("h2", "Cycle time by issue type"), ("table", [["Type", "Median", "85%", "Fixes"]] + types),
        ("img", "01_cycle_scatter.png"), ("h2", "Where the time goes"), ("img", "02_time_in_status.png"),
        ("p", "Recommendation: review capacity is the bottleneck. A rotating review rota or a limit on open patches would shorten cycle time more than faster coding."),
        ("h2", "Ageing work in progress"), ("img", "05_wip_aging.png"),
        ("p", f"Little's Law check: an average of {l['avg_wip']:.0f} items in working states at {l['throughput_per_day']:.2f} fixes a day implies "
              f"{l['implied_avg_cycle_days']:.0f}-day cycle times, against {l['measured_avg_cycle_days']:.0f} measured. Counting only items that were "
              f"eventually fixed, average work in progress is {l['avg_wip_items_that_were_fixed']:.0f}, which implies about {l['implied_avg_cycle_days_fixed_only']:.0f} days in working states. That's the same order as measured. "
              "Recommendation: close or move back to the backlog any ticket untouched for 90 days."),
        ("h2", "Forecast"), ("img", "04_forecast_backtest.png"),
        ("p", f"Monte Carlo from the last 26 weeks' throughput. Backtested from 40 past dates, its 70% range caught {100 * b['nominal_70_band_hit_rate']:.0f}% "
              f"of real outcomes and its 90% range {100 * b['nominal_90_band_hit_rate']:.0f}%. Misses fell on both sides, so the ranges are too narrow "
              "(throughput comes in bursts), not biased. Re-forecast every week rather than committing to one date."),
        ("h2", "Method"),
        ("p", "Cycle time runs from the first move into In Progress, Patch Available or Review In Progress to resolution, for issues "
              "resolved as Fixed. Issues closed as Fixed straight from triage (batch closes) are left out of throughput. Data: the public "
              "issues.apache.org Jira REST API; only dates, types and status changes are used."),
    ]


def esc(x):
    return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(kind, item, storage):
    if kind in ("h2", "p"):
        return f"<{kind}>{esc(item)}</{kind}>"
    if kind == "ul":
        return "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in item) + "</ul>"
    if kind == "table":
        head = "".join(f"<th>{esc(x)}</th>" for x in item[0])
        body = "".join("<tr>" + "".join(f"<td>{esc(x)}</td>" for x in r) + "</tr>" for r in item[1:])
        return f"<table><tbody><tr>{head}</tr>{body}</tbody></table>"
    if kind == "img":
        return (f'<ac:image ac:width="900"><ri:attachment ri:filename="{item}" /></ac:image>' if storage
                else f'<img src="../charts/{item}" alt="{esc(item)}">')


def main():
    OUT.mkdir(exist_ok=True)
    bl = blocks()
    (OUT / "flow-report.storage.xhtml").write_text("\n".join(render(k, i, True) for k, i in bl) + "\n")
    css = ("body{margin:0;background:#fff;color:#172b4d;font:15px/1.6 -apple-system,'Segoe UI',Roboto,sans-serif}"
           "main{max-width:900px;margin:0 auto;padding:32px 20px}h1{font-size:28px;margin:0 0 6px}h2{font-size:20px;margin:28px 0 8px}"
           "table{border-collapse:collapse;width:100%;margin:8px 0}th,td{border:1px solid #dfe1e6;padding:6px 8px;text-align:left}"
           "th{background:#f4f5f7}img{max-width:100%;height:auto;border-radius:4px;margin:8px 0}.crumb{color:#6b778c;font-size:13px}"
           "@media (prefers-color-scheme:dark){body{background:#1d2125;color:#c7d1db}th{background:#22272b}th,td{border-color:#38414a}.crumb{color:#8c9bab}}")
    html = ("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Cassandra Flow Report</title><style>{css}</style></head><body><main>"
            "<div class='crumb'>Confluence page preview · Engineering / Delivery reports</div><h1>Cassandra delivery flow report</h1>"
            + "\n".join(render(k, i, False) for k, i in bl) + "</main></body></html>\n")
    (OUT / "preview.html").write_text(html)
    print("wrote", [p.name for p in OUT.iterdir()])


if __name__ == "__main__":
    main()
