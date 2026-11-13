"""Offline checks for incremental collector; never calls real API or Supabase."""
import os
import runpy
import sys
import types
import unittest
from unittest.mock import patch

SCRIPT = "scripts/collect_recent_finished_fixtures.py"

class FixtureCollectorTests(unittest.TestCase):
    def test_default_dry_run_never_creates_clients(self):
        fake_requests = types.ModuleType("requests")
        fake_requests.Session = lambda: self.fail("HTTP session must not be created")
        fake_supabase = types.ModuleType("supabase")
        fake_supabase.create_client = lambda *a: self.fail("DB client must not be created")
        with patch.dict(sys.modules, {"requests": fake_requests, "supabase": fake_supabase}):
            with patch.dict(os.environ, {"ENABLE_LIVE_FIXTURE_COLLECTION": "0"}, clear=True):
                with self.assertRaises(SystemExit) as caught:
                    runpy.run_path(SCRIPT, run_name="__main__")
        self.assertEqual(caught.exception.code, 0)

    def test_live_requires_secrets(self):
        fake_requests = types.ModuleType("requests")
        fake_supabase = types.ModuleType("supabase")
        with patch.dict(sys.modules, {"requests": fake_requests, "supabase": fake_supabase}):
            with patch.dict(os.environ, {"ENABLE_LIVE_FIXTURE_COLLECTION": "1"}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "Missing required secrets"):
                    runpy.run_path(SCRIPT, run_name="__main__")

    def test_request_budget_rejects_undersized_configuration(self):
        fake_requests = types.ModuleType("requests")
        fake_supabase = types.ModuleType("supabase")
        with patch.dict(sys.modules, {"requests": fake_requests, "supabase": fake_supabase}):
            with patch.dict(os.environ, {"ENABLE_LIVE_FIXTURE_COLLECTION": "0", "LIVE_FIXTURE_MAX_REQUESTS": "3"}, clear=True):
                with self.assertRaisesRegex(ValueError, "must allow"):
                    runpy.run_path(SCRIPT, run_name="__main__")

if __name__ == "__main__":
    unittest.main()
