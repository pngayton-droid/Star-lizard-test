"""Tests for historical fixture input provenance guard."""
import unittest
from fixture_input_audit import baseline_input_audit

class FixtureInputAuditTests(unittest.TestCase):
    def setUp(self):
        self.fixture={"competition_id":"10","home_team":{"name":"Home"},"away_team":{"name":"Away"}}
        self.rows=[
            {"competition_id":"10","team_name":"Home","venue":"home","sample_n":10,"last_match_date":"2026-10-31"},
            {"competition_id":"10","team_name":"Away","venue":"away","sample_n":9,"last_match_date":"2026-11-01"}]
    def test_pre_fixture(self):
        result=baseline_input_audit(self.fixture,self.rows,"2026-11-11")
        self.assertTrue(result["eligible_for_current_pricing"])
        self.assertFalse(result["point_in_time_verified"])
    def test_same_day_rejected(self):
        self.rows[0]["last_match_date"]="2026-11-11"
        result=baseline_input_audit(self.fixture,self.rows,"2026-11-11")
        self.assertFalse(result["eligible_for_current_pricing"])
        self.assertTrue(result["sources"]["home"]["known_future_observations"])
    def test_missing_team(self):
        result=baseline_input_audit(self.fixture,self.rows[:1],"2026-11-11")
        self.assertFalse(result["eligible_for_current_pricing"])
    def test_low_sample(self):
        self.rows[0]["sample_n"]=3
        self.assertFalse(baseline_input_audit(self.fixture,self.rows,"2026-11-11")["eligible_for_current_pricing"])

if __name__=="__main__":unittest.main()
