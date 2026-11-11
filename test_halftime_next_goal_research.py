"""Tests for explicitly labelled historical next-goal selection."""
import unittest
from halftime_next_goal_research import trailing_first_summary

class NextGoalResearchTests(unittest.TestCase):
    def test_filters_and_missing(self):
        rows=[
            dict(home_ht_goals=0,away_ht_goals=1,home_ht_xg=.3,away_ht_xg=.1,trailing_side="home",trailing_team_scored_first=True),
            dict(home_ht_goals=1,away_ht_goals=0,home_ht_xg=.2,away_ht_xg=.4,trailing_side="away",trailing_team_scored_first=False),
            dict(home_ht_goals=0,away_ht_goals=1,home_ht_xg=.5,away_ht_xg=.2,trailing_side="home",trailing_team_scored_first=None),
            dict(home_ht_goals=0,away_ht_goals=2,home_ht_xg=.5,away_ht_xg=.2,trailing_side="home",trailing_team_scored_first=True),
            dict(home_ht_goals=1,away_ht_goals=0,home_ht_xg=.2,away_ht_xg=.0,trailing_side="home",trailing_team_scored_first=True)]
        r=trailing_first_summary(rows)
        self.assertEqual((r["n"],r["hits"],r["rate"]),(2,1,.5))
        self.assertEqual(trailing_first_summary(rows,side="home")["n"],1)
        self.assertEqual(trailing_first_summary(rows,deficit=2)["n"],1)
        self.assertEqual(trailing_first_summary(rows,min_xg=.45)["n"],0)
    def test_invalid(self):
        with self.assertRaises(ValueError):
            trailing_first_summary([],side="neutral")
if __name__=="__main__":unittest.main()
