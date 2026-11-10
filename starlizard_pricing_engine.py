
"""PRO STARLIZARD — experimental, read-only historical xG pricing engine.

No TheStatsAPI calls. No claims of predictive calibration or betting edge.
Requires: numpy, pandas, supabase-py (Supabase client supplied by caller).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

COLUMNS = "match_id,competition_id,match_date,home_team,away_team,home_xg,away_xg"


def load_historical_xg(db: Any, competition_id: str, before: str, page_size: int = 500) -> pd.DataFrame:
    """Paginate one competition; strictly exclude matches on/after `before`."""
    if not competition_id or not before:
        raise ValueError("competition_id and before are required")
    if not 1 <= page_size <= 1000:
        raise ValueError("page_size must be 1..1000")
    rows = []
    start = 0
    while True:
        result = (db.table("historical_xg").select(COLUMNS)
                  .eq("competition_id", competition_id)
                  .lt("match_date", before)
                  .order("match_date").order("match_id")
                  .range(start, start + page_size - 1).execute())
        batch = result.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return clean_history(pd.DataFrame(rows), competition_id, before)


def clean_history(df: pd.DataFrame, competition_id: str, before: str) -> pd.DataFrame:
    """Validate data without mutating stored records."""
    required = COLUMNS.split(",")
    missing = set(required) - set(df.columns)
    if missing:
        if df.empty:
            return pd.DataFrame(columns=required)
        raise ValueError(f"Missing columns: {sorted(missing)}")
    d = df[required].copy()
    d["match_date"] = pd.to_datetime(d["match_date"], errors="coerce", utc=True)
    cutoff = pd.Timestamp(before)
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    for c in ("home_xg", "away_xg"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    for c in ("home_team", "away_team"):
        d[c] = d[c].astype("string").str.strip()
    d = d.dropna(subset=required)
    d = d[(d.competition_id == competition_id) & (d.match_date < cutoff)]
    d = d[(d.home_team != "") & (d.away_team != "") & (d.home_team != d.away_team)]
    d = d[np.isfinite(d.home_xg) & np.isfinite(d.away_xg)]
    d = d[(d.home_xg >= 0) & (d.away_xg >= 0)]
    return d.drop_duplicates("match_id", keep="last").sort_values(["match_date", "match_id"]).reset_index(drop=True)


@dataclass(frozen=True)
class Ratings:
    teams: tuple[str, ...]
    coefficients: np.ndarray
    matches: int
    competition_id: str
    cutoff: str

    def expected_goals(self, home: str, away: str) -> tuple[float, float]:
        if home == away:
            raise ValueError("Teams must be different")
        index = {team: i for i, team in enumerate(self.teams)}
        if home not in index or away not in index:
            raise ValueError("Both teams must have historical xG in this competition")
        n = len(self.teams)
        h, a = index[home], index[away]
        b = self.coefficients
        home_rate = math.exp(float(b[0] + b[1] + b[2+h] - b[2+n+a])) - 0.15
        away_rate = math.exp(float(b[0] + b[2+a] - b[2+n+h])) - 0.15
        return tuple(float(np.clip(rate, 0.1, 5.0)) for rate in (home_rate, away_rate))


def fit_ratings(history: pd.DataFrame, competition_id: str, before: str,
                half_life_days: float = 180, ridge: float = 10,
                minimum_matches: int = 60) -> Ratings:
    if half_life_days <= 0 or ridge <= 0:
        raise ValueError("half_life_days and ridge must be positive")
    data = clean_history(history, competition_id, before)
    if len(data) < minimum_matches:
        raise ValueError(f"Only {len(data)} valid matches; need at least {minimum_matches}")
    teams = tuple(sorted(set(data.home_team) | set(data.away_team)))
    idx = {team: i for i, team in enumerate(teams)}
    n = len(teams)
    x = np.zeros((2*len(data), 2+2*n))
    y = np.zeros(2*len(data))
    weights = np.zeros(2*len(data))
    cutoff = pd.Timestamp(before)
    cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
    for k, row in enumerate(data.itertuples(index=False)):
        h, a = idx[row.home_team], idx[row.away_team]
        age = max(0.0, (cutoff - row.match_date).total_seconds()/86400)
        weight = 2 ** (-age/half_life_days)
        for offset, attack, defence, is_home, goals in (
            (0, h, a, 1, row.home_xg), (1, a, h, 0, row.away_xg)
        ):
            pos = 2*k+offset
            x[pos, 0] = 1
            x[pos, 1] = is_home
            x[pos, 2+attack] = 1
            x[pos, 2+n+defence] = -1
            y[pos] = math.log(float(goals)+0.15)
            weights[pos] = weight
    sw = np.sqrt(weights)
    wx = x*sw[:, None]
    penalty = np.eye(x.shape[1])*ridge
    penalty[0, 0] = 0.001
    penalty[1, 1] = ridge*2
    beta = np.linalg.solve(wx.T @ wx + penalty, wx.T @ (y*sw))
    return Ratings(teams, beta, len(data), competition_id, before)


def poisson_distribution(rate: float, cap: int = 20) -> np.ndarray:
    if not math.isfinite(rate) or rate < 0 or cap < 1:
        raise ValueError("Invalid rate or cap")
    p = np.zeros(cap+1)
    p[0] = math.exp(-rate)
    for k in range(1, cap+1):
        p[k] = p[k-1]*rate/k
    p[-1] += max(0.0, 1.0-float(p.sum()))
    return p


def score_matrix(home_xg: float, away_xg: float, cap: int = 20) -> np.ndarray:
    return np.outer(poisson_distribution(home_xg, cap), poisson_distribution(away_xg, cap))


def fair_odds(probability: float) -> float | None:
    return 1/probability if probability > 0 else None


def standard_markets(matrix: np.ndarray) -> dict[str, float]:
    h, a = np.indices(matrix.shape)
    home = float(matrix[h>a].sum())
    draw = float(matrix[h==a].sum())
    away = float(matrix[h<a].sum())
    over25 = float(matrix[h+a>=3].sum())
    btts = float(matrix[(h>0)&(a>0)].sum())
    return {"home":home, "draw":draw, "away":away,
            "over_2_5":over25, "under_2_5":1-over25,
            "btts_yes":btts, "btts_no":1-btts}


def asian_settlement(difference: int, line: float) -> float:
    quarter = round(line*4)
    if not math.isclose(line*4, quarter, abs_tol=1e-8):
        raise ValueError("Asian line must be in quarter-goal increments")
    if quarter % 2:
        lower = math.floor(line*2)/2
        return (asian_settlement(difference, lower) +
                asian_settlement(difference, lower+0.5))/2
    value = difference+line
    return 1.0 if value > 1e-9 else (-1.0 if value < -1e-9 else 0.0)


def asian_market(matrix: np.ndarray, market: str, line: float) -> dict[str, Any]:
    if market not in ("home_handicap", "away_handicap", "over_goals", "under_goals"):
        raise ValueError("Unknown Asian market")
    outcomes = {1.0:0.0, 0.5:0.0, 0.0:0.0, -0.5:0.0, -1.0:0.0}
    for h in range(matrix.shape[0]):
        for a in range(matrix.shape[1]):
            diff = {"home_handicap":h-a, "away_handicap":a-h,
                    "over_goals":h+a, "under_goals":-h-a}[market]
            effective_line = -line if market == "over_goals" else line
            settlement = asian_settlement(diff, effective_line)
            outcomes[settlement] += float(matrix[h, a])
    win_units = outcomes[1.0]+0.5*outcomes[0.5]
    loss_units = outcomes[-1.0]+0.5*outcomes[-0.5]
    return {"fair_odds":1+loss_units/win_units if win_units else None,
            "outcomes":outcomes, "win_units":win_units, "loss_units":loss_units}


def price_fixture(ratings: Ratings, home: str, away: str) -> dict[str, Any]:
    hxg, axg = ratings.expected_goals(home, away)
    matrix = score_matrix(hxg, axg)
    probabilities = standard_markets(matrix)
    scores = {f"{h}-{a}":float(matrix[h,a]) for h in range(8) for a in range(8)}
    return {"home":home, "away":away, "home_xg":hxg, "away_xg":axg,
            "probabilities":probabilities,
            "fair_odds":{k:fair_odds(v) for k,v in probabilities.items()},
            "correct_scores":scores,
            "correct_score_fair_odds":{k:fair_odds(v) for k,v in scores.items()},
            "matrix":matrix, "training_matches":ratings.matches,
            "competition_id":ratings.competition_id, "training_cutoff":ratings.cutoff}
