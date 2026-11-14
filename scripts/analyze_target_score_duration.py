"""Analyze first arrival and duration of 2-1/1-2 using stored Supabase timelines.
No TheStatsAPI calls. Prints results in GitHub Actions logs.
"""
import os
from collections import defaultdict
from statistics import mean, median
from supabase import create_client

db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])

def pages(table, columns, batch=500):
    offset = 0
    while True:
        rows = (db.table(table).select(columns).order("match_id")
                .range(offset, offset + batch - 1).execute().data or [])
        yield from rows
        if len(rows) < batch:
            break
        offset += batch

matches = {}
for x in pages("historical_xg", "match_id,home_team,away_team,home_goals,away_goals"):
    if x["home_goals"] is not None and x["away_goals"] is not None:
        matches[x["match_id"]] = x
print("Results loaded:", len(matches), flush=True)

odds = {}
for row in pages("historical_match_odds", "match_id,odds_payload", 250):
    for bookmaker in ((row.get("odds_payload") or {}).get("data") or {}).get("bookmakers", []):
        if bookmaker.get("bookmaker") == "Bet365":
            market = (bookmaker.get("markets") or {}).get("match_odds") or {}
            try:
                odds[row["match_id"]] = (float(market["home"]["last_seen"]),
                                         float(market["away"]["last_seen"]))
            except (KeyError, TypeError, ValueError):
                pass
            break
print("Bet365 odds loaded:", len(odds), flush=True)

results = defaultdict(list)
verified = defaultdict(int)
excluded = defaultdict(int)
for row in pages("historical_match_events", "match_id,timeline_data", 200):
    mid = row["match_id"]
    if mid not in matches or mid not in odds:
        continue
    m = matches[mid]
    ho, ao = odds[mid]
    groups = ["All matches"]
    if 1.5 <= ho < 2.0 and 3.5 <= ao < 6.0:
        groups.append("United-Villa odds range")
    events = ((row.get("timeline_data") or {}).get("events") or [])
    goals = sorted((e for e in events if e.get("type") in ("goal", "own_goal")),
                   key=lambda e: int(e.get("sequence") or 0))
    h = a = 0
    first_hit = None
    next_goal = None
    valid = True
    for e in goals:
        team = (e.get("team") or {}).get("name")
        if team not in (m["home_team"], m["away_team"]):
            valid = False
            break
        home_scores = (team == m["home_team"]) != (e["type"] == "own_goal")
        if home_scores:
            h += 1
        else:
            a += 1
        minute = int(e.get("minute") or 0) + int(e.get("extra_time") or 0)
        if first_hit is not None and next_goal is None:
            next_goal = minute
        if first_hit is None and (h, a) in ((2, 1), (1, 2)):
            first_hit = minute
    if not valid or (h, a) != (m["home_goals"], m["away_goals"]):
        for group in groups:
            excluded[group] += 1
        continue
    for group in groups:
        verified[group] += 1
        if first_hit is not None:
            results[group].append((first_hit, next_goal))

for group in ("All matches", "United-Villa odds range"):
    rows = results[group]
    changed = [n - t for t, n in rows if n is not None]
    stayed = len(rows) - len(changed)
    print("\n" + "=" * 60)
    print(group)
    print("Verified matches:", verified[group], "Excluded inconsistent timelines:", excluded[group])
    print("Reached 2-1 or 1-2:", len(rows),
          "Hit rate: %.2f%%" % (100 * len(rows) / verified[group] if verified[group] else 0))
    print("Stayed until full-time:", stayed, "Changed again:", len(changed))
    if rows:
        print("Average first-hit minute: %.1f" % mean(t for t, _ in rows))
    if changed:
        print("Average minutes until next goal (changed matches): %.2f" % mean(changed))
        print("Median minutes until next goal (changed matches): %.1f" % median(changed))
        for limit in (2, 5, 10, 20):
            n = sum(d <= limit for d in changed)
            print("Next goal within %d minutes: %d / %d (%.1f%% of changed; %.1f%% of all hits)" %
                  (limit, n, len(changed), 100*n/len(changed), 100*n/len(rows)))
print("\nNo external API requests were made.")
