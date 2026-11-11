"""Tests for explicitly labelled historical next-goal selection."""
import unittest
from halftime_next_goal_research import trailing_first_summary,trailing_three_way_summary,trailing_three_way_holdout,three_way_holdout_scores

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
    def test_three_way_includes_no_goal(self):
        rows=[
            dict(home_ht_goals=0,away_ht_goals=1,home_ht_xg=.3,away_ht_xg=.1,trailing_side="home",trailing_team_scored_first=True),
            dict(home_ht_goals=1,away_ht_goals=0,home_ht_xg=.1,away_ht_xg=.4,trailing_side="away",trailing_team_scored_first=False),
            dict(home_ht_goals=0,away_ht_goals=1,home_ht_xg=.5,away_ht_xg=.2,trailing_side="home",trailing_team_scored_first=None)]
        result=trailing_three_way_summary(rows)
        self.assertEqual((result["n"],result["trailing_first"],result["leader_first"],result["no_goal"]),(3,1,1,1))
        self.assertAlmostEqual(result["trailing_rate"]+result["leader_rate"]+result["no_goal_rate"],1)
    def test_holdout_keeps_dates_together(self):
        rows=[
            dict(match_date="2025-01-01",home_ht_goals=0,away_ht_goals=1,home_ht_xg=.3,away_ht_xg=.2,trailing_side="home",trailing_team_scored_first=True),
            dict(match_date="2025-01-01",home_ht_goals=0,away_ht_goals=1,home_ht_xg=.3,away_ht_xg=.2,trailing_side="home",trailing_team_scored_first=None),
            dict(match_date="2025-02-01",home_ht_goals=0,away_ht_goals=1,home_ht_xg=.3,away_ht_xg=.2,trailing_side="home",trailing_team_scored_first=False),
            dict(match_date="2025-03-01",home_ht_goals=0,away_ht_goals=1,home_ht_xg=.3,away_ht_xg=.2,trailing_side="home",trailing_team_scored_first=True)]
        result=trailing_three_way_holdout(rows,train_fraction=.5)
        self.assertEqual(result["cutoff"],"2025-02-01")
        self.assertEqual(result["train"]["n"],2)
        self.assertEqual(result["later"]["n"],2)
        self.assertEqual(result["train"]["no_goal"],1)
    def test_holdout_rejects_single_date(self):
        self.assertEqual(trailing_three_way_holdout([{"match_date":"2025-01-01"}])["status"],"Insufficient distinct match dates")
        with self.assertRaises(ValueError):
            trailing_three_way_holdout([],train_fraction=1)
    def test_probability_quality_chronological(self):
        rows=[]
        for i in range(40):
            for month in (1,2):
                rows.append(dict(match_date=f"2025-{month:02d}-{i%28+1:02d}",
                    home_ht_goals=0,away_ht_goals=1,home_ht_xg=.4,away_ht_xg=.2,
                    trailing_side="home",trailing_team_scored_first=[True,False,None][i%3]))
        score=three_way_holdout_scores(rows,train_fraction=.5)
        self.assertEqual(score["status"],"ok")
        self.assertEqual(score["train_n"],40)
        self.assertEqual(score["later_n"],40)
        self.assertAlmostEqual(sum(score["earlier_probabilities"].values()),1.0)
        self.assertGreater(score["brier"],0)
        self.assertGreater(score["log_loss"],0)
    def test_probability_quality_small_sample(self):
        self.assertEqual(three_way_holdout_scores([])["status"],"Insufficient distinct match dates")
    def test_invalid(self):
        with self.assertRaises(ValueError):
            trailing_first_summary([],side="neutral")
if __name__=="__main__":unittest.main()
