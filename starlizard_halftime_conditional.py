"""Experimental half-time conditional goal model; uncalibrated research only."""
from math import exp, factorial


def half_time_rates(prematch_home, prematch_away, ht_home_xg, ht_away_xg):
    """Blend 50% pre-match second-half goal expectation with first-half xG.

    The 0.55 second-half share and 0.25 xG response are explicit
    heuristic assumptions, not empirically fitted coefficients.
    """
    if min(prematch_home, prematch_away, ht_home_xg, ht_away_xg) < 0:
        raise ValueError("Rates must be non-negative")
    base_h = 0.55 * prematch_home
    base_a = 0.55 * prematch_away
    # First-half performance relative to half the pre-match expectation.
    deviation_h = ht_home_xg - 0.5 * prematch_home
    deviation_a = ht_away_xg - 0.5 * prematch_away
    h = max(0.08, min(3.5, base_h * exp(0.25 * deviation_h)))
    a = max(0.08, min(3.5, base_a * exp(0.25 * deviation_a)))
    return h, a


def halftime_markets(ht_home, ht_away, second_home, second_away):
    """Enumerate second-half outcomes, preserving the halftime score."""
    def pmf(rate):
        values = [exp(-rate) * rate ** k / factorial(k) for k in range(12)]
        values.append(max(0.0, 1 - sum(values)))
        return values

    h, a = pmf(second_home), pmf(second_away)
    p = {
        "Home win FT": 0.0, "Draw FT": 0.0, "Away win FT": 0.0,
        "Over 0.5 second-half goals": 1 - exp(-(second_home + second_away)),
        "Over 1.5 second-half goals": 1 - exp(-(second_home + second_away)) * (1 + second_home + second_away),
        "Over 2.5 second-half goals": 1 - exp(-(second_home + second_away)) * (1 + second_home + second_away + (second_home + second_away)**2/2),
        "Home next goal (including no goal)": (second_home / (second_home + second_away)) * (1 - exp(-(second_home + second_away))),
        "Away next goal (including no goal)": (second_away / (second_home + second_away)) * (1 - exp(-(second_home + second_away))),
        "No second-half goal": exp(-(second_home + second_away)),
    }
    for i, hp in enumerate(h):
        for j, ap in enumerate(a):
            weight = hp * ap
            if ht_home + i > ht_away + j:
                p["Home win FT"] += weight
            elif ht_home + i == ht_away + j:
                p["Draw FT"] += weight
            else:
                p["Away win FT"] += weight
    return p
