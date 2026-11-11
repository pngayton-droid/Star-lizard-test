"""Experimental opponent-strength xG adjustments using strictly prior league matches.

For each historical observation, estimate opponent attack/defence from
matches dated strictly before that observation. No future match outcomes.
This is not a calibrated model.
"""
import pandas as pd


def adjust_venue_rows(frame, league_history, prior_weight=8, minimum=5):
    """Return adjusted xGF/xGA dataframe and adjustment coverage.

    league_history rows: Date, home_team, away_team, home_xg, away_xg.
    Opponent defensive xGA below league average means the opponent was
    tougher: attacking xG is multiplied upward. Opponent attacking xGF
    above league average means stronger attack: xGA multiplied downward.
    """
    adjusted = frame.copy()
    adjusted["xGF"] = pd.to_numeric(adjusted["xGF"], errors="coerce")
    adjusted["xGA"] = pd.to_numeric(adjusted["xGA"], errors="coerce")
    used = 0
    eligible = 0
    if not league_history:
        return adjusted, used, eligible
    hist = pd.DataFrame(league_history)
    hist["home_xg"] = pd.to_numeric(hist["home_xg"], errors="coerce")
    hist["away_xg"] = pd.to_numeric(hist["away_xg"], errors="coerce")
    hist = hist.dropna(subset=["home_xg", "away_xg", "match_date"])
    hist = hist[
        hist["home_xg"].between(0, 12) & hist["away_xg"].between(0, 12)
    ]
    for idx, row in adjusted.iterrows():
        opponent, date = row.get("Opponent"), row.get("Date")
        if not opponent or not date:
            continue
        eligible += 1
        earlier = hist[hist["match_date"] < str(date)]
        if len(earlier) < 40:
            continue
        league_mean = (earlier["home_xg"].sum() + earlier["away_xg"].sum()) / (2 * len(earlier))
        if league_mean <= 0:
            continue
        home = earlier[earlier["home_team"] == opponent]
        away = earlier[earlier["away_team"] == opponent]
        n = len(home) + len(away)
        if n < minimum:
            continue
        opp_for = (home["home_xg"].sum() + away["away_xg"].sum()) / n
        opp_against = (home["away_xg"].sum() + away["home_xg"].sum()) / n
        opp_for = (opp_for * n + league_mean * prior_weight) / (n + prior_weight)
        opp_against = (opp_against * n + league_mean * prior_weight) / (n + prior_weight)
        # Cap adjustments to avoid excessive influence from sparse data.
        attack_factor = max(0.75, min(1.33, league_mean / max(0.2, opp_against)))
        defence_factor = max(0.75, min(1.33, league_mean / max(0.2, opp_for)))
        if pd.notna(row["xGF"]):
            adjusted.at[idx, "xGF"] = row["xGF"] * attack_factor
        if pd.notna(row["xGA"]):
            adjusted.at[idx, "xGA"] = row["xGA"] * defence_factor
        used += 1
    return adjusted, used, eligible
