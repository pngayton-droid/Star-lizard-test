
"""PRO STARLIZARD: chronological blended-model experiment.

Compare Ridge, quasi-Poisson and an adaptive blend.
Blend weights are selected using earlier completed fixtures only.

Read-only Supabase. No StatsAPI calls or database writes.
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

START = os.getenv("BLEND_START", "2024-08-01")
MIN_BLEND_HISTORY = int(os.getenv("BLEND_MIN_HISTORY", "100"))
MAX_DATES = int(os.getenv("BLEND_MAX_DATES", "0"))

WEIGHTS = np.linspace(0, 1, 11)
MARKETS = ("home", "draw", "away", "over_2_5", "btts_yes")


def season_for(day):
    year = int(day[:4])
    if int(day[5:7]) < 7:
        year -= 1
    return f"{year}/{str(year + 1)[-2:]}"


def probabilities(home_rate, away_rate):
    return standard_markets(
        score_matrix(home_rate, away_rate)
    )


def score_prediction(p, actual):
    outcome = actual["outcome"]
    y = np.zeros(3)
    y[outcome] = 1

    x = np.array([
        p["home"], p["draw"], p["away"]
    ])

    result = np.sum((x - y) ** 2)

    result += (
        p["over_2_5"] - actual["over"]
    ) ** 2

    result += (
        p["btts_yes"] - actual["btts"]
    ) ** 2

    return float(result)


def choose_weight(prior_records):
    """Select weight using previously predicted fixtures only."""
    if len(prior_records) < MIN_BLEND_HISTORY:
        return 0.5

    scores = []

    for weight in WEIGHTS:
        losses = []

        for r in prior_records:
            h = (
                weight * r["ridge_h"]
                + (1 - weight) * r["quasi_h"]
            )
            a = (
                weight * r["ridge_a"]
                + (1 - weight) * r["quasi_a"]
            )

            p = probabilities(h, a)
            losses.append(score_prediction(p, r))

        scores.append(np.mean(losses))

    return float(WEIGHTS[np.argmin(scores)])


def evaluate(records, label):
    if not records:
        return

    p = np.array([
        [
            r[f"{label}_home"],
            r[f"{label}_draw"],
            r[f"{label}_away"],
        ]
        for r in records
    ])

    outcomes = np.array([r["outcome"] for r in records])
    y = np.eye(3)[outcomes]

    brier = np.mean(np.sum((p - y) ** 2, axis=1))
    logloss = -np.log(
        np.clip(
            p[np.arange(len(records)), outcomes],
            1e-12,
            1,
        )
    ).mean()

    over_brier = np.mean([
        (
            r[f"{label}_over_2_5"] - r["over"]
        ) ** 2
        for r in records
    ])

    btts_brier = np.mean([
        (
            r[f"{label}_btts_yes"] - r["btts"]
        ) ** 2
        for r in records
    ])

    print(
        f"  {label:7s} "
        f"1X2={brier:.5f} "
        f"logloss={logloss:.5f} "
        f"Over2.5={over_brier:.5f} "
        f"BTTS={btts_brier:.5f}"
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
        d for d in data.day.unique()
        if START <= d < END
    )

    if MAX_DATES > 0:
        dates = dates[:MAX_DATES]

    prior_records = []
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

        # Select once per match day, before adding its results.
        weight = choose_weight(prior_records)

        count = 0

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
                quasi,
                match.home_team,
                match.away_team,
            )

            bh = weight * rh + (1 - weight) * qh
            ba = weight * ra + (1 - weight) * qa

            record = {
                "date": day,
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
                "weight": weight,
            }

            for label, h, a in (
                ("ridge", rh, ra),
                ("quasi", qh, qa),
                ("blend", bh, ba),
            ):
                p = probabilities(h, a)

                for market in MARKETS:
                    record[f"{label}_{market}"] = p[market]

            prior_records.append(record)

            # Warm-up predictions are used to select future weights,
            # not counted as adaptive-blend evaluation fixtures.
            if len(prior_records) > MIN_BLEND_HISTORY:
                evaluated.append(record)

            count += 1

        print(
            f"{day}: {count} predictions; "
            f"Ridge weight={weight:.1f}; "
            f"prior predictions={len(prior_records) - count}",
            flush=True,
        )

    if not evaluated:
        raise RuntimeError(
            "No evaluated matches. Reduce BLEND_MIN_HISTORY "
            "or extend the test period."
        )

    print("\nADAPTIVE BLEND RESULTS")
    print(
        f"Evaluated fixtures: {len(evaluated)}; "
        f"warm-up requirement: {MIN_BLEND_HISTORY}"
    )
    print("Lower scores are better.")

    for season in sorted(set(r["season"] for r in evaluated)):
        group = [
            r for r in evaluated
            if r["season"] == season
        ]

        print(f"\nSEASON {season}: {len(group)} fixtures")

        for label in ("ridge", "quasi", "blend"):
            evaluate(group, label)

        weights = [r["weight"] for r in group]
        print(
            f"  Mean Ridge blend weight: "
            f"{np.mean(weights):.2f}"
        )

    print(f"\nALL EVALUATED: {len(evaluated)} fixtures")

    for label in ("ridge", "quasi", "blend"):
        evaluate(evaluated, label)

    print(
        "\nResearch only. No market odds comparison, "
        "profitability or betting edge established."
    )


if __name__ == "__main__":
    main()
