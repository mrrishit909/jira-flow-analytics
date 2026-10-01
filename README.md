# Delivery flow analytics from Jira (Apache Cassandra) → Confluence report

The metrics an agile delivery lead or business analyst reports from Jira, computed from scratch on a real team's
public Jira:
- cycle time and lead time;
- where work waits;
- throughput;
- ageing work in progress;
- a delivery forecast that is backtested, not just asserted.

The result is a report ready to publish as a Confluence page.

Build log: https://mrrishit909.github.io/projects/jira-flow-analytics/ · [Report preview](https://mrrishit909.github.io/projects/jira-flow-analytics/confluence/)

## Data

Apache Software Foundation public Jira (issues.apache.org), project CASSANDRA, through the REST API (no login).
7,592 issues resolved since 2021 or still open, each with its full status history. Only dates, types and status
changes are kept, never titles or comments. Not committed.

**A sampling trap avoided:** the first download selected issues *created* since 2021. That silently drops long-running
work created earlier, which biases cycle times short. The final download selects by *resolution* date (or still open).

## Steps

| Step | File | What it does |
|---|---|---|
| 1 | `download.py` | issues and status histories, paged through the REST API |
| 2 | `analysis.py` | status timelines → cycle/lead time, time in status, throughput, WIP, Little's Law, forecast + backtest |
| 3 | `charts.py` | cycle-time scatterplot, time in status, throughput, backtest, ageing WIP |
| 4 | `confluence.py` | the report in Confluence storage format, plus an HTML preview |
| 5 | `check.py` | status stretches tile each issue's life; 300 cycle times recomputed; throughput and backtest reconcile |

## Definitions

- **Cycle time:** first move into In Progress, Patch Available or Review In Progress → resolution. Covers issues
  resolved as Fixed from 2022 (2,498).
- **Lead time:** created → resolution.
- **Throughput:** worked items fixed per week. 395 issues closed as Fixed straight from triage are batch closes; one day
  in April 2026 closed 55 at once. They are not delivered work and are left out.
- **Waiting statuses:** Patch Available, Needs Committer, Ready to Commit, Changes Suggested, Awaiting Feedback.
- **Working statuses:** In Progress, Review In Progress, Testing.

## Findings (to 1 October 2026)

| Measure | Value |
|---|---:|
| Cycle time, 50% / 85% / 95% of fixes | **7 / 60 / 271 days** |
| Lead time, 50% / 85% | 16 / 154 days |
| Throughput, last 26 weeks | 9.5 fixes a week |
| Cycle time spent waiting | 48% |
| Median flow efficiency (working ÷ total) | 13% |

- **The bottleneck is review.** "Patch Available" (code written, waiting for a reviewer) is 33% of all cycle time, the
  largest single status. Bugs take a median of 5 days and new features 22.
- **Zombie tickets.** 305 of the 397 items currently shown as in progress or in review are older than 60 days, the 85th
  percentile of real fixes. The median "In Progress" item entered work 3.3 years ago.
- **Little's Law catches it.** Average work in progress (273) ÷ throughput (1.44/day) implies 189-day cycle times,
  against 64 days measured. Counting only items that were eventually fixed, average WIP is 55, which implies about
  38 days in working states, the same order. About 80% of apparent WIP is stale.
- **The forecast is honest about itself.** A Monte Carlo forecast from the last 26 weeks gives a median of 75 fixes in
  the next 8 weeks (5–95%: 57–93). Backtested from 40 past dates, though, its 70% range caught only 50% of outcomes and
  its 90% range 63%. Misses fell on both sides (22.5% below, 27.5% above), so the ranges are too narrow, not biased.
  Longer history and 4-week blocks didn't fix it. Throughput comes in bursts, so re-forecast weekly.

**Recommendations in the report:**
1. Add reviewer capacity, for example a rota or a limit on open patches.
2. Send tickets untouched for 90 days back to the backlog.
3. Use 60 days as the service-level expectation.
4. Re-forecast weekly.

## Confluence

`confluence/flow-report.storage.xhtml` is the page body in Confluence's storage format, with the charts as attachments.
It's what Confluence's REST API accepts. `confluence/preview.html` shows the same content.

**Not yet published to a live Confluence space:** that step waits for a Confluence Cloud site.

## Not done

- Cassandra's workflow is open-source review culture (volunteer reviewers), so a company team's numbers would differ.
- "Working" statuses measure ticket state, not hours: an item can sit In Progress untouched, so flow efficiency is an upper bound.

## Run it

```
python3 -m venv venv && ./venv/bin/pip install pandas numpy matplotlib scipy
./venv/bin/python download.py && ./venv/bin/python analysis.py && ./venv/bin/python charts.py && ./venv/bin/python confluence.py && ./venv/bin/python check.py
```
