
import os
import time
from collections import Counter

import requests
from supabase import create_client

# TEAM STARLIZARD - EVENT COVERAGE INSPECTION
# READ ONLY: No database writes.
# Five matches, two endpoints each.

BASE = "https://api.thestatsapi.com/api"
API_KEY = os.environ["STATS_API_KEY"]

db = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SECRET_KEY"],
)

headers = {"Authorization": f"Bearer {API_KEY}"}

result = (
    db.table("historical_xg")
    .select("match_id,match_date,home_team,away_team")
    .like("match_id", "mt_%")
    .not_.is_("home_goals", "null")
    .order("match_date", desc=True)
    .limit(1000)
    .execute()
)

matches = result.data or []
positions = [0, 200, 400, 600, 800]
samples = [matches[i] for i in positions if i < len(matches)]


def fetch(match_id, endpoint):
    url = f"{BASE}/football/matches/{match_id}/{endpoint}"

    try:
        response = requests.get(
            url, headers=headers, timeout=30
        )
        print(
            f"{endpoint.upper()} HTTP STATUS: "
            f"{response.status_code}",
            flush=True,
        )

        if response.status_code != 200:
            print(
                "ERROR:", response.text[:300], flush=True
            )
            return None

        return response.json()

    except (requests.RequestException, ValueError) as exc:
        print("REQUEST ERROR:", str(exc), flush=True)
        return None


def preview(value, limit=5):
    if isinstance(value, dict):
        return list(value.keys())[:limit]
    if isinstance(value, list):
        return f"list with {len(value)} items"
    return str(value)[:100]


def inspect_stats(payload):
    if not isinstance(payload, dict):
        return

    data = payload.get("data", payload)
    if not isinstance(data, dict):
        print("Unexpected stats structure")
        return

    print("\nSTATS SECTIONS:")
    print(list(data.keys()))

    overview = data.get("overview", {})
    if isinstance(overview, dict):
        print("OVERVIEW STAT NAMES:")
        print(list(overview.keys()))

    keywords = (
        "corner", "card", "yellow", "red",
        "goal", "shot", "foul",
    )

    def scan(obj, path="", depth=0):
        if depth > 7:
            return

        if isinstance(obj, dict):
            for key, value in obj.items():
                location = f"{path}.{key}" if path else key
                if any(word in str(key).lower()
                       for word in keywords):
                    print(
                        "STAT FIELD:", location,
                        "VALUE:", str(value)[:350],
                    )
                if isinstance(value, (dict, list)):
                    scan(value, location, depth + 1)

        elif isinstance(obj, list):
            for index, value in enumerate(obj[:3]):
                scan(value, f"{path}[{index}]", depth + 1)

    print("\nCORNERS / CARDS / GOALS FIELDS:")
    scan(data)


def inspect_timeline(payload):
    if not isinstance(payload, dict):
        return

    data = payload.get("data", payload)

    if not isinstance(data, dict):
        print("Unexpected timeline structure")
        return

    print("\nTIMELINE KEYS:", list(data.keys()))
    print("COVERAGE:", data.get("coverage", "unknown"))

    events = data.get("events", [])
    if not isinstance(events, list):
        print("Events is not a list")
        return

    print("TOTAL EVENTS:", len(events))

    types = Counter(
        str(event.get("type", "unknown"))
        for event in events
        if isinstance(event, dict)
    )

    print("\nALL EVENT TYPES:")
    for name, count in sorted(types.items()):
        print(f"  {name}: {count}")

    keywords = (
        "goal", "corner", "card", "yellow",
        "red", "booking", "penalty",
    )

    print("\nGOALS / CORNERS / CARDS EVENTS:")

    found = 0

    for event in events:
        if not isinstance(event, dict):
            continue

        event_type = str(event.get("type", ""))
        event_text = str(event).lower()

        if any(word in event_text for word in keywords):
            found += 1
            minute = event.get("minute")
            extra = event.get("extra_time")
            period = event.get("period")

            team = event.get("team")
            if isinstance(team, dict):
                team = team.get("name", team.get("id"))

            print(
                f"  minute={minute} extra={extra}"
                f" period={period}"
                f" type={event_type} team={team}"
            )
            print("  RAW:", str(event)[:500])

    print("MATCHING EVENTS:", found)

    if events:
        print("\nFIRST EVENT FIELD NAMES:")
        first = events[0]
        if isinstance(first, dict):
            print(list(first.keys()))


print("\nTEAM STARLIZARD - EVENT REPORT")
print("Matches selected:", len(samples))

for index, match in enumerate(samples, 1):
    print("\n" + "=" * 65)
    print(f"MATCH {index}/{len(samples)}")
    print(match["match_date"])
    print(
        match["home_team"], "v", match["away_team"]
    )
    print("MATCH ID:", match["match_id"])
    print("=" * 65, flush=True)

    stats = fetch(match["match_id"], "stats")
    if stats is not None:
        inspect_stats(stats)

    time.sleep(1.2)

    timeline = fetch(match["match_id"], "timeline")
    if timeline is not None:
        inspect_timeline(timeline)

    time.sleep(1.2)

print("\nINSPECTION COMPLETE", flush=True)
