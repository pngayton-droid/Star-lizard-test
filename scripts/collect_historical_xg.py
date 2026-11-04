
import os
import time
import requests
from datetime import date
from supabase import create_client

API_KEY = os.environ["STATS_API_KEY"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SECRET_KEY"]

BASE_URL = "https://api.thestatsapi.com/api"
db = create_client(SUPABASE_URL, SUPABASE_KEY)

# Known IDs are retained for our original five leagues.
# Additional competitions are resolved using the API.
LEAGUES = {
    "Premier League": {
        "id": "comp_3039",
        "search": "Premier League",
        "country": "England",
    },
    "Championship": {
        "id": "comp_8321",
        "search": "Championship",
        "country": "England",
    },
    "La Liga": {
        "id": None,
        "search": "La Liga",
        "country": "Spain",
    },
    "Serie A": {
        "id": None,
        "search": "Serie A",
        "country": "Italy",
    },
    "Bundesliga": {
        "id": "comp_4643",
        "search": "Bundesliga",
        "country": "Germany",
    },
    "Ligue 1": {
        "id": "comp_0256",
        "search": "Ligue 1",
        "country": "France",
    },
    "Eredivisie": {
        "id": None,
        "search": "Eredivisie",
        "country": "Netherlands",
    },
    "Primeira Liga": {
        "id": None,
        "search": "Primeira Liga",
        "country": "Portugal",
    },
    "Belgian Pro League": {
        "id": "comp_8531",
        "search": "Pro League",
        "country": "Belgium",
    },
    "Scottish Premiership": {
        "id": None,
        "search": "Premiership",
        "country": "Scotland",
    },
}

MAX_MATCHES_PER_LEAGUE = 5
MAX_DETAIL_REQUESTS = 50
MAX_PAGES_PER_LEAGUE = 15
PAGE_SIZE = 20

START_DATE = "2025-08-01"
END_DATE = date.today().isoformat()

session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
})

last_request = 0.0


def api_get(path, params=None):
    global last_request

    for attempt in range(5):
        elapsed = time.monotonic() - last_request
        if elapsed < 3:
            time.sleep(3 - elapsed)

        last_request = time.monotonic()

        try:
            response = session.get(
                BASE_URL + path,
                params=params,
                timeout=30,
            )

            if response.status_code == 429:
                try:
                    code = (
                        response.json()
                        .get("error", {})
                        .get("code")
                    )
                except ValueError:
                    code = None

                if code == "USAGE_LIMIT_EXCEEDED":
                    raise RuntimeError(
                        "Monthly API quota exhausted"
                    )

                wait = response.headers.get(
                    "Retry-After", "60"
                )
                try:
                    wait = max(60, float(wait))
                except ValueError:
                    wait = 60

                wait = min(wait, 180)
                print(f"Rate limited: waiting {wait}s")
                time.sleep(wait)
                continue

            response.raise_for_status()
            return response.json()

        except requests.RequestException as exc:
            if attempt == 4:
                raise
            print(f"Request failed: {exc}")
            time.sleep(15)

    raise RuntimeError("API retries exhausted")


def unwrap_list(payload):
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for key in ("data", "results", "matches", "competitions"):
        value = payload.get(key)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):
            for nested in (
                "data", "results", "matches", "competitions"
            ):
                if isinstance(value.get(nested), list):
                    return value[nested]

    return []


def normalise(value):
    return "".join(
        c for c in str(value or "").casefold()
        if c.isalnum()
    )


def country_matches(item, country):
    value = item.get("country", "")
    if isinstance(value, dict):
        value = (
            value.get("name")
            or value.get("code")
            or ""
        )

    names = {
        "England": {"england", "gbeng"},
        "Scotland": {"scotland", "gbsct"},
        "Spain": {"spain", "es"},
        "Italy": {"italy", "it"},
        "Germany": {"germany", "de"},
        "France": {"france", "fr"},
        "Netherlands": {"netherlands", "nl"},
        "Portugal": {"portugal", "pt"},
        "Belgium": {"belgium", "be"},
    }

    candidates = {
        normalise(value),
        normalise(item.get("country_code")),
        normalise(item.get("subdivision_code")),
    }

    return bool(candidates & names[country])


def resolve_competition(league, config):
    if config["id"]:
        print(
            f"{league}: using existing ID "
            f"{config['id']}"
        )
        return config["id"]

    payload = api_get(
        "/football/competitions",
        {
            "search": config["search"],
            "per_page": 100,
        },
    )

    items = unwrap_list(payload)

    matches = []
    for item in items:
        if not isinstance(item, dict):
            continue

        if not country_matches(
            item, config["country"]
        ):
            continue

        name = normalise(item.get("name"))
        target = normalise(config["search"])

        if (
            target in name
            or name in target
            or (
                league == "La Liga"
                and name in ("laliga", "primeradivision")
            )
            or (
                league == "Primeira Liga"
                and name in (
                    "ligaportugal",
                    "ligaportugalbetclic",
                )
            )
            or (
                league == "Scottish Premiership"
                and "premiership" in name
            )
        ):
            matches.append(item)

    if len(matches) != 1:
        print(
            f"WARNING: {league} has "
            f"{len(matches)} matching competitions."
        )
        print(
            "Candidates:",
            [
                (
                    x.get("id"),
                    x.get("name"),
                    x.get("country"),
                )
                for x in items
                if isinstance(x, dict)
            ],
        )
        return None

    competition_id = matches[0].get("id")
    print(
        f"Resolved {league}: {competition_id}"
    )
    return competition_id


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

        for row in rows:
            if row.get("match_id"):
                ids.add(str(row["match_id"]))

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
    return unwrap_list(payload)


def get_xg(match_id):
    payload = api_get(
        f"/football/matches/{match_id}/stats"
    )

    data = payload.get("data") or {}
    overview = data.get("overview") or {}
    expected = (
        overview.get("expected_goals") or {}
    )
    values = expected.get("all") or {}

    home = values.get("home")
    away = values.get("away")

    if home is None or away is None:
        return None

    return float(home), float(away)


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

    total_saved = 0
    detail_requests = 0

    for league, config in LEAGUES.items():
        print(f"\n=== {league} ===")

        if detail_requests >= MAX_DETAIL_REQUESTS:
            print("Global request limit reached.")
            break

        competition_id = resolve_competition(
            league, config
        )

        if not competition_id:
            print(f"Skipping unresolved {league}")
            continue

        saved = 0
        checked = 0

        for page in range(
            1, MAX_PAGES_PER_LEAGUE + 1
        ):
            if saved >= MAX_MATCHES_PER_LEAGUE:
                break

            if detail_requests >= MAX_DETAIL_REQUESTS:
                break

            fixtures = fixture_list(
                competition_id, page
            )

            print(
                f"{league} page {page}: "
                f"{len(fixtures)} fixtures"
            )

            if not fixtures:
                break

            for match in fixtures:
                if saved >= MAX_MATCHES_PER_LEAGUE:
                    break

                if detail_requests >= MAX_DETAIL_REQUESTS:
                    break

                if not isinstance(match, dict):
                    continue

                match_id = (
                    match.get("id")
                    or match.get("match_id")
                )

                if not match_id:
                    continue

                match_id = str(match_id)

                if match_id in known:
                    continue

                if match.get("xg_available") is False:
                    continue

                actual_competition = (
                    match.get("competition_id")
                )

                if (
                    actual_competition is not None
                    and actual_competition != competition_id
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

                if not home or not away or not match_date:
                    continue

                checked += 1
                detail_requests += 1

                try:
                    xg = get_xg(match_id)

                    if xg is None:
                        print(
                            f"No xG: {match_id}"
                        )
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
                        row,
                        on_conflict="match_id",
                    ).execute()

                    known.add(match_id)
                    saved += 1
                    total_saved += 1

                    print(
                        f"Saved {league}: "
                        f"{home} v {away}"
                    )

                except Exception as exc:
                    print(
                        f"Match {match_id} failed: {exc}"
                    )

        print(
            f"{league}: saved {saved}, "
            f"detail requests {checked}"
        )

    print("\n=== FINAL SUMMARY ===")
    print(f"New matches saved: {total_saved}")
    print(f"Detail requests: {detail_requests}")
    print(f"Database total: {len(known)}")


if __name__ == "__main__":
    main()
