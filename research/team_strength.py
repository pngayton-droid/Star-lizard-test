"""Leakage-safe rolling team-strength scores from existing match records.

Score components are descriptive and exploratory, NOT calibrated win probabilities.
Only games strictly earlier than the fixture date are eligible.
"""
from collections import defaultdict
from datetime import date

WEIGHTS = {"results": 15, "venue": 15, "goals": 15, "xg": 25,
           "shots_on_target": 15, "corners": 10, "trend": 5}

def _number(value):
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None

def _scale(value, low, high):
    return max(0.0, min(1.0, (value - low) / (high - low)))

def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None

def _team_row(match, side):
    other = "away" if side == "home" else "home"
    goals = _number(match.get(side + "_goals"))
    conceded = _number(match.get(other + "_goals"))
    xg = _number(match.get(side + "_xg"))
    xga = _number(match.get(other + "_xg"))
    if goals is None or conceded is None:
        return None
    return {
        "date": str(match["match_date"]), "venue": side,
        "points": 3 if goals > conceded else 1 if goals == conceded else 0,
        "goal_diff": goals - conceded,
        "xg_diff": xg - xga if xg is not None and xga is not None else None,
        "shots_diff": _difference(match, side, other, "shots_on_target"),
        "corners_diff": _difference(match, side, other, "corners"),
    }

def _difference(match, side, other, suffix):
    a, b = _number(match.get(side + "_" + suffix)), _number(match.get(other + "_" + suffix))
    return a - b if a is not None and b is not None else None

def score_team(history, venue, window=10):
    """History is chronological team-perspective records; exclude fixture itself."""
    if window < 2:
        raise ValueError("window must be >= 2")
    games = history[-window:]
    if len(games) < window:
        return None
    venue_games = [g for g in games if g["venue"] == venue]
    first, last = games[:window//2], games[window//2:]
    components = {
        "results": _scale(_mean([g["points"] for g in games]), 0, 3),
        "venue": _scale(_mean([g["points"] for g in venue_games]), 0, 3) if venue_games else None,
        "goals": _scale(_mean([g["goal_diff"] for g in games]), -2, 2),
        "xg": _scale(_mean([g["xg_diff"] for g in games]), -2, 2) if all(g["xg_diff"] is not None for g in games) else None,
        "shots_on_target": _scale(_mean([g["shots_diff"] for g in games]), -5, 5) if all(g["shots_diff"] is not None for g in games) else None,
        "corners": _scale(_mean([g["corners_diff"] for g in games]), -6, 6) if all(g["corners_diff"] is not None for g in games) else None,
        "trend": _scale(_mean([g["points"] for g in last]) - _mean([g["points"] for g in first]), -2, 2),
    }
    available = sum(WEIGHTS[k] for k, v in components.items() if v is not None)
    if available == 0:
        return None
    return {"rating": round(100 * sum(WEIGHTS[k]*v for k,v in components.items() if v is not None)/available, 2),
            "available_weight": available, "components": components, "games": len(games),
            "venue_games": len(venue_games)}

def rolling_fixture_ratings(matches, window=10):
    """Yield paired scores for fixtures, without current/future-match leakage.

    Same-day fixtures are scored before ANY results from that day enter history.
    Team names are keyed by competition to prevent cross-league collisions.
    """
    histories = defaultdict(list)
    matches = sorted(matches, key=lambda m: (str(m["match_date"]), str(m.get("match_id", ""))))
    i = 0
    while i < len(matches):
        j = i + 1
        while j < len(matches) and str(matches[j]["match_date"]) == str(matches[i]["match_date"]):
            j += 1
        for match in matches[i:j]:
            league = match.get("competition_id")
            home_key = (league, match.get("home_team"))
            away_key = (league, match.get("away_team"))
            if not league or not home_key[1] or not away_key[1] or home_key == away_key:
                continue
            home = score_team(histories[home_key], "home", window)
            away = score_team(histories[away_key], "away", window)
            if home and away:
                yield {"match_id": match.get("match_id"), "match_date": str(match["match_date"]),
                       "competition_id": league, "home_team": home_key[1], "away_team": away_key[1],
                       "home_rating": home["rating"], "away_rating": away["rating"],
                       "rating_gap": round(home["rating"] - away["rating"], 2),
                       "home_coverage": home["available_weight"], "away_coverage": away["available_weight"],
                       "home_goals": match.get("home_goals"), "away_goals": match.get("away_goals")}
        for match in matches[i:j]:
            league = match.get("competition_id")
            home, away = match.get("home_team"), match.get("away_team")
            if not league or not home or not away or home == away:
                continue
            for side, name in (("home", home), ("away", away)):
                row = _team_row(match, side)
                if row:
                    histories[(league, name)].append(row)
        i = j
