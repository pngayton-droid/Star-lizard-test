
"""PRO STAR LIZARD — SAFE HISTORICAL SCORE RECOVERY"""

import os
import time
import requests
from supabase import create_client

BASE = "https://api.thestatsapi.com/api"
API_KEY = os.environ["STATS_API_KEY"]

DB = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SECRET_KEY"],
)

HEADERS = {"Authorization": f"Bearer {API_KEY}"}

# First run: only 10 matches.
MAX_MATCHES = 750
REQUEST_INTERVAL = 1.2

FIELDS = (
    "competition_id",
    "home_goals",
    "away_goals",
    "home_ht_goals",
    "away_ht_goals",
)


def get_match(match_id):
    for attempt in range(5):
        response = requests.get(
            f"{BASE}/football/matches/{match_id}",
            headers=HEADERS,
            timeout=30,
        )

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

    result = (
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
    )

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

            (
                DB.table("historical_xg")
                .update(update)
                .eq("match_id", match_id)
                .is_("home_goals", "null")
                .execute()
            )

            updated += 1
            print(f"Saved: {values}", flush=True)

        except requests.RequestException as exc:
            print(f"API error: {exc}", flush=True)
            raise

        if index < len(matches):
            time.sleep(REQUEST_INTERVAL)

    print("\n=== FINAL SUMMARY ===", flush=True)
    print(f"Selected: {len(matches)}", flush=True)
    print(f"Updated attempts: {updated}", flush=True)
    print(f"Unavailable: {unavailable}", flush=True)
    print(f"Incomplete/skipped: {incomplete}", flush=True)


if __name__ == "__main__":
    main()
