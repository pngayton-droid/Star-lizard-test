
import os
import time
from collections import Counter

import requests
from supabase import create_client

# STARLIZARD - HISTORICAL EVENTS COLLECTOR
# Safe batch collection, restartable and rate-limited.
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

BATCH_SIZE = min(
    max(int(os.getenv("EVENT_BATCH_SIZE", "25")), 1),
    100,
)
PAGE_SIZE = 500
REQUEST_DELAY = 1.3
MAX_ATTEMPTS = 4


class RateLimitExhausted(Exception):
    pass


def fetch(match_id, endpoint):
    url = f"{API_BASE}/{match_id}/{endpoint}"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = session.get(url, timeout=40)
            status = response.status_code

            if status == 429:
                retry_after = response.headers.get(
                    "Retry-After", ""
                )
                try:
                    wait = float(retry_after)
                except ValueError:
                    wait = 15 * attempt

                wait = min(max(wait, 2), 120)

                print(
                    f"RATE LIMIT: {endpoint} "
                    f"attempt {attempt}/{MAX_ATTEMPTS}, "
                    f"waiting {wait}s",
                    flush=True,
                )

                if attempt == MAX_ATTEMPTS:
                    raise RateLimitExhausted(
                        "API rate limit persists"
                    )

                time.sleep(wait)
                continue

            if status >= 500:
                print(
                    f"SERVER ERROR {status}: {endpoint}",
                    flush=True,
                )
                if attempt < MAX_ATTEMPTS:
                    time.sleep(10 * attempt)
                    continue
                return None, status

            if status != 200:
                print(
                    f"HTTP {status}: {endpoint} "
                    f"{response.text[:150]}",
                    flush=True,
                )
                return None, status

            payload = response.json()
            data = payload.get("data")

            if not isinstance(data, dict):
                print(
                    f"INVALID RESPONSE: {endpoint}",
                    flush=True,
                )
                return None, status

            return data, status

        except RateLimitExhausted:
            raise

        except (requests.RequestException, ValueError) as exc:
            print(
                f"REQUEST ERROR: {endpoint}: {exc}",
                flush=True,
            )
            if attempt < MAX_ATTEMPTS:
                time.sleep(10 * attempt)

    return None, None


def load_existing():
    records = {}
    offset = 0

    while True:
        result = (
            db.table("historical_match_events")
            .select("match_id,stats_data,timeline_data")
            .order("match_id")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )

        rows = result.data or []

        for row in rows:
            records[row["match_id"]] = row

        if len(rows) < PAGE_SIZE:
            break

        offset += PAGE_SIZE

    return records


def find_pending(existing):
    pending = []
    offset = 0

    while len(pending) < BATCH_SIZE:
        result = (
            db.table("historical_xg")
            .select(
                "match_id,match_date,"
                "home_team,away_team"
            )
            .like("match_id", "mt_%")
            .not_.is_("home_goals", "null")
            .order("match_date", desc=True)
            .order("match_id")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )

        rows = result.data or []

        for match in rows:
            old = existing.get(match["match_id"], {})

            # Fully collected matches need no more API calls.
            if (
                old.get("stats_data") is not None
                and old.get("timeline_data") is not None
            ):
                continue

            pending.append(match)

            if len(pending) >= BATCH_SIZE:
                break

        if len(rows) < PAGE_SIZE:
            break

        offset += PAGE_SIZE

    return pending


def stats_total(stats, field):
    if not isinstance(stats, dict):
        return None

    section = (
        stats.get("overview", {}).get(field, {})
    )

    if not isinstance(section, dict):
        return None

    values = section.get("all", {})

    if not isinstance(values, dict):
        return None

    home = values.get("home")
    away = values.get("away")

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
        event.get("type") == event_type
        for event in events
        if isinstance(event, dict)
    )


def compare(stats, timeline, field, event_type):
    a = stats_total(stats, field)
    b = timeline_count(timeline, event_type)

    if a is None or b is None:
        return None, a, b

    return a == b, a, b


def save_match(match_id, stats, timeline,
               stats_status, timeline_status):

    checks = {}

    for label, field, event_type in [
        ("corners", "corner_kicks", "corner_kick"),
        ("yellow_cards", "yellow_cards", "yellow_card"),
        ("red_cards", "red_cards", "red_card"),
    ]:
        matched, official, timeline_total = compare(
            stats, timeline, field, event_type
        )

        checks[label] = matched

        print(
            f"{label}: stats={official}, "
            f"timeline={timeline_total}, "
            f"match={matched}",
            flush=True,
        )

    record = {
        "match_id": match_id,
        "stats_data": stats,
        "timeline_data": timeline,
        "stats_status": stats_status,
        "timeline_status": timeline_status,
        "corners_match": checks["corners"],
        "yellow_cards_match": checks["yellow_cards"],
        "red_cards_match": checks["red_cards"],
        "updated_at": "now()",
    }

    # Supabase/PostgREST expects an actual timestamp,
    # not the SQL expression now().
    from datetime import datetime, timezone
    record["updated_at"] = (
        datetime.now(timezone.utc).isoformat()
    )

    db.table("historical_match_events").upsert(
        record,
        on_conflict="match_id",
    ).execute()

    print("SAVED TO SUPABASE", flush=True)


def main():
    print(
        "\nSTARLIZARD HISTORICAL EVENT COLLECTOR",
        flush=True,
    )
    print("Batch size:", BATCH_SIZE, flush=True)

    existing = load_existing()
    completed_before = sum(
        row.get("stats_data") is not None
        and row.get("timeline_data") is not None
        for row in existing.values()
    )

    print(
        "Previously completed:", completed_before,
        flush=True,
    )

    pending = find_pending(existing)

    print(
        "Selected for this run:", len(pending),
        flush=True,
    )

    saved = 0
    fully_completed = 0
    stopped_for_rate_limit = False

    for index, match in enumerate(pending, 1):
        match_id = match["match_id"]
        old = existing.get(match_id, {})

        print(
            f"\n{index}/{len(pending)} "
            f"{match['home_team']} v "
            f"{match['away_team']} "
            f"({match_id})",
            flush=True,
        )

        stats = old.get("stats_data")
        timeline = old.get("timeline_data")

        stats_status = 200 if stats is not None else None
        timeline_status = (
            200 if timeline is not None else None
        )

        try:
            if stats is None:
                stats, stats_status = fetch(
                    match_id, "stats"
                )
                time.sleep(REQUEST_DELAY)

            if timeline is None:
                timeline, timeline_status = fetch(
                    match_id, "timeline"
                )
                time.sleep(REQUEST_DELAY)

        except RateLimitExhausted:
            print(
                "STOPPING: API rate limit persists. "
                "Already saved matches are safe.",
                flush=True,
            )
            stopped_for_rate_limit = True
            break

        if stats is None and timeline is None:
            print(
                "No usable response; will retry "
                "in a future run.",
                flush=True,
            )
            continue

        if isinstance(timeline, dict):
            events = timeline.get("events", [])
            if isinstance(events, list):
                types = Counter(
                    event.get("type")
                    for event in events
                    if isinstance(event, dict)
                )
                print(
                    "EVENT TYPES:", dict(types),
                    flush=True,
                )

        save_match(
            match_id,
            stats,
            timeline,
            stats_status,
            timeline_status,
        )

        saved += 1

        if stats is not None and timeline is not None:
            fully_completed += 1

    print("\n" + "=" * 55)
    print("COLLECTION SUMMARY")
    print("Selected:", len(pending))
    print("Saved this run:", saved)
    print("Fully completed this run:", fully_completed)
    print("Stopped for rate limit:", stopped_for_rate_limit)
    print("Existing complete before run:", completed_before)
    print("=" * 55, flush=True)


if __name__ == "__main__":
    main()
