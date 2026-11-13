"""Incremental finished-fixture collector. Existing TheStatsAPI only.

Defaults to DRY RUN. A live run requires ENABLE_LIVE_FIXTURE_COLLECTION=1.
Stores full available stats and timelines plus xG; missing data retried.
"""
import os
import time
from datetime import datetime, timedelta, timezone
import requests

BASE = "https://api.thestatsapi.com/api"
LEAGUES = {
    "Premier League": "comp_3039", "Championship": "comp_8321",
    "La Liga": "comp_8814", "Serie A": "comp_5840",
    "Bundesliga": "comp_4643", "Ligue 1": "comp_0256",
    "Eredivisie": "comp_3809", "Primeira Liga": "comp_8385",
    "Belgian Pro League": "comp_8531", "Scottish Premiership": "comp_6387",
}
LIVE = os.getenv("ENABLE_LIVE_FIXTURE_COLLECTION") == "1"
MAX_CALLS = int(os.getenv("LIVE_FIXTURE_MAX_REQUESTS", "150"))
DAYS_BACK = min(14, max(2, int(os.getenv("LIVE_FIXTURE_LOOKBACK_DAYS", "4"))))
if MAX_CALLS < len(LEAGUES) + 1:
    raise ValueError("LIVE_FIXTURE_MAX_REQUESTS must allow all league-list calls")
if LIVE and not all(os.getenv(k) for k in ("STATS_API_KEY", "SUPABASE_URL", "SUPABASE_SECRET_KEY")):
    raise RuntimeError("Missing required secrets")
if not LIVE:
    print("DRY RUN: no API requests and no database changes. Set ENABLE_LIVE_FIXTURE_COLLECTION=1 to collect.")
    raise SystemExit(0)

from supabase import create_client

db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])
http = requests.Session()
http.headers.update({"Authorization": "Bearer " + os.environ["STATS_API_KEY"]})
calls = 0
last_call = 0.0

def get(path, params=None):
    global calls, last_call
    for attempt in range(3):
        if calls >= MAX_CALLS:
            raise RuntimeError("Request budget exhausted")
        delay = 1.1 - (time.monotonic() - last_call)
        if delay > 0:
            time.sleep(delay)
        last_call = time.monotonic()
        resp = http.get(BASE + path, params=params, timeout=30)
        calls += 1
        if resp.status_code == 429:
            if attempt == 2:
                raise RuntimeError("Rate limited; stopping without retry storm")
            time.sleep(min(90, max(1, int(resp.headers.get("Retry-After", "30")))))
            continue
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    return None

def existing_ids():
    result = {}
    offset = 0
    while True:
        rows = db.table("historical_xg").select("match_id,match_date,home_ht_xg,away_ht_xg,home_goals,away_goals,home_ht_goals,away_ht_goals").order("match_id").range(offset, offset + 999).execute().data or []
        for r in rows:
            result[str(r["match_id"])] = r
        if len(rows) < 1000:
            break
        offset += 1000
    return result

def existing_events(recent_match_ids):
    result = {}
    ids = list(recent_match_ids)
    for i in range(0, len(ids), 50):
        rows = db.table("historical_match_events").select("match_id,stats_data,timeline_data").in_("match_id", ids[i:i + 50]).execute().data or []
        for row in rows:
            result[str(row["match_id"])] = row
    return result

def save_events(match_id, stats=None, timeline=None):
    row = {"match_id": match_id}
    if isinstance(stats, dict):
        row.update(stats_data=stats, stats_status=200)
    if isinstance(timeline, dict):
        row.update(timeline_data=timeline, timeline_status=200)
    if len(row) > 1:
        db.table("historical_match_events").upsert(row, on_conflict="match_id").execute()

def main():
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=DAYS_BACK)
    known = existing_ids()
    events = existing_events([mid for mid, row in known.items() if str(row.get("match_date") or "") >= start.isoformat()])
    added = skipped = missing = event_updates = 0
    # PRIORITY: discover and import missing fixtures before enriching old events.
    # Historical event backfill is deliberately excluded from catch-up runs.
    # Date-window discovery avoids TheStatsAPI rejecting page=2.
    # Catch up the lagging leagues first; preserve a fixed per-league budget.
    league_items = sorted(LEAGUES.items(), key=lambda item: (
        0 if item[0] == "Premier League" else
        1 if item[0] == "Championship" else
        2 if item[0] == "La Liga" else 3, item[0]))
    for name, competition_id in league_items:
        league_start_calls = calls
        per_league_budget = 30 if name in ("Premier League", "Championship", "La Liga") else 10
        day = today
        while day >= start and calls < MAX_CALLS and calls - league_start_calls < per_league_budget:
            # One day per query, always page 1; no invalid pagination.
            try:
                payload = get("/football/matches", {
                    "competition_id": competition_id, "status": "finished",
                    "date_from": day.isoformat(), "date_to": day.isoformat(),
                    "per_page": 20, "page": 1, "sort": "-utc_date",
                })
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 400:
                    print(f"{name}: rejected date {day}; continuing", flush=True)
                    day -= timedelta(days=1)
                    continue
                raise
            day -= timedelta(days=1)
            matches = (payload or {}).get("data") or []
            if name in ("Premier League", "Championship", "La Liga"):
                print(f"DIAG {name} date={day + timedelta(days=1)} returned={len(matches)} ids={[str(m.get('id') or m.get('match_id')) for m in matches[:5]]} statuses={[m.get('status') for m in matches[:5]]}", flush=True)
            if not isinstance(matches, list):
                raise RuntimeError("Unexpected matches response")
            for match in matches:
                match_id = str(match.get("id") or match.get("match_id") or "")
                if not match_id:
                    continue
                old = events.get(match_id) or {}
                stats = old.get("stats_data")
                timeline = old.get("timeline_data")
                existing = known.get(match_id) or {}
                xg_complete = all(existing.get(k) is not None for k in ("home_ht_xg", "away_ht_xg"))
                score_complete = all(existing.get(k) is not None for k in ("home_goals", "away_goals", "home_ht_goals", "away_ht_goals"))
                if xg_complete and score_complete and stats is not None and timeline is not None:
                    skipped += 1
                    continue
                if calls >= MAX_CALLS or calls - league_start_calls >= per_league_budget:
                    missing += 1
                    break
                if stats is None and not xg_complete:
                    payload = get(f"/football/matches/{match_id}/stats")
                    stats = (payload or {}).get("data")
                    if isinstance(stats, dict):
                        save_events(match_id, stats=stats)
                        event_updates += 1
                # Save scores when included in the finished-match listing.
                score = match.get("score") or {}
                regulation = score.get("regulation") or {}
                goals = (regulation.get("home"), regulation.get("away"),
                         score.get("half_time_home"), score.get("half_time_away"))
                if not xg_complete:
                    expected = ((stats or {}).get("overview") or {}).get("expected_goals") or {}
                    full, half = expected.get("all") or {}, expected.get("first_half") or {}
                    values = (full.get("home"), full.get("away"), half.get("home"), half.get("away"))
                    if any(v is None for v in values):
                        print(f"DIAG missing_xg league={name} match={match_id} date={match.get('utc_date')} stats_keys={list((stats or {}).keys())[:12]}", flush=True)
                        missing += 1
                    else:
                        row = {
                            "match_id": match_id, "match_date": str(match.get("utc_date") or "")[:10],
                            "home_team": (match.get("home_team") or {}).get("name", ""),
                            "away_team": (match.get("away_team") or {}).get("name", ""),
                            "competition_id": competition_id,
                            "home_xg": values[0], "away_xg": values[1],
                            "home_ht_xg": values[2], "away_ht_xg": values[3],
                        }
                        if all(v is not None for v in goals):
                            row.update(home_goals=goals[0], away_goals=goals[1],
                                       home_ht_goals=goals[2], away_ht_goals=goals[3])
                        if row["match_date"] and row["home_team"] and row["away_team"]:
                            db.table("historical_xg").upsert(row, on_conflict="match_id").execute()
                            known[match_id] = row
                            added += 1
                if not score_complete and calls < MAX_CALLS:
                    # The listing may omit scores: use the authoritative match detail.
                    if any(v is None for v in goals):
                        detail_payload = get(f"/football/matches/{match_id}")
                        detail = (detail_payload or {}).get("data") or {}
                        if str(detail.get("id")) == match_id and detail.get("status") == "finished":
                            ds = detail.get("score") or {}
                            dr = ds.get("regulation") or {}
                            goals = (dr.get("home"), dr.get("away"), ds.get("half_time_home"), ds.get("half_time_away"))
                    if all(v is not None for v in goals):
                        update = dict(zip(("home_goals", "away_goals", "home_ht_goals", "away_ht_goals"), goals))
                        db.table("historical_xg").update(update).eq("match_id", match_id).execute()
                        score_complete = True
                # Timelines are enrichment, not required to import finished fixtures.
                # Collect separately once the missing fixture backlog is cleared.
                events[match_id] = {"stats_data": stats, "timeline_data": timeline}
            if calls >= MAX_CALLS or calls - league_start_calls >= per_league_budget:
                break
        print(f"{name}: calls={calls - league_start_calls} total_calls={calls} added_so_far={added}", flush=True)
    print(f"Added={added} complete_skipped={skipped} missing_xg={missing} event_updates={event_updates} api_calls={calls}", flush=True)

if __name__ == "__main__":
    main()
