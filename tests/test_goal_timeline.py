"""Offline verification of timeline anomaly exclusions and first 2H scorer."""
import unittest
from research.goal_timeline import validated_goal_sequence, first_second_half_goal


def event(seq, kind, period, team=None, minute=10):
    return {"sequence": seq, "type": kind, "period": period,
            "minute": minute, "team": {"name": team} if team else None}


class TimelineTests(unittest.TestCase):
    def test_first_second_half_scorer(self):
        events = [event(1, "period_start", "first_half"),
                  event(2, "goal", "first_half", "Home", 20),
                  event(3, "period_start", "second_half", minute=46),
                  event(4, "goal", "second_half", "Away", 60),
                  event(5, "goal", "second_half", "Home", 75)]
        goals, reason = validated_goal_sequence({"events": events}, "Home", "Away", 1, 0, 2, 1)
        self.assertIsNone(reason)
        self.assertEqual(first_second_half_goal(goals), "away")

    def test_reject_var_duplicate_goal(self):
        goals, reason = validated_goal_sequence(
            {"events": [event(1, "goal", "first_half", "Home"),
                        event(2, "goal", "first_half", "Home")]},
            "Home", "Away", 1, 0, 1, 0)
        self.assertIsNone(goals)
        self.assertEqual(reason, "score_mismatch")

    def test_reject_own_goal(self):
        goals, reason = validated_goal_sequence(
            {"events": [event(1, "own_goal", "second_half", "Away")]},
            "Home", "Away", 0, 0, 1, 0)
        self.assertIsNone(goals)
        self.assertEqual(reason, "own_goal_requires_manual_review")

    def test_reject_unmatched_team(self):
        goals, reason = validated_goal_sequence(
            {"events": [event(1, "goal", "second_half", "Other")]},
            "Home", "Away", 0, 0, 1, 0)
        self.assertIsNone(goals)
        self.assertEqual(reason, "unmatched_goal_team")

    def test_reject_duplicate_sequence(self):
        goals, reason = validated_goal_sequence(
            {"events": [event(1, "foul", "first_half"),
                        event(1, "goal", "second_half", "Away")]},
            "Home", "Away", 0, 0, 0, 1)
        self.assertIsNone(goals)
        self.assertEqual(reason, "invalid_sequence")

    def test_reject_reversed_minutes(self):
        goals, reason = validated_goal_sequence(
            {"events": [event(1, "foul", "first_half", minute=30),
                        event(2, "goal", "first_half", "Home", minute=20)]},
            "Home", "Away", 1, 0, 1, 0)
        self.assertIsNone(goals)
        self.assertEqual(reason, "reversed_minutes")

    def test_reject_reversed_period(self):
        goals, reason = validated_goal_sequence(
            {"events": [event(1, "period_start", "second_half", minute=46),
                        event(2, "goal", "first_half", "Home", minute=47)]},
            "Home", "Away", 1, 0, 1, 0)
        self.assertIsNone(goals)
        self.assertEqual(reason, "reversed_period")

    def test_no_second_half_goal(self):
        goals, reason = validated_goal_sequence(
            {"events": [event(1, "goal", "first_half", "Home")]},
            "Home", "Away", 1, 0, 1, 0)
        self.assertIsNone(reason)
        self.assertEqual(first_second_half_goal(goals), "none")


if __name__ == "__main__":
    unittest.main()
