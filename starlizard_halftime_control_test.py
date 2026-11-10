
"""PRO STARLIZARD — Halftime xG Control Group Test.

Compare baseline halftime outcomes against higher-xG
and narrow xG-matching situations.

Read-only Supabase. No TheStatsAPI requests or DB writes.
"""

import os
import math
import pandas as pd
from supabase import create_client

TABLE = "historical_xg"
PAGE_SIZE = 500

COLUMNS = (
    "match_id,competition_id,match_date,"
    "home_ht_goals,away_ht_goals,"
    "home_ht_xg,away_ht_xg,"
    "home_goals,away_goals"
)


def fetch_history(db):
    rows = []
    offset = 0

    while True:
        response = (
            db.table(TABLE)
            .select(COLUMNS)
            .order("match_date")
            .order("match_id")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )

        batch = response.data or []
        rows.extend(batch)

        if len(batch) < PAGE_SIZE:
            break

        offset += PAGE_SIZE

    return pd.DataFrame(rows)


def prepare(df):
    numeric = [
        "home_ht_goals",
        "away_ht_goals",
        "home_ht_xg",
        "away_ht_xg",
        "home_goals",
        "away_goals",
    ]

    df = df.copy()

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


def wilson(hits, n):
    if n == 0:
        return 0.0, 1.0

    z = 1.96
    p = hits / n
    denominator = 1 + z*z/n
    centre = (p + z*z/(2*n)) / denominator
    margin = (
        z * math.sqrt(
            p*(1-p)/n + z*z/(4*n*n)
        ) / denominator
    )

    return centre - margin, centre + margin


def outcome_rates(df):
    home = df.home_2h
    away = df.away_2h
    total = df.total_2h

    return {
        "Home scores 2H": home >= 1,
        "Home wins 2H": home > away,
        "Home avoids FT defeat":
            df.home_goals >= df.away_goals,
        "Home wins FT":
            df.home_goals > df.away_goals,
        "FT draw":
            df.home_goals == df.away_goals,
        "Over 1.5 goals 2H": total >= 2,
        "Over 2.5 goals 2H": total >= 3,
    }


def report_group(name, df):
    n = len(df)

    print("\n" + "=" * 78)
    print(name)
    print(f"Sample: {n} matches")
    print("=" * 78)

    if n == 0:
        return {}

    results = {}

    for label, condition in outcome_rates(df).items():
        hits = int(condition.sum())
        p = hits / n
        low, high = wilson(hits, n)

        odds = f"{1/p:.2f}" if p > 0 else "N/A"

        print(
            f"{label:26s} "
            f"{hits:4d}/{n:<4d} "
            f"{p:6.1%} "
            f"odds={odds:>6s} "
            f"CI={low:.1%}-{high:.1%}"
        )

        results[label] = p

    return results


def main():
    db = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SECRET_KEY"],
    )

    print("PRO STARLIZARD — HALFTIME CONTROL TEST")
    print("=" * 78)

    raw = fetch_history(db)
    df = prepare(raw)

    print(f"Raw records: {len(raw)}")
    print(f"Valid completed matches: {len(df)}")

    # Keep the same halftime score across all groups.
    baseline = df[
        (df.home_ht_goals == 0)
        & (df.away_ht_goals == 1)
    ].copy()

    higher_xg = baseline[
        baseline.home_ht_xg > baseline.away_ht_xg
    ].copy()

    narrow = baseline[
        (baseline.home_ht_xg.between(0.55, 1.15))
        & (baseline.away_ht_xg.between(0.05, 0.65))
    ].copy()

    groups = [
        ("A — ALL HOME TEAMS TRAILING 0-1", baseline),
        ("B — TRAILING HOME TEAM HAS HIGHER HT xG",
         higher_xg),
        ("C — ORIGINAL xG FILTER", narrow),
    ]

    results = {}

    for name, group in groups:
        results[name] = report_group(name, group)

    print("\n" + "=" * 78)
    print("DIFFERENCE VERSUS BASELINE")
    print("=" * 78)

    baseline_rates = results[groups[0][0]]

    for name, _ in groups[1:]:
        print(f"\n{name}")

        for outcome, p in results[name].items():
            base = baseline_rates.get(outcome)

            if base is None:
                continue

            difference = 100 * (p - base)

            print(
                f"{outcome:26s} "
                f"{difference:+.2f} percentage points"
            )

    print("\nIMPORTANT NOTES")
    print("- All three groups use halftime score 0-1.")
    print("- Groups overlap; differences are descriptive.")
    print("- This is not an out-of-sample backtest.")
    print("- No bookmaker prices are used.")
    print("- No database records were modified.")


if __name__ == "__main__":
    main()
