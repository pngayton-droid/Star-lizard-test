
"""PRO STARLIZARD — Halftime Historical Intelligence v1.

Search comparable historical halftime situations and calculate
second-half outcome frequencies and historical fair odds.

Read-only Supabase. No TheStatsAPI calls or database writes.

Usage:
  python starlizard_halftime_analyser.py

Configuration through GitHub Actions environment variables.
"""

import math
import os
import numpy as np
import pandas as pd
from supabase import create_client


COMPETITION = os.getenv("HT_COMPETITION", "ALL")
HOME_HT_GOALS = int(os.getenv("HT_HOME_GOALS", "0"))
AWAY_HT_GOALS = int(os.getenv("HT_AWAY_GOALS", "1"))
HOME_HT_XG = float(os.getenv("HT_HOME_XG", "0.85"))
AWAY_HT_XG = float(os.getenv("HT_AWAY_XG", "0.35"))
XG_TOLERANCE = float(os.getenv("HT_XG_TOLERANCE", "0.30"))
MIN_SAMPLE = int(os.getenv("HT_MIN_SAMPLE", "100"))

COLUMNS = (
    "match_id,competition_id,match_date,"
    "home_team,away_team,"
    "home_ht_goals,away_ht_goals,"
    "home_ht_xg,away_ht_xg,"
    "home_goals,away_goals"
)


def fetch_history(db):
    rows = []
    offset = 0

    while True:
        query = (
            db.table("historical_xg")
            .select(COLUMNS)
            .order("match_date")
            .order("match_id")
        )

        if COMPETITION != "ALL":
            query = query.eq("competition_id", COMPETITION)

        result = query.range(offset, offset + 499).execute()
        batch = result.data or []
        rows.extend(batch)

        if len(batch) < 500:
            break

        offset += 500

    return pd.DataFrame(rows)


def prepare_history(raw):
    if raw.empty:
        raise RuntimeError("No historical records found.")

    numeric = [
        "home_ht_goals",
        "away_ht_goals",
        "home_ht_xg",
        "away_ht_xg",
        "home_goals",
        "away_goals",
    ]

    df = raw.copy()

    for column in numeric:
        df[column] = pd.to_numeric(
            df[column], errors="coerce"
        )

    df = df.dropna(subset=numeric)

    df = df.drop_duplicates(
        subset=["match_id"], keep="last"
    )

    for column in (
        "home_ht_goals",
        "away_ht_goals",
        "home_goals",
        "away_goals",
    ):
        df = df[
            (df[column] >= 0)
            & (df[column] % 1 == 0)
        ]

    df = df[
        (df.home_ht_xg >= 0)
        & (df.away_ht_xg >= 0)
        & (df.home_goals >= df.home_ht_goals)
        & (df.away_goals >= df.away_ht_goals)
    ].copy()

    df["home_2h"] = (
        df.home_goals - df.home_ht_goals
    )

    df["away_2h"] = (
        df.away_goals - df.away_ht_goals
    )

    df["total_2h"] = df.home_2h + df.away_2h

    return df


def matching_games(df, tolerance):
    return df[
        (df.home_ht_goals == HOME_HT_GOALS)
        & (df.away_ht_goals == AWAY_HT_GOALS)
        & (
            (df.home_ht_xg - HOME_HT_XG).abs()
            <= tolerance
        )
        & (
            (df.away_ht_xg - AWAY_HT_XG).abs()
            <= tolerance
        )
    ].copy()


def wilson_interval(hits, total, z=1.96):
    if total == 0:
        return 0.0, 1.0

    p = hits / total
    z2 = z * z
    denominator = 1 + z2 / total

    centre = (p + z2 / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            p * (1 - p) / total
            + z2 / (4 * total * total)
        )
        / denominator
    )

    return (
        max(0.0, centre - margin),
        min(1.0, centre + margin),
    )


def report_outcome(label, condition, total):
    hits = int(condition.sum())
    probability = hits / total

    low, high = wilson_interval(hits, total)

    fair_odds = (
        f"{1 / probability:.2f}"
        if probability > 0
        else "N/A"
    )

    print(
        f"{label:34s} "
        f"{hits:4d}/{total:<4d} "
        f"{probability:6.1%} "
        f"odds={fair_odds:>6s} "
        f"95% CI={low:.1%}-{high:.1%}"
    )


def main():
    if (
        HOME_HT_GOALS < 0
        or AWAY_HT_GOALS < 0
        or HOME_HT_XG < 0
        or AWAY_HT_XG < 0
        or XG_TOLERANCE < 0
        or MIN_SAMPLE < 1
    ):
        raise ValueError("Invalid halftime configuration.")

    db = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SECRET_KEY"],
    )

    print("PRO STARLIZARD — HALFTIME INTELLIGENCE")
    print("=" * 62)

    raw = fetch_history(db)
    df = prepare_history(raw)

    print(f"Competition filter: {COMPETITION}")
    print(f"Raw records fetched: {len(raw)}")
    print(f"Valid completed matches: {len(df)}")

    print(
        f"\nHALFTIME SITUATION: "
        f"{HOME_HT_GOALS}-{AWAY_HT_GOALS}"
    )
    print(
        f"Home HT xG: {HOME_HT_XG:.2f} | "
        f"Away HT xG: {AWAY_HT_XG:.2f}"
    )

    # Expand the xG search gradually if the sample is small.
    tolerance = XG_TOLERANCE
    matches = matching_games(df, tolerance)

    while len(matches) < MIN_SAMPLE and tolerance < 1.0:
        tolerance = round(
            min(1.0, tolerance + 0.10), 2
        )
        matches = matching_games(df, tolerance)

    n = len(matches)

    print(f"\nFinal xG tolerance: +/-{tolerance:.2f}")
    print(f"Historical matches found: {n}")

    if n == 0:
        print("No comparable historical matches found.")
        return

    if n < MIN_SAMPLE:
        print(
            "WARNING: Small historical sample. "
            "Treat probabilities cautiously."
        )

    home = matches.home_2h
    away = matches.away_2h
    total = matches.total_2h

    print("\nSECOND-HALF OUTCOMES")
    print("-" * 88)

    outcomes = [
        ("Home scores in second half", home >= 1),
        ("Away scores in second half", away >= 1),
        ("Home wins second half", home > away),
        ("Second half drawn", home == away),
        ("Away wins second half", away > home),
        ("Over 0.5 second-half goals", total >= 1),
        ("Over 1.5 second-half goals", total >= 2),
        ("Over 2.5 second-half goals", total >= 3),
        ("Both teams score second half",
         (home >= 1) & (away >= 1)),
        ("Home avoids full-time defeat",
         matches.home_goals >= matches.away_goals),
        ("Away avoids full-time defeat",
         matches.away_goals >= matches.home_goals),
        ("Home wins full-time",
         matches.home_goals > matches.away_goals),
        ("Full-time draw",
         matches.home_goals == matches.away_goals),
        ("Away wins full-time",
         matches.away_goals > matches.home_goals),
    ]

    for label, condition in outcomes:
        report_outcome(label, condition, n)

    print("\nSECOND-HALF GOAL DISTRIBUTION")

    for number in (0, 1, 2, 3):
        if number < 3:
            condition = total == number
            label = f"Exactly {number} goals"
        else:
            condition = total >= 3
            label = "Three or more goals"

        report_outcome(label, condition, n)

    print("\nIMPORTANT")
    print(
        "These are historical frequencies, not "
        "validated individual-match predictions."
    )
    print(
        "Fair odds exclude bookmaker margin and "
        "estimation uncertainty."
    )
    print(
        "This first version does not determine "
        "which team scored the next goal."
    )
    print("No database records were modified.")


if __name__ == "__main__":
    main()
