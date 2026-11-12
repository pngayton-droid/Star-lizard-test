"""Historical, strictly past-only venue baselines for the pricing benchmark."""
from collections import defaultdict

class VenueBaseline:
    def __init__(self):
        self.by_league = defaultdict(lambda: [0, 0., 0.])
        self.global_totals = [0, 0., 0.]

    def get(self, league, prior=1.35, strength=80, minimum=40):
        n, home_sum, away_sum = self.by_league[league]
        if n < minimum:
            return prior, prior
        gn, gh, ga = self.global_totals
        # Pool toward globally observed venue-specific xG, never toward future data.
        home_prior = gh / gn if gn >= minimum else prior
        away_prior = ga / gn if gn >= minimum else prior
        return ((home_sum + strength * home_prior) / (n + strength),
                (away_sum + strength * away_prior) / (n + strength))

    def record(self, league, home_xg, away_xg):
        for bucket in (self.by_league[league], self.global_totals):
            bucket[0] += 1
            bucket[1] += home_xg
            bucket[2] += away_xg
