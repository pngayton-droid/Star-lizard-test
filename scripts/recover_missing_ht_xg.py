"""
PRO STAR LIZARD
Recover missing half-time xG from TheStatsAPI.

Only updates missing HT xG fields.
Preserves existing full-time xG.
"""

import os
import time
import requests
from supabase import create_client

BASE = "https://api.thestatsapi.com/api"

API_KEY = os.environ["STATS_API_KEY"]

DB = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SECRET_KEY"]
)

SESSION = requests.Session()
SESSION.headers.update({
    "Authorization": f"Bearer {API_KEY}"
})

# Small, controlled recovery batch.
# Increase after verifying the first run.
MAX_MATCHES = 350

# Respect the API's 1-request-per-second limit.
REQUEST_INTERVAL = 1.2


def get_missing_matches():
    """Find records with missing half-time xG."""

    response = (
        DB.table("historical_xg")
        .select(
            "match_id,match_date,home_team,away_team,"
            "home_ht_xg,away_ht_xg"
        )
        .or_(
            "home_ht_xg.is.null,"
            "away_ht_xg.is.null"
        )
        .like("match_id", "mt_%")
        .order("match_date", desc=True)
        .limit(MAX_MATCHES)
        .execute()
    )

    return response.data or []


def get_ht_xg(match_id):
    """Retrieve first-half xG from TheStatsAPI."""

    url = f"{BASE}/football/matches/{match_id}/stats"

    for attempt in range(4):

        try:
            response = SESSION.get(
                url,
                timeout=30
            )

            if response.status_code == 429:
                wait = int(
                    response.headers.get("Retry-After", "30")
                )
                print(
                    f"Rate limited. Waiting {wait}s",
                    flush=True
                )
                time.sleep(max(wait, 1))
                continue

            if response.status_code == 404:
                return None

            response.raise_for_status()

            payload = response.json()

            expected = (
                payload.get("data", {})
                .get("overview", {})
                .get("expected_goals", {})
            )

            first_half = expected.get("first_half") or {}

            home = first_half.get("home")
            away = first_half.get("away")

            if home is None or away is None:
                return None

            return {
                "home_ht_xg": float(home),
                "away_ht_xg": float(away)
            }

        except (
            requests.RequestException,
            ValueError,
            TypeError
        ) as error:

            print(
                f"Attempt {attempt + 1} failed: {error}",
                flush=True
            )

            if attempt == 3:
                raise

            time.sleep(3)

    return None


def main():

    print(
        "PRO STAR LIZARD - HT xG RECOVERY",
        flush=True
    )

    matches = get_missing_matches()

    print(
        f"Matches selected: {len(matches)}",
        flush=True
    )

    recovered = 0
    unavailable = 0
    failed = 0

    for index, match in enumerate(matches, 1):

        match_id = match["match_id"]

        print(
            f"\n[{index}/{len(matches)}] "
            f"{match['match_date']} "
            f"{match['home_team']} v "
            f"{match['away_team']}",
            flush=True
        )

        try:

            values = get_ht_xg(match_id)

            if values is None:
                unavailable += 1
                print(
                    "HT xG unavailable",
                    flush=True
                )
                continue

            # Never overwrite an existing HT value.
            updates = {}

            if match["home_ht_xg"] is None:
                updates["home_ht_xg"] = (
                    values["home_ht_xg"]
                )

            if match["away_ht_xg"] is None:
                updates["away_ht_xg"] = (
                    values["away_ht_xg"]
                )

            if not updates:
                continue

            # Recheck missing fields before writing,
            # so existing values are preserved.
            query = (
                DB.table("historical_xg")
                .update(updates)
                .eq("match_id", match_id)
            )

            for field in updates:
                query = query.is_(field, "null")

            result = query.execute()

            if result.data:
                recovered += 1
                print(
                    "RECOVERED:",
                    values,
                    flush=True
                )
            else:
                print(
                    "Skipped: record already updated",
                    flush=True
                )

        except Exception as error:
            failed += 1
            print(
                f"ERROR: {error}",
                flush=True
            )

        finally:
            time.sleep(REQUEST_INTERVAL)

    print("\n" + "=" * 50)
    print("RECOVERY SUMMARY")
    print(f"Matches checked: {len(matches)}")
    print(f"Recovered: {recovered}")
    print(f"HT xG unavailable: {unavailable}")
    print(f"Errors: {failed}")
    print("=" * 50)


if __name__ == "__main__":
    main()
