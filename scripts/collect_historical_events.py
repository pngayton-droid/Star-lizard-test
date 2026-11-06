
import os
import time
from collections import Counter
from datetime import datetime, timezone

import requests
from supabase import create_client

# STARLIZARD - HISTORICAL EVENTS COLLECTOR
# Restartable, rate-limited.
# Writes ONLY to historical_match_events.
# Preserves raw API data and flags discrepancies.

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
                try:
                    wait = float(
                        response.headers.get("Retry-After", "")
                    )
                except (ValueError, TypeError):
                    wait = 15 * attempt

                wait = min(max(wait, 2), 120)

                print(
                    f"RATE LIMIT: {endpoint} "
                    f"attempt {attempt}/{MAX_ATTEMPTS}; "
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

            data = (
                payload.get("data")
                if isinstance(payload, dict)
                else None
            )

            if not isinstance(data, dict):
                print(
                    f"INVALID RESPONSE: {endpoint}",
                    flush=True,
                )
                return None, status

            return data, status

        except RateLimitExhausted:
            raise

        except (
            requests.RequestException,
            ValueError,
        ) as exc:
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
            .select(
                "match_id,stats_data,timeline_data"
            )
            .order("match_id")
            .range(
                offset,
                offset + PAGE_SIZE - 1,
            )
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
                "home_team,away_team,"
                "home_goals,away_goals"
            )
            .like("match_id", "mt_%")
            .not_.is_("home_goals", "null")
            .order("match_date", desc=True)
            .order("match_id")
            .range(
                offset,
                offset + PAGE_SIZE - 1,
            )
            .execute()
        )

        rows = result.data or []

        for match in rows:
            old = existing.get(
                match["match_id"], {}
            )

            # Never refetch completed matches.
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


def official_pair(stats, field, period="all"):
    if not isinstance(stats, dict):
        return None

    values = (
        stats.get("overview", {})
        .get(field, {})
        .get(period)
    )

    if not isinstance(values, dict):
        return None

    try:
        if (
            values.get("home") is None
            or values.get("away") is None
        ):
            return None

        return (
            int(values["home"]),
            int(values["away"]),
        )

    except (TypeError, ValueError):
        return None


def valid_events(timeline):
    if not isinstance(timeline, dict):
        return None

    if timeline.get("coverage") != "full":
        return None

    events = timeline.get("events")

    if not isinstance(events, list):
        return None

    if not all(
        isinstance(event, dict)
        for event in events
    ):
        return None

    return events


def count_pair(
    events,
    home,
    away,
    kind,
    period=None,
):
    counts = [0, 0]

    for event in events:
        if (
            period is not None
            and event.get("period") != period
        ):
            continue

        event_type = event.get("type")
        team = event.get("team")

        name = (
            team.get("name")
            if isinstance(team, dict)
            else None
        )

        if name not in (home, away):
            continue

        index = 0 if name == home else 1

        if (
            kind == "corners"
            and event_type == "corner_kick"
        ):
            # Observed timeline convention:
            # team identifies the opposing side.
            counts[1 - index] += 1

        elif (
            kind == "yellows"
            and event_type in (
                "yellow_card",
                "yellow_red_card",
            )
        ):
            counts[index] += 1

        elif (
            kind == "reds"
            and event_type in (
                "red_card",
                "yellow_red_card",
            )
        ):
            counts[index] += 1

        elif kind == "goals":
            if event_type in (
                "goal",
                "penalty_scored",
            ):
                counts[index] += 1

            elif event_type == "own_goal":
                counts[1 - index] += 1

    return tuple(counts)


def validate(
    stats,
    timeline,
    home,
    away,
    home_goals,
    away_goals,
):
    events = valid_events(timeline)

    mapping = {
        "corners": (
            "corner_kicks",
            "corners",
        ),
        "yellow_cards": (
            "yellow_cards",
            "yellows",
        ),
        "red_cards": (
            "red_cards",
            "reds",
        ),
    }

    checks = {}

    for label, (field, kind) in mapping.items():
        official = official_pair(
            stats, field
        )

        counted = (
            count_pair(
                events, home, away, kind
            )
            if events is not None
            else None
        )

        if (
            official is not None
            and counted is not None
        ):
            ok = official == counted
        else:
            ok = None

        half_results = []

        if events is not None:
            for period in (
                "first_half",
                "second_half",
            ):
                official_half = official_pair(
                    stats, field, period
                )

                if official_half is not None:
                    counted_half = count_pair(
                        events,
                        home,
                        away,
                        kind,
                        period,
                    )

                    half_results.append(
                        official_half == counted_half
                    )

                    print(
                        f"  {label} {period}: "
                        f"stats={official_half}, "
                        f"timeline={counted_half}",
                        flush=True,
                    )

        if (
            ok is True
            and half_results
            and not all(half_results)
        ):
            ok = False

        checks[label] = ok

        print(
            f"{label}: "
            f"stats={official}, "
            f"timeline={counted}, "
            f"match={ok}",
            flush=True,
        )

    try:
        official_goals = (
            int(home_goals),
            int(away_goals),
        )
    except (TypeError, ValueError):
        official_goals = None

    counted_goals = (
        count_pair(
            events,
            home,
            away,
            "goals",
        )
        if events is not None
        else None
    )

    goals_ok = (
        official_goals == counted_goals
        if (
            official_goals is not None
            and counted_goals is not None
        )
        else None
    )

    print(
        f"goals: score={official_goals}, "
        f"timeline={counted_goals}, "
        f"match={goals_ok}",
        flush=True,
    )

    return checks


def save_match(
    match,
    stats,
    timeline,
    stats_status,
    timeline_status,
):
    checks = validate(
        stats,
        timeline,
        match["home_team"],
        match["away_team"],
        match.get("home_goals"),
        match.get("away_goals"),
    )

    record = {
        "match_id": match["match_id"],
        "stats_data": stats,
        "timeline_data": timeline,
        "stats_status": stats_status,
        "timeline_status": timeline_status,
        "corners_match": checks["corners"],
        "yellow_cards_match": checks["yellow_cards"],
        "red_cards_match": checks["red_cards"],
        "updated_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
    }

    db.table(
        "historical_match_events"
    ).upsert(
        record,
        on_conflict="match_id",
    ).execute()

    print(
        "SAVED TO SUPABASE",
        flush=True,
    )


def main():
    print(
        "\nSTARLIZARD HISTORICAL "
        "EVENT COLLECTOR",
        flush=True,
    )

    print(
        "Batch size:",
        BATCH_SIZE,
        flush=True,
    )

    existing = load_existing()

    completed_before = sum(
        row.get("stats_data") is not None
        and row.get("timeline_data") is not None
        for row in existing.values()
    )

    print(
        "Previously completed:",
        completed_before,
        flush=True,
    )

    pending = find_pending(existing)

    print(
        "Selected for this run:",
        len(pending),
        flush=True,
    )

    saved = 0
    fully_completed = 0
    stopped_for_rate_limit = False

    for index, match in enumerate(
        pending, 1
    ):
        match_id = match["match_id"]
        old = existing.get(
            match_id, {}
        )

        print(
            f"\n{index}/{len(pending)} "
            f"{match['home_team']} v "
            f"{match['away_team']} "
            f"({match_id})",
            flush=True,
        )

        stats = old.get("stats_data")
        timeline = old.get("timeline_data")

        stats_status = (
            200 if stats is not None
            else None
        )

        timeline_status = (
            200 if timeline is not None
            else None
        )

        try:
            if stats is None:
                stats, stats_status = fetch(
                    match_id, "stats"
                )
                time.sleep(
                    REQUEST_DELAY
                )

            if timeline is None:
                timeline, timeline_status = fetch(
                    match_id, "timeline"
                )
                time.sleep(
                    REQUEST_DELAY
                )

        except RateLimitExhausted:
            print(
                "STOPPING: API rate limit "
                "persists. Saved matches "
                "are safe.",
                flush=True,
            )
            stopped_for_rate_limit = True
            break

        if (
            stats is None
            and timeline is None
        ):
            print(
                "No usable response; "
                "will retry later.",
                flush=True,
            )
            continue

        events = valid_events(
            timeline
        )

        if events is not None:
            types = Counter(
                event.get("type")
                for event in events
            )

            print(
                "EVENT TYPES:",
                dict(types),
                flush=True,
            )

        save_match(
            match,
            stats,
            timeline,
            stats_status,
            timeline_status,
        )

        saved += 1

        if (
            stats is not None
            and timeline is not None
        ):
            fully_completed += 1

    print("\n" + "=" * 55)
    print("COLLECTION SUMMARY")
    print("Selected:", len(pending))
    print("Saved this run:", saved)
    print(
        "Fully completed this run:",
        fully_completed,
    )
    print(
        "Stopped for rate limit:",
        stopped_for_rate_limit,
    )
    print(
        "Existing complete before run:",
        completed_before,
    )
    print("=" * 55, flush=True)


if __name__ == "__main__":
    main()
