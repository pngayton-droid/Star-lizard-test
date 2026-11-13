"""Smoke-test the actual Streamlit script with in-memory database fixtures.

Never connects to Supabase or TheStatsAPI. The production entry point is tested
rather than a duplicate implementation. Run with python -m unittest discover.
"""
import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest


class _Response:
    def __init__(self, rows, count=None):
        self.data = rows
        self.count = len(rows) if count is None else count


class _Query:
    def __init__(self, table, rows):
        self.table, self.rows = table, rows
        self._limit = None
        self._range = None

    def select(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, limit):
        self._limit = limit
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def execute(self):
        rows = self.rows.get(self.table, [])
        count = len(rows)
        if self._range is not None:
            start, end = self._range
            rows = rows[start:end+1]
        if self._limit is not None:
            rows = rows[:self._limit]
        return _Response(rows, count)


class _Database:
    def __init__(self, rows):
        self.rows = rows

    def table(self, name):
        return _Query(name, self.rows)


class DashboardSmokeTests(unittest.TestCase):
    def test_dashboard_renders_without_external_services(self):
        fixtures = {
            "historical_xg": [{
                "match_id": "m1", "competition_id": "comp_3039",
                "match_date": "2026-01-01",
                "home_ht_goals": 1, "away_ht_goals": 0,
                "home_goals": 2, "away_goals": 1,
                "home_ht_xg": 0.8, "away_ht_xg": 0.3,
                "home_xg": 1.5, "away_xg": 0.7,
            }, {
                "match_id": "m2", "competition_id": "comp_3039",
                "match_date": None,
                "home_ht_goals": None, "away_ht_goals": None,
                "home_goals": None, "away_goals": None,
                "home_ht_xg": None, "away_ht_xg": None,
                "home_xg": None, "away_xg": None,
            }],
            "historical_match_odds": [{"match_id": "m1", "odds_payload": {}}],
            "historical_match_events": [{"match_id": "m1"}],
        }
        with patch("supabase.create_client", return_value=_Database(fixtures)):
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "starlizard_2.py"), default_timeout=30)
            app.secrets["SUPABASE_URL"] = "https://example.supabase.co"
            app.secrets["SUPABASE_SECRET_KEY"] = "fake-local-test-key"
            app.run()
            self.assertFalse(app.exception, [str(x.message) for x in app.exception])
            for label in ("Run read-only coverage audit", "Load stored halftime outcomes", "Audit stored Bet365 odds", "Search for stable patterns", "Evaluate model on later matches", "Audit match integrity"):
                next(x for x in app.button if x.label == label).click().run()
                self.assertFalse(app.exception, [str(x.message) for x in app.exception])
            metrics = {m.label: m.value for m in app.metric}
            self.assertEqual(metrics["Stored match rows"], "2")
            self.assertEqual(metrics["Incomplete score rows"], "1")
            self.assertEqual(metrics["Missing match dates"], "1")
            self.assertEqual(metrics["Missing halftime xG pairs"], "1")
            self.assertEqual(metrics["Negative or fractional scores"], "0")
        self.assertFalse(app.exception, [str(x.message) for x in app.exception])
        self.assertTrue(any("PRO STARLIZARD" in x.value for x in app.title))


if __name__ == "__main__":
    unittest.main()
