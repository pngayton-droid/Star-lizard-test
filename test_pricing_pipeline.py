"""Cross-engine invariants for the PRO STARLIZARD fixture pricing pipeline.

These are deterministic sanity checks, not model calibration or live API tests.
"""
import unittest
from fixture_market_pricing import price_goals
from fixture_asian_pricing import asian_market
from fixture_quote_comparison import compare_quote

class PricingPipelineTests(unittest.TestCase):
    def test_totals_consistent_across_engines(self):
        for h,a in ((.5,.8),(1.2,1.4),(2.5,1.1),(0,0)):
            goals=price_goals(h,a)
            for line,key in ((1.5,"over_1_5"),(2.5,"over_2_5")):
                asian=asian_market(h,a,"total",line,"over")
                self.assertAlmostEqual(asian["win_stake"],goals["probabilities"][key],places=9)
                self.assertAlmostEqual(asian["lose_stake"],1-goals["probabilities"][key],places=9)
                self.assertAlmostEqual(asian["push_stake"],0,places=9)
    def test_quote_at_model_fair_price(self):
        for h,a in ((.8,1.2),(1.6,1.6),(2.2,.7)):
            prices=price_goals(h,a)
            for key in ("home_win","draw","away_win","btts_yes","over_2_5"):
                p=prices["probabilities"][key]
                if key in ("home_win","draw","away_win"):
                    # Grid truncation is tiny, and quote comparator expects exhaustive settlement.
                    self.assertLess(prices["missing_mass"],1e-8)
                else:
                    result=compare_quote(prices["decimal_prices"][key],p,1-p)
                    self.assertAlmostEqual(result["expected_roi"],0,places=9)
    def test_asian_fair_quote_is_zero_ev(self):
        for market,line,side in (("total",2.25,"over"),("total",3.0,"under"),
                                 ("handicap",-.75,"home"),("handicap",.25,"away")):
            settlement=asian_market(1.5,1.1,market,line,side)
            result=compare_quote(settlement["fair_decimal"],
                                 settlement["win_stake"],settlement["lose_stake"],
                                 settlement["push_stake"])
            self.assertAlmostEqual(result["expected_roi"],0,places=9)

if __name__=="__main__":
    unittest.main()
