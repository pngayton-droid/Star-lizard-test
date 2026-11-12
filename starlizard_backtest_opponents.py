"""Causal, sequential opponent-strength adjustment for historical odds testing.

Uses the same prior-weight (8), minimum opponent matches (5), and
factor cap (0.75..1.33) as starlizard_opponent_adjustment.py.
Only matches strictly before each match date contribute to factors.
"""
from collections import defaultdict

class OpponentHistory:
    def __init__(self):
        self.league = defaultdict(lambda: [0, 0.0])
        self.team = defaultdict(lambda: [0, 0.0, 0.0])

    def factors(self, league, opponent):
        count, sum_xg = self.league[league]
        n, xgf, xga = self.team[(league, opponent)]
        if count < 40 or n < 5 or sum_xg <= 0:
            return 1.0, 1.0, False
        avg = sum_xg / (2 * count)
        opp_for = (xgf + 8 * avg) / (n + 8)
        opp_against = (xga + 8 * avg) / (n + 8)
        attack = max(.75, min(1.33, avg / max(.2, opp_against)))
        defence = max(.75, min(1.33, avg / max(.2, opp_for)))
        return attack, defence, True

    def record(self, league, home, away, home_xg, away_xg):
        self.league[league][0] += 1
        self.league[league][1] += home_xg + away_xg
        for team, xgf, xga in ((home, home_xg, away_xg), (away, away_xg, home_xg)):
            agg = self.team[(league, team)]
            agg[0] += 1
            agg[1] += xgf
            agg[2] += xga
