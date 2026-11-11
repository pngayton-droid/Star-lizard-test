"""Regression tests for historical venue forensic dossier."""
import unittest
from fixture_forensic_dossier import venue_dossier

class VenueDossierTests(unittest.TestCase):
    def setUp(self):
        self.fixture={"competition_id":"10","home_team":{"name":"Home FC"},"away_team":{"name":"Away FC"}}
        self.rows=[
            {"competition_id":"10","team_name":"Home FC","venue":"home","sample_n":12,
             "xg_for_avg":1.7,"xg_against_avg":.9,"last_match_date":"2026-11-01"},
            {"competition_id":"10","team_name":"Away FC","venue":"away","sample_n":11,
             "xg_for_avg":1.1,"xg_against_avg":1.5,"last_match_date":"2026-10-30"}]
    def test_complete_dossier(self):
        r=venue_dossier(self.fixture,self.rows,"2026-11-11")
        self.assertEqual(r["status"],"ready")
        self.assertEqual(r["teams"]["home"]["matches"],12)
        self.assertAlmostEqual(r["teams"]["away"]["xg_difference"],-.4)
        self.assertEqual(r["warnings"],[])
    def test_stale_data_warns(self):
        self.rows[0]["last_match_date"]="2026-01-01"
        r=venue_dossier(self.fixture,self.rows,"2026-11-11")
        self.assertEqual(r["status"],"caution")
        self.assertTrue(any("90 days" in x for x in r["warnings"]))
    def test_unresolved_team(self):
        r=venue_dossier(self.fixture,self.rows[:1],"2026-11-11")
        self.assertEqual(r["status"],"unavailable")
        self.assertEqual(len(r["warnings"]),1)

if __name__=="__main__":unittest.main()
