"""Offline leakage and missing-data checks for team strength rating."""
import unittest
from research.team_strength import score_team, rolling_fixture_ratings

def game(day, home, away, hg=1, ag=0, xh=1.4, xa=0.7):
    return {"match_id": str(day)+home+away, "match_date": "2026-01-%02d" % day,
            "competition_id": "league", "home_team": home, "away_team": away,
            "home_goals": hg, "away_goals": ag, "home_xg": xh, "away_xg": xa}

class TeamStrengthTests(unittest.TestCase):
    def test_missing_shots_and_corners_are_not_assumed_zero(self):
        rows = [{"venue": "home", "points": 3, "goal_diff": 1, "xg_diff": 0.7,
                 "shots_diff": None, "corners_diff": None} for _ in range(10)]
        rating = score_team(rows, "home")
        self.assertEqual(rating["available_weight"], 75)
        self.assertIsNone(rating["components"]["corners"])
        self.assertIsNone(rating["components"]["shots_on_target"])

    def test_ten_game_minimum(self):
        self.assertIsNone(score_team([], "away"))
        self.assertIsNone(score_team([{"points": 3}] * 9, "away"))

    def test_no_future_leakage_or_same_day_leakage(self):
        matches = []
        for day in range(1, 12):
            matches += [game(day, "A", "B"), game(day, "C", "D")]
        original = list(rolling_fixture_ratings(matches))
        self.assertEqual(len(original), 2)
        changed = matches + [game(12, "A", "B", 0, 8), game(12, "C", "D", 0, 8)]
        self.assertEqual(list(rolling_fixture_ratings(changed))[:2], original)

    def test_venue_only_applies_to_venue_component(self):
        rows = [{"venue": "away" if i % 2 else "home", "points": 3 if i % 2 else 0,
                 "goal_diff": 0, "xg_diff": 0, "shots_diff": None,
                 "corners_diff": None} for i in range(10)]
        home = score_team(rows, "home")
        away = score_team(rows, "away")
        self.assertLess(home["rating"], away["rating"])

if __name__ == "__main__":
    unittest.main()
