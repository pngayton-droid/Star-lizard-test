
"""PRO STARLIZARD: recent-performance blend comparison.

Read-only chronological experiment. No StatsAPI requests,
database writes or production pricing-engine changes.

Compare Ridge, quasi-Poisson, fixed 50/50 blend,
and adaptive blends using the last 100 or 200 matches.
"""

import os
import numpy as np
import pandas as pd
from supabase import create_client

from starlizard_pricing_engine import (
    clean_history,
    fit_ratings,
    score_matrix,
    standard_markets,
)
from starlizard_ridge_vs_poisson import (
    fit_quasipoisson,
    qp_goals,
)
from starlizard_walkforward_backtest import (
    COMPETITION,
    END,
    MIN_TRAIN,
    fetch,
)

START = os.getenv("RECENT_BLEND_START", "2024-08-01")
MAX_DATES = int(os.getenv("RECENT_BLEND_MAX_DATES", "0"))
WEIGHTS = np.linspace(0, 1, 11)
MARKETS = ("home", "draw", "away", "over_2_5", "btts_yes")


def season_for(day):
    year = int(day[:4])
    if int(day[5:7]) < 7:
        year -= 1
    return f"{year}/{str(year + 1)[-2:]}"


def predict(home, away):
    return standard_markets(score_matrix(home, away))


def combine(record, weight):
    home = (
        weight * record["ridge_h"]
        + (1 - weight) * record["quasi_h"]
    )
    away = (
        weight * record["ridge_a"]
        + (1 - weight) * record["quasi_a"]
    )
    return predict(home, away)


def combined_loss(probs, record):
    actual = np.zeros(3)
    actual[record["outcome"]] = 1

    forecast = np.array([
        probs["home"],
        probs["draw"],
        probs["away"],
    ])

    return float(
        np.sum((forecast - actual) ** 2)
        + (probs["over_2_5"] - record["over"]) ** 2
        + (probs["btts_yes"] - record["btts"]) ** 2
    )


def select_weight(previous, window):
    """Only completed predictions before today's matches."""
    sample = previous[-window:]

    if len(sample) < window:
        return 0.5

    losses = [
        np.mean([
            combined_loss(combine(r, weight), r)
            for r in sample
        ])
        for weight in WEIGHTS
    ]

    return float(WEIGHTS[int(np.argmin(losses))])


def evaluate(records, name):
    probs = np.array([
        [
            r[name]["home"],
            r[name]["draw"],
            r[name]["away"],
        ]
        for r in records
    ])

    outcomes = np.array([r["outcome"] for r in records])
    actual = np.eye(3)[outcomes]

    brier = float(
        np.mean(np.sum((probs - actual) ** 2, axis=1))
    )

    logloss = float(
        -np.mean(np.log(np.clip(
            probs[np.arange(len(records)), outcomes],
            1e-12, 1.0
        )))
    )

    over_brier = float(np.mean([
        (r[name]["over_2_5"] - r["over"]) ** 2
        for r in records
    ]))

    btts_brier = float(np.mean([
        (r[name]["btts_yes"] - r["btts"]) ** 2
        for r in records
    ]))

    print(
        f"  {name:9s} "
        f"1X2={brier:.5f} "
        f"logloss={logloss:.5f} "
        f"Over2.5={over_brier:.5f} "
        f"BTTS={btts_brier:.5f}"
    )


def report(records, title):
    print(f"\n{title}: {len(records)} matches")

    for name in ("ridge", "quasi", "fixed50", "recent100", "recent200"):
        evaluate(records, name)

    for name in ("recent100_weight", "recent200_weight"):
        print(
            f"  Mean {name}: "
            f"{np.mean([r[name] for r in records]):.3f}"
        )


def main():
    db = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SECRET_KEY"],
    )

    raw = fetch(db)
    history = clean_history(raw, COMPETITION, END)

    goals = raw[
        ["match_id", "home_goals", "away_goals"]
    ].drop_duplicates("match_id", keep="last").copy()

    for col in ("home_goals", "away_goals"):
        goals[col] = pd.to_numeric(
            goals[col], errors="coerce"
        )

    data = history.merge(
        goals, on="match_id", how="inner"
    ).dropna(subset=["home_goals", "away_goals"])

    data = data[
        (data.home_goals >= 0)
        & (data.away_goals >= 0)
        & (data.home_goals % 1 == 0)
        & (data.away_goals % 1 == 0)
    ].copy()

    data["day"] = data.match_date.dt.strftime("%Y-%m-%d")

    dates = sorted(
        day for day in data.day.unique()
        if START <= day < END
    )

    if MAX_DATES > 0:
        dates = dates[:MAX_DATES]

    previous = []
    evaluated = []

    for day in dates:
        cutoff = pd.Timestamp(day, tz="UTC")
        training = history[history.match_date < cutoff]

        if len(training) < MIN_TRAIN:
            continue

        ridge = fit_ratings(
            training,
            COMPETITION,
            day,
            minimum_matches=MIN_TRAIN,
        )
        quasi = fit_quasipoisson(training, cutoff)

        # Weights are locked before today's results.
        w100 = select_weight(previous, 100)
        w200 = select_weight(previous, 200)

        todays_records = []

        for match in data[data.day == day].itertuples(index=False):
            if (
                match.home_team not in ridge.teams
                or match.away_team not in ridge.teams
            ):
                continue

            rh, ra = ridge.expected_goals(
                match.home_team, match.away_team
            )
            qh, qa = qp_goals(
                quasi, match.home_team, match.away_team
            )

            record = {
                "day": day,
                "season": season_for(day),
                "outcome": (
                    0 if match.home_goals > match.away_goals
                    else 1 if match.home_goals == match.away_goals
                    else 2
                ),
                "over": int(
                    match.home_goals + match.away_goals >= 3
                ),
                "btts": int(
                    match.home_goals > 0
                    and match.away_goals > 0
                ),
                "ridge_h": rh,
                "ridge_a": ra,
                "quasi_h": qh,
                "quasi_a": qa,
                "recent100_weight": w100,
                "recent200_weight": w200,
            }

            record["ridge"] = predict(rh, ra)
            record["quasi"] = predict(qh, qa)
            record["fixed50"] = combine(record, 0.5)
            record["recent100"] = combine(record, w100)
            record["recent200"] = combine(record, w200)

            todays_records.append(record)

        # Only evaluate once both rolling windows are ready.
        # All five approaches use the identical evaluation set.
        if len(previous) >= 200:
            evaluated.extend(todays_records)

        # Add results only after all predictions for today.
        previous.extend(todays_records)

        print(
            f"{day}: {len(todays_records)} matches; "
            f"prior={len(previous) - len(todays_records)}; "
            f"Ridge weight 100={w100:.1f}, "
            f"200={w200:.1f}",
            flush=True,
        )

    if not evaluated:
        raise RuntimeError(
            "No evaluation matches. Extend the date range."
        )

    print("\nRECENT PERFORMANCE BLEND RESULTS")
    print("Lower Brier and log loss are better.")
    print("All models evaluated on identical fixtures.")

    for season in sorted(set(r["season"] for r in evaluated)):
        group = [
            r for r in evaluated
            if r["season"] == season
        ]
        report(group, f"SEASON {season}")

    report(evaluated, "ALL EVALUATED")

    print(
        "\nResearch only. No betting edge established."
    )


if __name__ == "__main__":
    main()
