
"""PRO STAR LIZARD — SAFE HISTORICAL SCORE RECOVERY"""

import os
import time
import requests
from httpx import RemoteProtocolError, ReadError, ConnectError, ReadTimeout
from supabase import create_client

BASE = "https://api.thestatsapi.com/api"
API_KEY = os.environ["STATS_API_KEY"]

DB = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SECRET_KEY"],
)

DB_RETRY_ERRORS = (RemoteProtocolError, ReadError, ConnectError, ReadTimeout, requests.RequestException)


def db_call(operation, label):
    for attempt in range(6):
        try:
            return operation()
        except Exception as exc:
            # Transient Supabase/PostgREST HTTP/2 connection interruptions.
            if not isinstance(exc, DB_RETRY_ERRORS):
                raise
            if attempt == 5:
                raise
            delay = min(40, 2 ** (attempt + 1))
            print(f"SUPABASE_RETRY {label} attempt={attempt + 1} wait={delay}s: {type(exc).__name__}", flush=True)
            time.sleep(delay)


HEADERS = {"Authorization": f"Bearer {API_KEY}"}

# First run: only 10 matches.
MAX_MATCHES = 1700
REQUEST_INTERVAL = 1.5
MAX_API_CALLS = 1700
MIN_QUOTA_REMAINING = 300
api_calls = 0

FIELDS = (
    "competition_id",
    "home_goals",
    "away_goals",
    "home_ht_goals",
    "away_ht_goals",
)


def get_match(match_id):
    global api_calls
    for attempt in range(5):
        if api_calls >= MAX_API_CALLS:
            raise RuntimeError('Recovery request budget exhausted')
        response = requests.get(
            f"{BASE}/football/matches/{match_id}",
            headers=HEADERS,
            timeout=30,
        )

        api_calls += 1
        remaining = response.headers.get("X-Monthly-Quota-Remaining")
        if remaining is not None and remaining.isdigit() and int(remaining) <= MIN_QUOTA_REMAINING:
            raise RuntimeError(f"Monthly quota safety floor reached: {remaining}")
        if response.status_code == 429:
            retry = response.headers.get("Retry-After", "30")
            try:
                delay = max(float(retry), 1)
            except ValueError:
                delay = 30

            print(f"Rate limited. Waiting {delay}s", flush=True)
            time.sleep(delay)
            continue

        if response.status_code == 404:
            return None

        response.raise_for_status()
        return response.json().get("data") or {}

    raise RuntimeError(f"API retries exhausted for {match_id}")


def main():
    print("PRO STAR LIZARD - HISTORICAL SCORE RECOVERY", flush=True)

    result = db_call(lambda: (
        DB.table("historical_xg")
        .select(
            "match_id,match_date,home_team,away_team,"
            "competition_id,home_goals,away_goals,"
            "home_ht_goals,away_ht_goals"
        )
        .like("match_id", "mt_%")
        .is_("home_goals", "null")
        .order("match_date", desc=True)
        .limit(MAX_MATCHES)
        .execute()
    ), "load_missing_matches")

    matches = result.data or []
    print(f"Matches selected: {len(matches)}", flush=True)

    updated = 0
    unavailable = 0
    incomplete = 0

    for index, match in enumerate(matches, 1):
        match_id = match["match_id"]

        print(
            f"\n[{index}/{len(matches)}] "
            f"{match['match_date']} "
            f"{match['home_team']} v {match['away_team']}",
            flush=True,
        )

        try:
            data = get_match(match_id)

            if not data:
                unavailable += 1
                print("Match unavailable", flush=True)
                continue

            if str(data.get("id")) != match_id:
                incomplete += 1
                print("Match ID mismatch - skipped", flush=True)
                continue

            if data.get("status") != "finished":
                incomplete += 1
                print("Not finished - skipped", flush=True)
                continue

            score = data.get("score") or {}
            regulation = score.get("regulation") or {}

            values = {
                "competition_id": data.get("competition_id"),
                "home_goals": regulation.get("home"),
                "away_goals": regulation.get("away"),
                "home_ht_goals": score.get("half_time_home"),
                "away_ht_goals": score.get("half_time_away"),
            }

            if any(value is None for value in values.values()):
                incomplete += 1
                print(f"Incomplete score fields: {values}", flush=True)
                continue

            if (
                values["home_ht_goals"] > values["home_goals"]
                or values["away_ht_goals"] > values["away_goals"]
            ):
                incomplete += 1
                print("Invalid HT/FT score relationship", flush=True)
                continue

            # Only write the five new fields.
            # Never overwrite existing xG.
            update = {
                field: value
                for field, value in values.items()
                if match.get(field) is None
            }

            if not update:
                print("Already populated", flush=True)
                continue

            saved = db_call(lambda: (
                DB.table("historical_xg")
                .update(update)
                .eq("match_id", match_id)
                .is_("home_goals", "null")
                .execute()
            ), f"save_{match_id}")

            if not saved.data:
                print("Already recovered by another job; skipped", flush=True)
                continue
            updated += 1
            print(f"Saved: {values}", flush=True)

        except RuntimeError as exc:
            print(f"Stopping safely: {exc}", flush=True)
            break
        except DB_RETRY_ERRORS as exc:
            print(f"Connection failed after retries; stopping to preserve progress: {exc}", flush=True)
            break

        if index < len(matches):
            time.sleep(REQUEST_INTERVAL)

    print("\n=== FINAL SUMMARY ===", flush=True)
    print(f"Selected: {len(matches)}", flush=True)
    print(f"Updated attempts: {updated}", flush=True)
    print(f"Unavailable: {unavailable}", flush=True)
    print(f"Incomplete/skipped: {incomplete}", flush=True)


if __name__ == "__main__":
    main()
