
import os
import time
import requests

from supabase import create_client

# ==========================================
# PRO STAR LIZARD
# HISTORICAL xG COLLECTOR
# STARTER PLAN EDITION
# ==========================================

API_KEY = os.environ["STATS_API_KEY"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SECRET_KEY"]

BASE_URL = "https://api.thestatsapi.com/api"

db = create_client(
    SUPABASE_URL,
    SUPABASE_KEY,
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

# ==========================================
# HISTORICAL TEST SETTINGS
# ==========================================



START_DATE = "2016-08-01"
END_DATE = "2017-07-31"

# Maximum detailed match requests.
MAX_DETAIL_REQUESTS = 500

# Spread the test across ten leagues.
MAX_REQUESTS_PER_LEAGUE = 50

PAGE_SIZE = 20
MAX_PAGES_PER_LEAGUE = 100

# Conservative paid-plan pacing:
# approximately 60 requests per minute.
MIN_REQUEST_INTERVAL = 1.0

# Includes fixture searches and retries.
MAX_TOTAL_API_REQUESTS = 1000

session = requests.Session()

session.headers.update({
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
})

last_request = 0.0
api_requests = 0
detail_requests = 0

rate_limit = None
monthly_remaining = None

printed_xg_schema = False


# ==========================================
# API
# ==========================================

class StopCollection(Exception):
    pass


def api_get(path, params=None):
    global last_request
    global api_requests
    global rate_limit
    global monthly_remaining

    for attempt in range(4):

        if api_requests >= MAX_TOTAL_API_REQUESTS:
            raise StopCollection(
                "Run API request budget reached"
            )

        elapsed = time.monotonic() - last_request

        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(
                MIN_REQUEST_INTERVAL - elapsed
            )

        last_request = time.monotonic()
        api_requests += 1

        try:
            response = session.get(
                BASE_URL + path,
                params=params,
                timeout=30,
            )

        except requests.RequestException as exc:
            print(
                f"Network error: {exc}",
                flush=True,
            )

            if attempt == 3:
                raise StopCollection(
                    "Repeated network failures"
                )

            time.sleep(10)
            continue

        headers = response.headers

        rate_limit = headers.get(
            "X-RateLimit-Limit",
            rate_limit,
        )

        monthly_remaining = headers.get(
            "X-Monthly-Quota-Remaining",
            monthly_remaining,
        )

        if response.status_code == 429:

            try:
                error = response.json().get(
                    "error", {}
                )
                code = error.get("code")
            except ValueError:
                code = None

            if code == "USAGE_LIMIT_EXCEEDED":
                raise StopCollection(
                    "Monthly API quota exhausted"
                )

            try:
                wait = float(
                    headers.get(
                        "Retry-After", "60"
                    )
                )
            except ValueError:
                wait = 60

            wait = min(
                max(wait, 5),
                180,
            )

            print(
                f"Rate limit reached. "
                f"Waiting {wait}s",
                flush=True,
            )

            time.sleep(wait)
            continue

        if response.status_code in (401, 403):
            raise StopCollection(
                f"API access denied: "
                f"HTTP {response.status_code}"
            )

        if response.status_code >= 500:
            if attempt == 3:
                raise StopCollection(
                    "Repeated API server errors"
                )

            time.sleep(10)
            continue

    
        if response.status_code == 400:
            print(
                f"API rejected request: {response.url}",
                flush=True,
            )
            print(
                f"API explanation: {response.text[:500]}",
                flush=True,
            )
            return {}

        response.raise_for_status()
    
        return response.json()

    raise StopCollection(
        "API retries exhausted"
    )


# ==========================================
# RESPONSE HELPERS
# ==========================================

def unwrap_list(payload):

    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for key in (
        "data",
        "results",
        "matches",
    ):

        value = payload.get(key)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):

            for nested in (
                "data",
                "results",
                "matches",
            ):

                result = value.get(nested)

                if isinstance(result, list):
                    return result

    return []


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


def read_pair(value):

    if not isinstance(value, dict):
        return None

    home = value.get("home")
    away = value.get("away")

    if home is None or away is None:
        return None

    try:
        return (
            float(home),
            float(away),
        )

    except (ValueError, TypeError):
        return None


# ==========================================
# EXISTING DATABASE
# ==========================================

def load_existing():

    records = {}
    offset = 0

    while True:

        response = (
            db.table("historical_xg")
            .select(
                "match_id,home_ht_xg,away_ht_xg"
            )
            .range(
                offset,
                offset + 999,
            )
            .execute()
        )

        rows = response.data or []

        for row in rows:

            match_id = row.get("match_id")

            if match_id is not None:
                records[str(match_id)] = row

        if len(rows) < 1000:
            break

        offset += 1000

    return records


# ==========================================
# FIXTURE SEARCH
# ==========================================

def get_fixtures(competition_id, page):

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

    
    if not payload:
        return []

    return unwrap_list(payload)



# ==========================================
# MATCH xG
# ==========================================

def get_match_xg(match_id):

    global printed_xg_schema

    payload = api_get(
        f"/football/matches/{match_id}/stats"
    )

    if not isinstance(payload, dict):
        return None

    data = payload.get("data") or {}
    overview = data.get("overview") or {}

    expected = (
        overview.get("expected_goals") or {}
    )

    if not isinstance(expected, dict):
        return None

    # Show available xG fields once,
    # so we can verify the API structure.
    if not printed_xg_schema:

        print(
            "XG RESPONSE KEYS:",
            list(expected.keys()),
            flush=True,
        )

        printed_xg_schema = True

    full_time = read_pair(
        expected.get("all")
    )

    if full_time is None:
        return None

    # Only use genuine first-half xG.
    # Never estimate it from full-time xG.
    half_time = read_pair(
        expected.get("first_half")
    )

    result = {
        "home_xg": full_time[0],
        "away_xg": full_time[1],
        "home_ht_xg": None,
        "away_ht_xg": None,
    }

    if half_time is not None:

        result["home_ht_xg"] = (
            half_time[0]
        )

        result["away_ht_xg"] = (
            half_time[1]
        )

    return result


# ==========================================
# MAIN COLLECTOR
# ==========================================

def main():

    global detail_requests

    existing = load_existing()

    new_matches = 0
    updated_matches = 0
    ht_available = 0
    ht_missing = 0

    print(
        "PRO STAR LIZARD HISTORICAL TEST",
        flush=True,
    )

    print(
        f"Existing matches: {len(existing)}",
        flush=True,
    )

    print(
        f"Historical period: "
        f"{START_DATE} to {END_DATE}",
        flush=True,
    )

    print(
        f"Maximum detail requests: "
        f"{MAX_DETAIL_REQUESTS}",
        flush=True,
    )

    try:

        for league, competition_id in LEAGUES.items():

            if detail_requests >= MAX_DETAIL_REQUESTS:
                break

            print(
                f"\n=== {league} ===",
                flush=True,
            )

            league_requests = 0
            league_new = 0
            league_updated = 0

            for page in range(
                1,
                MAX_PAGES_PER_LEAGUE + 1,
            ):

                if (
                    league_requests
                    >= MAX_REQUESTS_PER_LEAGUE
                ):
                    break

                if (
                    detail_requests
                    >= MAX_DETAIL_REQUESTS
                ):
                    break

                fixtures = get_fixtures(
                    competition_id,
                    page,
                )

                print(
                    f"{league}, page {page}: "
                    f"{len(fixtures)} fixtures",
                    flush=True,
                )

                if not fixtures:
                    break

                for match in fixtures:

                    if (
                        league_requests
                        >= MAX_REQUESTS_PER_LEAGUE
                    ):
                        break

                    if (
                        detail_requests
                        >= MAX_DETAIL_REQUESTS
                    ):
                        break

                    if not isinstance(match, dict):
                        continue

                    actual_competition = (
                        match.get("competition_id")
                    )

                    if (
                        actual_competition is not None
                        and str(actual_competition)
                        != competition_id
                    ):
                        continue

                    match_id = (
                        match.get("id")
                        or match.get("match_id")
                    )

                    if match_id is None:
                        continue

                    match_id = str(match_id)

                    previous = existing.get(
                        match_id
                    )

                    # Skip matches already complete.
                    if previous is not None:

                        if (
                            previous.get("home_ht_xg")
                            is not None
                            and previous.get("away_ht_xg")
                            is not None
                        ):
                            continue

                    if (
                        match.get("xg_available")
                        is False
                    ):
                        continue

                    home = team_name(
                        match.get("home_team")
                        or match.get("home")
                    )

                    away = team_name(
                        match.get("away_team")
                        or match.get("away")
                    )

                    match_date = (
                        match.get("utc_date")
                        or match.get("date")
                        or match.get("match_date")
                    )

                    if not all((
                        home,
                        away,
                        match_date,
                    )):
                        continue

                    detail_requests += 1
                    league_requests += 1

                    try:

                        xg = get_match_xg(
                            match_id
                        )

                        if xg is None:

                            print(
                                f"No FT xG: "
                                f"{match_id}",
                                flush=True,
                            )

                            continue

                        has_ht = (
                            xg["home_ht_xg"]
                            is not None
                            and xg["away_ht_xg"]
                            is not None
                        )

                        if has_ht:
                            ht_available += 1
                        else:
                            ht_missing += 1

                        if previous is not None:

                            updates = {
                                "home_xg": (
                                    xg["home_xg"]
                                ),
                                "away_xg": (
                                    xg["away_xg"]
                                ),
                            }

                            if has_ht:
                                updates.update({
                                    "home_ht_xg": (
                                        xg["home_ht_xg"]
                                    ),
                                    "away_ht_xg": (
                                        xg["away_ht_xg"]
                                    ),
                                })

                            (
                                db.table("historical_xg")
                                .update(updates)
                                .eq(
                                    "match_id",
                                    match_id,
                                )
                                .execute()
                            )

                            updated_matches += 1
                            league_updated += 1

                            print(
                                f"UPDATED: "
                                f"{home} v {away} "
                                f"| HT xG: {has_ht}",
                                flush=True,
                            )

                        else:

                            row = {
                                "match_id": match_id,
                                "match_date": (
                                    str(match_date)[:10]
                                ),
                                "home_team": home,
                                "away_team": away,
                                **xg,
                            }

                            (
                                db.table("historical_xg")
                                .upsert(
                                    row,
                                    on_conflict="match_id",
                                )
                                .execute()
                            )

                            new_matches += 1
                            league_new += 1

                            print(
                                f"SAVED: "
                                f"{home} v {away} "
                                f"| HT xG: {has_ht}",
                                flush=True,
                            )

                        existing[match_id] = {
                            "match_id": match_id,
                            "home_ht_xg": (
                                xg["home_ht_xg"]
                                if has_ht
                                else (
                                    previous or {}
                                ).get("home_ht_xg")
                            ),
                            "away_ht_xg": (
                                xg["away_ht_xg"]
                                if has_ht
                                else (
                                    previous or {}
                                ).get("away_ht_xg")
                            ),
                        }

                    except StopCollection:
                        raise

                    except Exception as exc:

                        print(
                            f"Match failed: "
                            f"{match_id}: {exc}",
                            flush=True,
                        )

            print(
                f"{league}: "
                f"{league_new} new, "
                f"{league_updated} updated, "
                f"{league_requests} details",
                flush=True,
            )

    except StopCollection as exc:

        print(
            f"COLLECTION STOPPED: {exc}",
            flush=True,
        )

    print(
        "\n=== FINAL SUMMARY ===",
        flush=True,
    )

    print(
        f"New matches: {new_matches}",
        flush=True,
    )

    print(
        f"Existing matches updated: "
        f"{updated_matches}",
        flush=True,
    )

    print(
        f"HT xG available: "
        f"{ht_available}",
        flush=True,
    )

    print(
        f"HT xG missing: "
        f"{ht_missing}",
        flush=True,
    )

    print(
        f"Detailed requests: "
        f"{detail_requests}",
        flush=True,
    )

    print(
        f"Total API requests: "
        f"{api_requests}",
        flush=True,
    )

    print(
        f"Reported rate limit: "
        f"{rate_limit}",
        flush=True,
    )

    print(
        f"Monthly requests remaining: "
        f"{monthly_remaining}",
        flush=True,
    )

    print(
        f"Database total: "
        f"{len(existing)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
