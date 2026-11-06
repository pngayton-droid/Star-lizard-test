
import os
import time
from collections import Counter

import requests
from supabase import create_client

# STARLIZARD - HISTORICAL EVENT COLLECTOR
# TEST MODE: FIVE MATCHES ONLY
# Writes ONLY to historical_match_events.

API_BASE = "https://api.thestatsapi.com/api/football/matches"
API_KEY = os.environ["STATS_API_KEY"]

db = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SECRET_KEY"],
)

session = requests.Session()
session.headers.update({
    "Authorization": f"Bearer {API_KEY}"
})

TEST_LIMIT = 5


def fetch(match_id, endpoint):
    url = f"{API_BASE}/{match_id}/{endpoint}"

    for attempt in range(3):
        try:
            response = session.get(url, timeout=40)
            status = response.status_code

            if status == 429 or status >= 500:
                wait = 10 * (attempt + 1)
                print(
                    f"{endpoint}: HTTP {status}; "
                    f"waiting {wait}s",
                    flush=True,
                )
                time.sleep(wait)
                continue

            if status != 200:
                print(
                    f"{endpoint}: HTTP {status} "
                    f"{response.text[:200]}",
                    flush=True,
                )
                return None, status

            payload = response.json()
            data = payload.get("data")

            if not isinstance(data, dict):
                print(
                    f"{endpoint}: unexpected response",
                    flush=True,
                )
                return None, status

            return data, status

        except (requests.RequestException, ValueError) as exc:
            print(f"{endpoint}: {exc}", flush=True)
            if attempt < 2:
                time.sleep(10)

    return None, None


def stats_total(stats, field):
    if not isinstance(stats, dict):
        return None

    overview = stats.get("overview")
    if not isinstance(overview, dict):
        return None

    section = overview.get(field)
    if not isinstance(section, dict):
        return None

    full = section.get("all")
    if not isinstance(full, dict):
        return None

    home = full.get("home")
    away = full.get("away")

    if home is None or away is None:
        return None

    return int(home) + int(away)


def timeline_count(timeline, event_type):
    if not isinstance(timeline, dict):
        return None

    if timeline.get("coverage") != "full":
        return None

    events = timeline.get("events")
    if not isinstance(events, list):
        return None

    return sum(
        1 for event in events
        if isinstance(event, dict)
        and event.get("type") == event_type
    )


def compare(stats, timeline, stat_field, event_type):
    official = stats_total(stats, stat_field)
    events = timeline_count(timeline, event_type)

    if official is None or events is None:
        return None, official, events

    return official == events, official, events


def main():
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
    samples = [
        matches[i] for i in positions
        if i < len(matches)
    ][:TEST_LIMIT]

    print(
        f"STARLIZARD EVENT COLLECTOR: "
        f"{len(samples)} test matches",
        flush=True,
    )

    for number, match in enumerate(samples, 1):
        match_id = match["match_id"]

        print(
            f"\n{number}/{len(samples)} "
            f"{match['home_team']} v "
            f"{match['away_team']} "
            f"({match_id})",
            flush=True,
        )

        stats, stats_status = fetch(match_id, "stats")
        time.sleep(1.2)

        timeline, timeline_status = fetch(
            match_id, "timeline"
        )
        time.sleep(1.2)

        if stats is None and timeline is None:
            print("No usable data; skipping save")
            continue

        checks = {}

        for label, field, event_type in [
            ("corners", "corner_kicks", "corner_kick"),
            ("yellow_cards", "yellow_cards", "yellow_card"),
            ("red_cards", "red_cards", "red_card"),
        ]:
            match_flag, official, events = compare(
                stats, timeline, field, event_type
            )
            checks[label] = match_flag

            print(
                f"{label}: stats={official}, "
                f"timeline={events}, "
                f"match={match_flag}",
                flush=True,
            )

        if isinstance(timeline, dict):
            events = timeline.get("events", [])
            if isinstance(events, list):
                types = Counter(
                    event.get("type")
                    for event in events
                    if isinstance(event, dict)
                )
                print("EVENT TYPES:", dict(types))

                goals = [
                    {
                        "minute": e.get("minute"),
                        "extra_time": e.get("extra_time"),
                        "team": e.get("team"),
                    }
                    for e in events
                    if isinstance(e, dict)
                    and e.get("type") == "goal"
                ]
                print("GOALS:", goals)

        record = {
            "match_id": match_id,
            "stats_data": stats,
            "timeline_data": timeline,
            "stats_status": stats_status,
            "timeline_status": timeline_status,
            "corners_match": checks["corners"],
            "yellow_cards_match": checks["yellow_cards"],
            "red_cards_match": checks["red_cards"],
        }

        # Only update the new event table.
        # Do not replace previously saved good data
        # with an unsuccessful response.
        existing = (
            db.table("historical_match_events")
            .select("stats_data,timeline_data")
            .eq("match_id", match_id)
            .limit(1)
            .execute()
        )

        old = existing.data[0] if existing.data else None

        if old:
            if stats is None:
                record["stats_data"] = old.get("stats_data")
            if timeline is None:
                record["timeline_data"] = old.get("timeline_data")

        db.table("historical_match_events").upsert(
            record, on_conflict="match_id"
        ).execute()

        print("SAVED TO SUPABASE", flush=True)

    print("\nFIVE-MATCH TEST COMPLETE", flush=True)


if __name__ == "__main__":
    main()
