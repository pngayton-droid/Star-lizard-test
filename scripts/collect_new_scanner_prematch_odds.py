"""Bounded pre-kickoff 1X2 snapshot collector for the ten selected leagues.

Runs once per invocation (no sleeping); stores verified bookmaker payloads only
before scheduled kickoff. Existing table name is legacy but holds new snapshots.
"""
import datetime as dt
import os
import json
from pathlib import Path
import requests
from supabase import create_client

BASE = "https://api.thestatsapi.com/api"
LEAGUES = {"comp_3039","comp_8321","comp_8814","comp_5840","comp_4643",
           "comp_0256","comp_3809","comp_8385","comp_8531","comp_6387"}
CAP = 35
RESERVE = 500
WINDOW_MINUTES = 25
TABLE = "ht_odds_trial_20261120"
SCHEDULE_PATH = Path(os.environ.get("SCANNER_SCHEDULE_PATH", ".cache/scanner_fixture_schedule.json"))
now = dt.datetime.now(dt.timezone.utc)
session = requests.Session()
session.headers["Authorization"] = "Bearer " + os.environ["STATS_API_KEY"]
db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])
calls = 0

def get(path, params=None):
    global calls
    if calls >= CAP:
        raise RuntimeError("API request cap reached")
    response = session.get(BASE + path, params=params, timeout=30)
    calls += 1
    quota = response.headers.get("X-Monthly-Quota-Remaining")
    if quota is not None and int(quota) <= RESERVE:
        raise RuntimeError("Quota reserve reached")
    if response.status_code in (404, 409, 429):
        print("Skipping response", response.status_code, path)
        return None
    response.raise_for_status()
    body = response.json()
    if path == "/football/matches":
        return {"data": body.get("data"), "meta": body.get("meta") or {}}
    return body.get("data")

def main():
    day = now.date().isoformat()
    # One fixture-feed collection per UTC date, cached across GitHub Actions runs.
    # Later ten-minute invocations read kickoff times from the cached schedule
    # without consuming any TheStatsAPI fixture-list requests.
    matches = None
    if SCHEDULE_PATH.is_file():
        try:
            cached = json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
            if cached.get("date") == day and isinstance(cached.get("matches"), list):
                matches = cached["matches"]
                print("Using cached daily kickoff schedule:", len(matches), "fixtures")
        except (OSError, ValueError, TypeError) as exc:
            print("Invalid schedule cache; refetching:", type(exc).__name__)
    if matches is None:
        matches = []
        # Follow the API's pagination metadata, like the working scanner feed.
        for page in range(1, 21):
            payload = get("/football/matches", {
                "date_from": day, "date_to": day, "sort": "utc_date",
                "per_page": 100, "page": page
            })
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                raise RuntimeError("Unexpected fixture feed; refusing to cache incomplete schedule")
            matches.extend(payload["data"])
            total_pages = int((payload.get("meta") or {}).get("total_pages") or 1)
            print("Fixture page:", page, "of", total_pages, "items:", len(payload["data"]))
            if page >= total_pages:
                break
            # The endpoint's meta.total_pages is authoritative. Our get()
            # wrapper returns data only, so a short final page also terminates.
            if len(payload["data"]) < 100:
                break
        else:
            raise RuntimeError("Fixture feed exceeded 20 pages; no complete schedule cached")
        SCHEDULE_PATH.parent.mkdir(parents=True, exist_ok=True)
        SCHEDULE_PATH.write_text(
            json.dumps({"date": day, "matches": matches}), encoding="utf-8"
        )
        print("Saved daily kickoff schedule:", len(matches), "fixtures")

    upcoming = []
    for match in matches:
        comp = match.get("competition") or {}
        cid = str(match.get("competition_id") or (comp.get("id") if isinstance(comp, dict) else "") or "")
        if cid not in LEAGUES:
            continue
        raw = match.get("utc_date")
        try:
            kickoff = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            remaining = (kickoff - now).total_seconds() / 60
        except (ValueError, TypeError):
            continue
        if not 0 < remaining <= WINDOW_MINUTES:
            continue
        # Do not trust stale odds_available from the morning fixture snapshot.
        # The odds endpoint itself determines current coverage.
        mid = str(match.get("id") or "")
        if mid:
            upcoming.append((kickoff, mid, match, cid))
    upcoming.sort()
    print("Eligible fixtures:", len(upcoming), "API calls:", calls)
    for kickoff, mid, _match, _cid in upcoming:
        print("Upcoming:", mid, "kickoff UTC:", kickoff.isoformat(), "minutes:", round((kickoff-now).total_seconds()/60,1))
    saved = 0
    for kickoff, mid, match, cid in upcoming:
        if calls >= CAP:
            print("Request cap reached; remaining fixtures deferred")
            break
        existing = (db.table(TABLE).select("bookmaker")
                    .eq("match_id", mid)
                    .eq("snapshot_kind", "prematch_within_20m")
                    .execute().data or [])
        existing_books = {str(row.get("bookmaker") or "").casefold() for row in existing}
        if existing_books:
            print("Already captured", mid, sorted(existing_books))
            continue
        # Verify kickoff is still in future immediately before fetching odds.
        observed = dt.datetime.now(dt.timezone.utc)
        if observed >= kickoff:
            continue
        payload = get("/football/matches/" + mid + "/odds",
                      {"bookmaker": "bet365,betfair-exchange,pinnacle"})
        if not isinstance(payload, dict):
            continue
        rows = []
        home = (match.get("home_team") or {}).get("name", "Home")
        away = (match.get("away_team") or {}).get("name", "Away")
        for book in payload.get("bookmakers") or []:
            if not isinstance(book, dict):
                continue
            name, markets = book.get("bookmaker"), book.get("markets")
            match_odds = (markets or {}).get("match_odds") if isinstance(markets, dict) else None
            if not name or not isinstance(match_odds, dict):
                continue
            # Only store bookmakers with a complete, valid pre-match 1X2.
            try:
                prices = [float((match_odds.get(side) or {}).get("last_seen"))
                          for side in ("home", "draw", "away")]
            except (TypeError, ValueError):
                continue
            if not all(price > 1 for price in prices):
                continue
            rows.append({"match_id": mid, "fixture": f"{home} v {away}",
                         "competition_id": cid, "observed_at": observed.isoformat(),
                         "match_status": "scheduled", "elapsed_minutes": None,
                         "bookmaker": name, "markets": markets,
                         "snapshot_kind": "prematch_within_20m"})
        if rows:
            # Existing match/bookmaker/snapshot rows are checked above;
            # the workflow concurrency group prevents overlapping runs.
            db.table(TABLE).insert(rows).execute()
            saved += len(rows)
            print("Saved:", mid, "bookmakers:", [row["bookmaker"] for row in rows])
        else:
            print("No complete 1X2 prices:", mid)
    print("FINISHED", "saved", saved, "calls", calls)

if __name__ == "__main__":
    main()
