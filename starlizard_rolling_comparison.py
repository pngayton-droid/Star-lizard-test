
"""PRO STARLIZARD: rolling ridge vs quasi-Poisson comparison.

Read-only Supabase research. No StatsAPI calls or database writes.
Reports historical coverage and performance by football season.
All training uses matches strictly before the prediction date.
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
from starlizard_walkforward_backtest import (
    COMPETITION,
    END,
    MIN_TRAIN,
    fetch,
)
from starlizard_ridge_vs_poisson import (
    fit_quasipoisson,
    qp_goals,
)

START = os.getenv("ROLLING_START", "2024-08-01")
MAX_DATES = int(os.getenv("ROLLING_MAX_DATES", "0"))


def season_for(day):
    year = int(day[:4])
    if int(day[5:7]) < 7:
        year -= 1
    return f"{year}/{str(year + 1)[-2:]}"


def report(group, label):
    if group.empty:
        return

    p = group[
        [f"{label}_home", f"{label}_draw", f"{label}_away"]
    ].to_numpy(dtype=float)

    y = group["outcome"].to_numpy(dtype=int)
    actual = np.eye(3)[y]

    brier = np.mean(np.sum((p - actual) ** 2, axis=1))
    logloss = -np.log(
        np.clip(p[np.arange(len(y)), y], 1e-12, 1.0)
    ).mean()

    over = group[f"{label}_over"].to_numpy(dtype=float)
    btts = group[f"{label}_btts"].to_numpy(dtype=float)

    over_brier = np.mean(
        (over - group["actual_over"].to_numpy()) ** 2
    )
    btts_brier = np.mean(
        (btts - group["actual_btts"].to_numpy()) ** 2
    )

    goals = group[f"{label}_total"].mean()

    print(
        f"  {label}: "
        f"1X2 Brier={brier:.5f}; "
        f"log loss={logloss:.5f}; "
        f"Over2.5 Brier={over_brier:.5f}; "
        f"BTTS Brier={btts_brier:.5f}; "
        f"predicted goals={goals:.3f}"
    )


def main():
    db = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SECRET_KEY"],
    )

    raw = fetch(db)
    history = clean_history(raw, COMPETITION, END)

    if history.empty:
        raise RuntimeError("No valid historical xG data")

    goals = raw[
        ["match_id", "home_goals", "away_goals"]
    ].drop_duplicates("match_id", keep="last").copy()

    for col in ("home_goals", "away_goals"):
        goals[col] = pd.to_numeric(goals[col], errors="coerce")

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

    print("HISTORICAL DATA COVERAGE")
    print(f"Competition: {COMPETITION}")
    print(f"Valid xG matches: {len(history)}")
    print(f"Matches with valid final scores: {len(data)}")
    print(f"Earliest xG date: {history.match_date.min()}")
    print(f"Latest xG date: {history.match_date.max()}")

    print("Available scored fixtures by season:")
    data["season"] = data.day.map(season_for)

    for season, group in data.groupby("season", sort=True):
        print(f"  {season}: {len(group)} fixtures")

    dates = sorted(
        day for day in data.day.unique()
        if START <= day < END
    )

    if MAX_DATES > 0:
        dates = dates[:MAX_DATES]

    records = []

    for day in dates:
        cutoff = pd.Timestamp(day, tz="UTC")
        prior = history[history.match_date < cutoff]
        prior_goals = data[data.match_date < cutoff]

        if (
            len(prior) < MIN_TRAIN
            or len(prior_goals) < MIN_TRAIN
        ):
            continue

        ridge = fit_ratings(
            prior,
            COMPETITION,
            day,
            minimum_matches=MIN_TRAIN,
        )

        quasi = fit_quasipoisson(prior, cutoff)

        baseline_home = float(prior_goals.home_goals.mean())
        baseline_away = float(prior_goals.away_goals.mean())

        day_count = 0

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

            record = {
                "date": day,
                "season": season_for(day),
                "outcome": (
                    0 if match.home_goals > match.away_goals
                    else 1 if match.home_goals == match.away_goals
                    else 2
                ),
                "actual_over": int(
                    match.home_goals + match.away_goals >= 3
                ),
                "actual_btts": int(
                    match.home_goals > 0 and match.away_goals > 0
                ),
                "actual_total": float(
                    match.home_goals + match.away_goals
                ),
            }

            for label, home_rate, away_rate in (
                ("ridge", rh, ra),
                ("quasipoisson", qh, qa),
                ("baseline", baseline_home, baseline_away),
            ):
                probs = standard_markets(
                    score_matrix(home_rate, away_rate)
                )

                for outcome in ("home", "draw", "away"):
                    record[f"{label}_{outcome}"] = probs[outcome]

                record[f"{label}_over"] = probs["over_2_5"]
                record[f"{label}_btts"] = probs["btts_yes"]
                record[f"{label}_total"] = home_rate + away_rate

            records.append(record)
            day_count += 1

        print(
            f"{day}: {day_count} predictions; "
            f"{len(prior)} earlier training matches",
            flush=True,
        )

    if not records:
        raise RuntimeError(
            "No eligible predictions. Check date range and data."
        )

    results = pd.DataFrame(records)

    print("\nROLLING MODEL COMPARISON")
    print(
        "Training uses strictly earlier match dates. "
        "Lower Brier and log loss are better."
    )

    for season, group in results.groupby("season", sort=True):
        print(
            f"\nSEASON {season}: "
            f"{len(group)} fixtures across "
            f"{group.date.nunique()} dates"
        )
        print(
            f"  Actual Over2.5={group.actual_over.mean():.1%}; "
            f"BTTS={group.actual_btts.mean():.1%}; "
            f"mean goals={group.actual_total.mean():.3f}"
        )

        for label in ("ridge", "quasipoisson", "baseline"):
            report(group, label)

    print(
        f"\nALL PERIODS: {len(results)} fixtures "
        f"across {results.date.nunique()} dates"
    )

    for label in ("ridge", "quasipoisson", "baseline"):
        report(results, label)

    print(
        "\nResearch only. Historical evaluation periods may "
        "overlap previous experiments. No bookmaker edge established."
    )


if __name__ == "__main__":
    main()
