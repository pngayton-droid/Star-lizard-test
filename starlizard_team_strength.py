"""Sequential team attack/defence strength model, using only previous dates.

EWMA log attack and defensive concessions, league-normalised with empirical
shrinkage. Updated after every match-day batch to avoid same-day leakage.
This is a separate benchmark, not a fitted maximum-likelihood Dixon-Coles model.
"""
from collections import defaultdict
import math

class SequentialTeamStrength:
    def __init__(self, half_life=12, prior_games=8):
        self.decay = 0.5 ** (1 / half_life)
        self.prior_games = prior_games
        self.leagues = defaultdict(lambda: [0, 0., 0.])
        self.teams = defaultdict(lambda: [0., 0., 0.]) # effective weight, xGF, xGA

    def predict(self, league, home, away):
        n, home_total, away_total = self.leagues[league]
        if n < 40:
            return None
        league_home = max(.4, home_total / n)
        league_away = max(.4, away_total / n)
        league_avg = (league_home + league_away) / 2
        def strength(team):
            weight, gf, ga = self.teams[(league, team)]
            attack = ((gf + self.prior_games * league_avg) /
                      (weight + self.prior_games)) / league_avg
            weakness = ((ga + self.prior_games * league_avg) /
                        (weight + self.prior_games)) / league_avg
            return attack, weakness
        ha, hd = strength(home)
        aa, ad = strength(away)
        return (max(.15, min(4., league_home * ha * ad)),
                max(.15, min(4., league_away * aa * hd)))

    def record(self, league, home, away, home_xg, away_xg):
        totals = self.leagues[league]
        totals[0] += 1
        totals[1] += home_xg
        totals[2] += away_xg
        for team, gf, ga in ((home, home_xg, away_xg),
                             (away, away_xg, home_xg)):
            old = self.teams[(league, team)]
            old[0] = self.decay * old[0] + 1
            old[1] = self.decay * old[1] + gf
            old[2] = self.decay * old[2] + ga
