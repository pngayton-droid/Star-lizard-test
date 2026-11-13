"""Conservative validation of stored TheStatsAPI goal timelines.

Use only after matching event team names to the stored home/away teams.
Reject rather than silently repair ambiguous VAR, own-goal or duplicate data.
"""
GOAL_TYPES = {"goal", "own_goal"}


def validated_goal_sequence(timeline, home_name, away_name, ht_home, ht_away, ft_home, ft_away):
    """Return ordered goals with side and half, or (None, reason)."""
    if not isinstance(timeline, dict) or not isinstance(timeline.get("events"), list):
        return None, "missing_events"
    if not home_name or not away_name or home_name == away_name:
        return None, "ambiguous_teams"
    goals = []
    previous_sequence = -1
    previous_half = 1
    previous_minute = 0
    for event in timeline["events"]:
        if not isinstance(event, dict):
            return None, "malformed_event"
        sequence = event.get("sequence")
        if not isinstance(sequence, int) or sequence <= previous_sequence:
            return None, "invalid_sequence"
        previous_sequence = sequence
        period_value = event.get("period")
        if period_value in ("first_half", "second_half"):
            half_value = 1 if period_value == "first_half" else 2
            minute_value = event.get("minute")
            if half_value < previous_half:
                return None, "reversed_period"
            if isinstance(minute_value, int) and minute_value < previous_minute:
                return None, "reversed_minutes"
            previous_half = half_value
            if isinstance(minute_value, int):
                previous_minute = minute_value
        if event.get("type") not in GOAL_TYPES:
            continue
        if event.get("type") == "own_goal":
            return None, "own_goal_requires_manual_review"
        period = event.get("period")
        if period not in ("first_half", "second_half"):
            return None, "invalid_goal_period"
        minute = event.get("minute")
        if not isinstance(minute, int) or minute < 1 or minute > 130:
            return None, "invalid_goal_minute"
        team = event.get("team")
        team_name = team.get("name") if isinstance(team, dict) else None
        if team_name == home_name:
            side = "home"
        elif team_name == away_name:
            side = "away"
        else:
            return None, "unmatched_goal_team"
        goals.append({"side": side, "half": 1 if period == "first_half" else 2,
                      "minute": minute, "sequence": sequence})
    actual = (
        sum(g["side"] == "home" and g["half"] == 1 for g in goals),
        sum(g["side"] == "away" and g["half"] == 1 for g in goals),
        sum(g["side"] == "home" for g in goals),
        sum(g["side"] == "away" for g in goals),
    )
    if actual != (ht_home, ht_away, ft_home, ft_away):
        return None, "score_mismatch"
    return goals, None


def first_second_half_goal(goals):
    """Return 'home', 'away', or 'none' for verified ordered goals."""
    for goal in goals:
        if goal["half"] == 2:
            return goal["side"]
    return "none"
