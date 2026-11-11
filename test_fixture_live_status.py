"""Live status classification does not infer match state from clock time."""
import unittest
from fixture_live_status import fixture_status,live_fixture_rows

class LiveFixtureStatusTests(unittest.TestCase):
    def test_live_statuses(self):
        for status in ("LIVE","in_progress","1H","HT","2H","extra_time"):
            self.assertEqual(fixture_status({"status":status}),"Live")
    def test_scheduled_and_final(self):
        for status in ("scheduled","not_started","FT","completed","postponed"):
            self.assertNotEqual(fixture_status({"status":status}),"Live")
    def test_missing_unknown(self):
        self.assertEqual(fixture_status({}),"Scheduled / unknown")
    def test_only_observed_live(self):
        fixtures=[{"status":"LIVE","id":1},{"status":"scheduled","id":2},{"status":"HT","id":3}]
        self.assertEqual([x["id"] for x in live_fixture_rows(fixtures)],[1,3])

if __name__=="__main__":unittest.main()
