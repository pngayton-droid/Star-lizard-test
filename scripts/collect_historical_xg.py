
import os
import time
import requests
from datetime import date, timedelta
from supabase import create_client

API_KEY = os.environ["STATS_API_KEY"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SECRET_KEY"]

BASE_URL = "https://api.thestatsapi.com/api"
db = create_client(SUPABASE_URL, SUPABASE_KEY)

LEAGUES = {
    "Championship": "comp_8321",
    "Premier League": "comp_3039",
    "Bundesliga": "comp_4643",
    "Ligue 1": "comp_0256",
    "Belgian Pro League": "comp_8531",
}

# Safety limits for the first test
MAX_DETAIL_REQUESTS = 20
MAX_PAGES_PER_LEAGUE = 5
PAGE_SIZE = 20
START_DATE = "2025-08-01"
END_DATE = date.today().isoformat()

session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
})




_last_api_request = 0.0

def api_get(path, params=None):
    global _last_api_request

    for attempt in range(5):
        elapsed = time.monotonic() - _last_api_request
        if elapsed < 3:
            time.sleep(3 - elapsed)

        _last_api_request = time.monotonic()

        try:
            response = session.get(
                BASE_URL + path,
                params=params,
                timeout=30,
            )

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "60")
                try:
                    wait = max(60, float(retry_after))
                except ValueError:
                    wait = 60

                wait = min(wait, 180)
                print(f"Rate limited. Waiting {wait:.0f} seconds.")
                time.sleep(wait)
                continue

            response.raise_for_status()
            return response.json()

        except requests.RequestException as exc:
            if attempt == 4:
                raise
            print(f"API error: {exc}. Retrying in 15 seconds.")
            time.sleep(15)

    raise RuntimeError("API rate limit retries exhausted")


def existing_ids():
    ids = set()
    offset = 0

    while True:
        result = (
            db.table("historical_xg")
            .select("match_id")
            .range(offset, offset + 999)
            .execute()
        )
        rows = result.data or []
        ids.update(
            str(row["match_id"])
            for row in rows
            if row.get("match_id")
        )
        if len(rows) < 1000:
            break
        offset += 1000

    return ids


def fixture_list(competition_id, page):
    payload = api_get(
        "/football/matches",
        {
            "competition_id": competition_id,
            "status": "finished",
            "date_from": START_DATE,
            "date_to": END_DATE,
            "per_page": PAGE_SIZE,
            "page": page,
            "sort": "-utc_date",
        },
    )

    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        raise ValueError("Unexpected fixture response")

    for key in ("data", "matches", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for nested in ("data", "matches", "results"):
                if isinstance(value.get(nested), list):
                    return value[nested]

    raise ValueError("Could not locate fixture list")


def get_xg(match_id):
    payload = api_get(
        f"/football/matches/{match_id}/stats"
    )

    # Match the nested expected_goals structure
    # used by the existing collector.
    candidates = [payload]
    if isinstance(payload, dict):
        candidates.extend(
            payload.get(key)
            for key in ("data", "stats", "statistics")
        )

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue

        stats = candidate.get("stats", candidate)
        if not isinstance(stats, dict):
            continue

        expected = stats.get("expected_goals")
        if not isinstance(expected, dict):
            continue

        values = expected.get("all")
        if not isinstance(values, dict):
            continue

        home = values.get("home")
        away = values.get("away")

        if home is not None and away is not None:
            return float(home), float(away)

    return None


def team_name(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return (
            value.get("name")
            or value.get("short_name")
            or value.get("display_name")
        )
    return None


def main():
    known = existing_ids()
    print(f"Existing database IDs: {len(known)}")

    requests_used = 0
    saved = 0

    for league, competition_id in LEAGUES.items():
        if requests_used >= MAX_DETAIL_REQUESTS:
            break

        for page in range(1, MAX_PAGES_PER_LEAGUE + 1):
            fixtures = fixture_list(competition_id, page)
            print(f"{league}, page {page}: {len(fixtures)} fixtures")

            for match in fixtures:
                if requests_used >= MAX_DETAIL_REQUESTS:
                    break

                if not isinstance(match, dict):
                    continue

                # Never mix leagues if the API ignores
                # its competition filter.
                competition = match.get("competition_id")
                if competition != competition_id:
                    continue

                match_id = match.get("id") or match.get("match_id")
                if not match_id:
                    continue

                match_id = str(match_id)
                if match_id in known:
                    continue

                home = team_name(
                    match.get("home_team") or match.get("home")
                )
                away = team_name(
                    match.get("away_team") or match.get("away")
                )
                match_date = (
                    match.get("utc_date")
                    or match.get("date")
                    or match.get("match_date")
                )

                if not home or not away or not match_date:
                    print(f"Skipping incomplete fixture {match_id}")
                    continue

                requests_used += 1
                try:
                    xg = get_xg(match_id)
                    if xg is None:
                        print(f"No xG: {match_id}")
                        continue

                    row = {
                        "match_id": match_id,
                        "match_date": str(match_date)[:10],
                        "home_team": home,
                        "away_team": away,
                        "home_xg": xg[0],
                        "away_xg": xg[1],
                    }

                    db.table("historical_xg").upsert(
                        row, on_conflict="match_id"
                    ).execute()

                    known.add(match_id)
                    saved += 1
                    print(f"Saved {league}: {home} v {away}")

                except Exception as exc:
                    print(f"Match {match_id} failed: {exc}")

                time.sleep(0.25)

    print(
        f"Finished. Detail requests: {requests_used}. "
        f"New matches saved: {saved}."
    )


if __name__ == "__main__":
    main()
