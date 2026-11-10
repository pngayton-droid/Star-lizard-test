
"""PRO STARLIZARD — ridge vs quasi-Poisson xG experiment.

Read-only Supabase research. No TheStatsAPI requests.
All models train on matches strictly before prediction day.
"""

import os
import math

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from supabase import create_client

from starlizard_pricing_engine import (
    clean_history,
    fit_ratings,
    score_matrix,
    standard_markets,
)
from starlizard_walkforward_backtest import (
    COMPETITION,
    START,
    END,
    MIN_TRAIN,
    MAX_DATES,
    fetch,
)

MARKETS = ("home", "draw", "away", "over_2_5", "btts_yes")


def fit_quasipoisson(history, cutoff, half_life_days=180.0, ridge=10.0):
    """Fit penalised log-link quasi-Poisson model to fractional xG."""
    teams = tuple(sorted(set(history.home_team) | set(history.away_team)))
    ix = {team: i for i, team in enumerate(teams)}
    n = len(teams)
    m = len(history)

    X = np.zeros((2 * m, 2 + 2 * n), dtype=float)
    y = np.zeros(2 * m, dtype=float)
    w = np.zeros(2 * m, dtype=float)

    for k, r in enumerate(history.itertuples(index=False)):
        h, a = ix[r.home_team], ix[r.away_team]
        age = max(0.0, (cutoff - r.match_date).total_seconds() / 86400.0)
        weight = 2.0 ** (-age / half_life_days)

        for j, attack, defence, is_home, xg in (
            (0, h, a, 1, r.home_xg),
            (1, a, h, 0, r.away_xg),
        ):
            pos = 2 * k + j
            X[pos, 0] = 1.0
            X[pos, 1] = is_home
            X[pos, 2 + attack] = 1.0
            X[pos, 2 + n + defence] = -1.0
            y[pos] = float(xg)
            w[pos] = weight

    penalty = np.full(X.shape[1], ridge)
    penalty[0] = 0.001
    penalty[1] = 2 * ridge

    initial = np.zeros(X.shape[1])
    initial[0] = math.log(max(float(np.average(y, weights=w)), 0.1))

    def objective(beta):
        eta = X @ beta
        mu = np.exp(np.clip(eta, -20.0, 20.0))
        value = np.sum(w * (mu - y * eta))
        value += 0.5 * np.dot(penalty * beta, beta)
        gradient = X.T @ (w * (mu - y)) + penalty * beta
        return float(value), gradient

    result = minimize(
        objective,
        initial,
        method="L-BFGS-B",
        jac=True,
        options={"maxiter": 300, "ftol": 1e-10},
    )

    if not result.success:
        raise RuntimeError(
            f"Quasi-Poisson fit failed: {result.message}"
        )

    return teams, ix, result.x


def qp_goals(fitted, home, away):
    teams, ix, beta = fitted
    n = len(teams)
    h, a = ix[home], ix[away]

    home_rate = np.exp(
        beta[0] + beta[1] + beta[2 + h] - beta[2 + n + a]
    )
    away_rate = np.exp(
        beta[0] + beta[2 + a] - beta[2 + n + h]
    )

    return (
        float(np.clip(home_rate, 0.1, 5.0)),
        float(np.clip(away_rate, 0.1, 5.0)),
    )


def evaluate(rows, label):
    probabilities = np.array([
        [r[f"{label}_{k}"] for k in ("home", "draw", "away")]
        for r in rows
    ])
    outcomes = np.array([r["outcome"] for r in rows], dtype=int)

    brier = np.mean(
        np.sum(
            (probabilities - np.eye(3)[outcomes]) ** 2,
            axis=1,
        )
    )
    logloss = -np.log(
        np.clip(
            probabilities[np.arange(len(outcomes)), outcomes],
            1e-12,
            1.0,
        )
    ).mean()

    print(
        f"{label}: 1X2 Brier={brier:.5f}; "
        f"log loss={logloss:.5f}"
    )

    for market, actual in (
        ("over_2_5", "actual_over25"),
        ("btts_yes", "actual_btts"),
    ):
        predicted = np.array([
            r[f"{label}_{market}"] for r in rows
        ])
        observed = np.array([r[actual] for r in rows])

        print(
            f"  {market}: "
            f"Brier={np.mean((predicted - observed) ** 2):.5f}; "
            f"predicted={predicted.mean():.1%}; "
            f"actual={observed.mean():.1%}"
        )

    mean_total = np.mean([
        r[f"{label}_total"] for r in rows
    ])
    print(f"  mean projected total goals={mean_total:.3f}")


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

    for column in ("home_goals", "away_goals"):
        goals[column] = pd.to_numeric(
            goals[column], errors="coerce"
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

    rows = []
    tested_days = 0

    for day in dates:
        cutoff = pd.Timestamp(day, tz="UTC")
        prior = history[history.match_date < cutoff]
        prior_goals = data[data.match_date < cutoff]

        if len(prior) < MIN_TRAIN or len(prior_goals) < MIN_TRAIN:
            continue

        ridge = fit_ratings(
            prior,
            COMPETITION,
            day,
            minimum_matches=MIN_TRAIN,
        )
        quasi_poisson = fit_quasipoisson(prior, cutoff)

        baseline_home = float(prior_goals.home_goals.mean())
        baseline_away = float(prior_goals.away_goals.mean())

        baseline = standard_markets(
            score_matrix(baseline_home, baseline_away)
        )

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
            ph, pa = qp_goals(
                quasi_poisson,
                match.home_team,
                match.away_team,
            )

            record = {
                "outcome": (
                    0 if match.home_goals > match.away_goals
                    else 1 if match.home_goals == match.away_goals
                    else 2
                ),
                "actual_over25": int(
                    match.home_goals + match.away_goals >= 3
                ),
                "actual_btts": int(
                    match.home_goals > 0 and match.away_goals > 0
                ),
                "actual_total": float(
                    match.home_goals + match.away_goals
                ),
            }

            for label, h, a, probs in (
                (
                    "ridge",
                    rh,
                    ra,
                    standard_markets(score_matrix(rh, ra)),
                ),
                (
                    "quasipoisson",
                    ph,
                    pa,
                    standard_markets(score_matrix(ph, pa)),
                ),
                (
                    "baseline",
                    baseline_home,
                    baseline_away,
                    baseline,
                ),
            ):
                record[f"{label}_total"] = h + a
                for market in MARKETS:
                    record[f"{label}_{market}"] = probs[market]

            rows.append(record)
            day_count += 1

        if day_count:
            tested_days += 1

        print(
            f"{day}: {day_count} predictions; "
            f"{len(prior)} prior xG matches",
            flush=True,
        )

    if not rows:
        raise RuntimeError("No eligible evaluation fixtures")

    print(
        f"RIDGE VS QUASI-POISSON: "
        f"{len(rows)} fixtures across {tested_days} match dates"
    )
    print(
        "All training and benchmark rates use strictly earlier dates."
    )

    for label in ("ridge", "quasipoisson", "baseline"):
        evaluate(rows, label)

    actual_mean = np.mean([
        r["actual_total"] for r in rows
    ])
    print(f"Actual mean total goals={actual_mean:.3f}")
    print(
        "Research only. No predictive calibration or betting "
        "edge established."
    )


if __name__ == "__main__":
    main()
