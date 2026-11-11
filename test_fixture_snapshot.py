"""Deterministic fixture snapshot schema checks."""
import json
import unittest
from fixture_snapshot import build_snapshot,snapshot_json,SCHEMA_VERSION

class FixtureSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.baseline={"home_xg":1.5,"away_xg":1.1,"home_n":10,"away_n":9,
                       "home_last":"2026-11-01","away_last":"2026-10-31"}
    def test_complete_export(self):
        record=build_snapshot("Home v Away","2026-11-11","3039",self.baseline,
                              {"status":"ready"},{"probabilities":{"draw":.3}},
                              {"rows":[]},{"source":"manual_user_entry","decimal_odds":2.5})
        decoded=json.loads(snapshot_json(record))
        self.assertEqual(decoded["schema_version"],SCHEMA_VERSION)
        self.assertEqual(decoded["fixture"]["competition_id"],"3039")
        self.assertEqual(decoded["observed_quote"]["decimal_odds"],2.5)
        self.assertFalse(decoded["model"]["calibrated"])
        self.assertIn("generated_at_utc",decoded)
    def test_missing_inputs(self):
        with self.assertRaises(ValueError):
            build_snapshot("a","2026-11-11","1",{}, {}, {}, {})
    def test_nan_rejected(self):
        with self.assertRaises(ValueError):
            snapshot_json({"bad":float("nan")})

if __name__=="__main__":unittest.main()
