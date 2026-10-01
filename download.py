"""Step 1: Apache Cassandra's public Jira issues with their full status history.

    ./venv/bin/python download.py

Source: the Apache Software Foundation's public Jira (issues.apache.org/jira, REST API v2, no login needed).
Issues resolved since 2021 or still open (created by 30 Sep 2026), with the changelog (every status change).
Only key, type, priority, dates and status transitions are kept, not titles or comments. Saved to data/raw/ (not committed).
"""
import json
import ssl
import time
import urllib.parse
import urllib.request
from pathlib import Path

RAW = Path(__file__).parent / "data" / "raw"
API = "https://issues.apache.org/jira/rest/api/2/"
# Selected by RESOLUTION date (or still open), not creation date: filtering on creation would drop long-running
# items created before 2021 and so bias cycle times short.
JQL = ("project = CASSANDRA AND created <= 2026-09-30 AND (resolved >= 2021-01-01 OR resolution is EMPTY) "
       "ORDER BY created ASC")
CTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem")


def get(path, **params):
    url = API + path + "?" + urllib.parse.urlencode(params)
    for attempt in range(5):
        try:
            return json.load(urllib.request.urlopen(url, context=CTX, timeout=120))
        except Exception:
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(url)


def slim(issue, histories):
    f = issue["fields"]
    moves = [{"at": h["created"], "from": it["fromString"], "to": it["toString"]}
             for h in histories for it in h["items"] if it["field"] == "status"]
    return {"key": issue["key"], "type": f["issuetype"]["name"], "priority": (f.get("priority") or {}).get("name"),
            "created": f["created"], "resolved": f.get("resolutiondate"), "resolution": (f.get("resolution") or {}).get("name"),
            "status": f["status"]["name"], "moves": moves}


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    out, start, refetched = [], 0, 0
    while True:
        page = get("search", jql=JQL, startAt=start, maxResults=100, expand="changelog",
                   fields="issuetype,priority,created,resolutiondate,resolution,status")
        for issue in page["issues"]:
            cl = issue["changelog"]
            hist = cl["histories"]
            if cl.get("total", len(hist)) > len(hist):              # long histories come back truncated: fetch in full
                hist = get(f"issue/{issue['key']}", expand="changelog", fields="status")["changelog"]["histories"]
                refetched += 1
            out.append(slim(issue, hist))
        start += len(page["issues"])
        print(start, "/", page["total"])
        if start >= page["total"] or not page["issues"]:
            break
        time.sleep(0.5)
    (RAW / "issues.json").write_text(json.dumps(out))
    print(len(out), "issues;", refetched, "changelogs fetched in full")
