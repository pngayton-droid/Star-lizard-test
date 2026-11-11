"""Regression checks for quote comparison with stake settlement."""
import unittest
from fixture_quote_comparison import compare_quote

class QuoteComparisonTests(unittest.TestCase):
    def test_even_money_fair(self):
        result=compare_quote(2.0,.5,.5)
        self.assertAlmostEqual(result["expected_roi"],0)
        self.assertAlmostEqual(result["break_even_decimal"],2)
    def test_commission(self):
        result=compare_quote(2.0,.5,.5,commission=.05)
        self.assertAlmostEqual(result["expected_roi"],-.025)
        self.assertAlmostEqual(result["break_even_decimal"],1+1/.95)
    def test_asian_push(self):
        result=compare_quote(2.0,.4,.4,.2)
        self.assertAlmostEqual(result["expected_roi"],0)
        self.assertAlmostEqual(result["break_even_decimal"],2)
    def test_half_win_and_loss(self):
        result=compare_quote(2.5,.25,.5,.25)
        self.assertAlmostEqual(result["expected_roi"],-.125)
    def test_reject_bad_inputs(self):
        for args in [(1,.5,.5,0,0),(2,.7,.7,0,0),(2,.5,.5,0,1),
                     (float("nan"),.5,.5,0,0)]:
            with self.assertRaises(ValueError):compare_quote(*args)

if __name__=="__main__":unittest.main()
