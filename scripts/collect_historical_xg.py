
"""PRO STAR LIZARD — RESUMABLE HISTORICAL xG COLLECTOR"""

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

LEAGUES = {
    "Premier League": "comp_3039",
    "Championship": "comp_8321",
    "La Liga": "comp_8814",
    "Serie A": "comp_5840",
    "Bundesliga": "comp_4643",
    "Ligue 1": "comp_0256",
    "Eredivisie": "comp_3809",
    "Primeira Liga": "comp_8385",
    "Belgian Pro League": "comp_8531",
    "Scottish Premiership": "comp_6387",
}

FIRST_SEASON = 2016
LAST_SEASON = 2025

MAX_DETAIL_REQUESTS = 500
MAX_TOTAL_API_REQUESTS = 900
PAGE_SIZE = 20
MIN_REQUEST_INTERVAL = 1.0

COLLECTOR_NAME = "historical_xg"

session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {API_KEY}"
})

api_calls = 0
last_request = 0.0
monthly_remaining = "unknown"


def api_get(path, params=None):
    global api_calls, last_request, monthly_remaining

    for attempt in range(4):
        if api_calls >= MAX_TOTAL_API_REQUESTS:
            return None

        wait = MIN_REQUEST_INTERVAL - (
            time.monotonic() - last_request
        )

        if wait > 0:
            time.sleep(wait)

        last_request = time.monotonic()

        response = session.get(
            BASE + path,
            params=params,
            timeout=30,
        )

        api_calls += 1

        monthly_remaining = response.headers.get(
            "X-Monthly-Quota-Remaining",
            monthly_remaining,
        )

        if response.status_code == 429:
            delay = int(
                response.headers.get("Retry-After", "60")
            )
            print(
                f"Rate limited: waiting {delay}s",
                flush=True,
            )
            time.sleep(max(delay, 1))
            continue

        if response.status_code == 400:
            try:
                error = response.json().get("error", {})
            except ValueError:
                error = {}

            if error.get("code") == "PAGE_OUT_OF_RANGE":
                return {"data": []}

        response.raise_for_status()
        return response.json()

    raise RuntimeError(
        "API retries exhausted. Progress is preserved."
    )


def load_existing():
    existing = {}
    offset = 0

    while True:
        result = (
            DB.table("historical_xg")
            .select("match_id,home_ht_xg,away_ht_xg")
            .range(offset, offset + 999)
            .execute()
        )

        rows = result.data or []

        for row in rows:
            existing[str(row["match_id"])] = (
                row.get("home_ht_xg") is not None
                and row.get("away_ht_xg") is not None
            )

        if len(rows) < 1000:
            break

        offset += 1000

    return existing


def load_progress():
    result = (
        DB.table("collector_progress")
        .select("*")
        .eq("collector_name", COLLECTOR_NAME)
        .limit(1)
        .execute()
    )

    if result.data:
        row = result.data[0]
        return (
            int(row["season"]),
            int(row["league_index"]),
            int(row["page"]),
            int(row["match_index"]),
        )

    return (LAST_SEASON, 0, 1, 0)


def save_progress(season, league_index, page, match_index):
    DB.table("collector_progress").upsert(
        {
            "collector_name": COLLECTOR_NAME,
            "season": season,
            "league_index": league_index,
            "page": page,
            "match_index": match_index,
            
        },
        on_conflict="collector_name",
    ).execute()


def get_match_xg(match_id):
    payload = api_get(
        f"/football/matches/{match_id}/stats"
    )

    if payload is None:
        return None

    data = payload.get("data") or {}
    overview = data.get("overview") or {}
    expected = overview.get("expected_goals") or {}

    full = expected.get("all") or {}
    half = expected.get("first_half") or {}

    values = (
        full.get("home"),
        full.get("away"),
        half.get("home"),
        half.get("away"),
    )

    if any(value is None for value in values):
        return None

    return values


def save_match(match, values):
    home = match.get("home_team") or {}
    away = match.get("away_team") or {}

    match_id = str(
        match.get("id") or match.get("match_id")
    )

    row = {
        "match_id": match_id,
        "match_date": str(
            match.get("utc_date", "")
        )[:10],
        "home_team": home.get("name", ""),
        "away_team": away.get("name", ""),
        "home_xg": values[0],
        "away_xg": values[1],
        "home_ht_xg": values[2],
        "away_ht_xg": values[3],
    }

    DB.table("historical_xg").upsert(
        row,
        on_conflict="match_id",
    ).execute()


def next_league_position(season, league_index):
    league_index += 1

    if league_index >= len(LEAGUES):
        return (season - 1, 0, 1, 0)

    return (season, league_index, 1, 0)


def main():
    existing = load_existing()

    season, league_index, page, match_index = load_progress()

    print(
        "PRO STAR LIZARD RESUMABLE HISTORICAL COLLECTOR",
        flush=True,
    )
    print(
        f"Existing matches: {len(existing)}",
        flush=True,
    )
    print(
        f"RESUMING: season={season}, "
        f"league={league_index}, "
        f"page={page}, match={match_index}",
        flush=True,
    )

    new = 0
    updated = 0
    missing = 0
    skipped = 0
    details = 0

    leagues = list(LEAGUES.items())

    while season >= FIRST_SEASON:
        if (
            details >= MAX_DETAIL_REQUESTS
            or api_calls >= MAX_TOTAL_API_REQUESTS
        ):
            break

        league_name, competition_id = leagues[league_index]

        print(
            f"\n=== {league_name} "
            f"{season}/{season + 1}, page {page} ===",
            flush=True,
        )

        start = f"{season}-08-01"
        end = f"{season + 1}-07-31"

        payload = api_get(
            "/football/matches",
            {
                "competition_id": competition_id,
                "status": "finished",
                "date_from": start,
                "date_to": end,
                "per_page": PAGE_SIZE,
                "page": page,
                "sort": "-utc_date",
            },
        )

        if payload is None:
            break

        matches = payload.get("data") or []

        if not isinstance(matches, list):
            raise RuntimeError(
                "Unexpected fixtures response. "
                "Progress preserved."
            )

        if not matches:
            season, league_index, page, match_index = (
                next_league_position(season, league_index)
            )

            save_progress(
                season, league_index, page, match_index
            )
            continue

        print(
            f"Page {page}: {len(matches)} fixtures",
            flush=True,
        )

        while match_index < len(matches):
            if (
                details >= MAX_DETAIL_REQUESTS
                or api_calls >= MAX_TOTAL_API_REQUESTS
            ):
                break

            match = matches[match_index]

            match_id = str(
                match.get("id")
                or match.get("match_id")
                or ""
            )

            if not match_id:
                match_index += 1
                save_progress(
                    season, league_index, page, match_index
                )
                continue

            if existing.get(match_id) is True:
                skipped += 1

            elif match.get("xg_available") is False:
                missing += 1

            else:
                # Reserve a request for the detail endpoint.
                if api_calls >= MAX_TOTAL_API_REQUESTS - 1:
                    break

                details += 1

                try:
                    values = get_match_xg(match_id)

                except requests.HTTPError as exc:
                    if (
                        exc.response is not None
                        and exc.response.status_code == 404
                    ):
                        values = None
                    else:
                        raise

                if values is None:
                    missing += 1
                else:
                    save_match(match, values)

                    if match_id in existing:
                        updated += 1
                    else:
                        new += 1

                    existing[match_id] = True

            # Advance only after this match is handled.
            match_index += 1

            save_progress(
                season, league_index, page, match_index
            )

        if (
            details >= MAX_DETAIL_REQUESTS
            or api_calls >= MAX_TOTAL_API_REQUESTS - 1
        ):
            break

        if match_index >= len(matches):
            page += 1
            match_index = 0

            save_progress(
                season, league_index, page, match_index
            )

    print("\n=== FINAL SUMMARY ===", flush=True)
    print(f"New matches: {new}", flush=True)
    print(f"Existing matches updated: {updated}", flush=True)
    print(f"HT xG saved/updated: {new + updated}", flush=True)
    print(f"Without usable xG: {missing}", flush=True)
    print(f"Already complete skipped: {skipped}", flush=True)
    print(f"Detailed requests: {details}", flush=True)
    print(f"Total API requests: {api_calls}", flush=True)
    print(
        f"Monthly requests remaining: {monthly_remaining}",
        flush=True,
    )
    print(f"Database total: {len(existing)}", flush=True)
    print(
        f"NEXT POSITION: season={season}, "
        f"league={league_index}, "
        f"page={page}, match={match_index}",
        flush=True,
    )

    if season < FIRST_SEASON:
        print(
            "HISTORICAL COLLECTION COMPLETE",
            flush=True,
        )


if __name__ == "__main__":
    main()
