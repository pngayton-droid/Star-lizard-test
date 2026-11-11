"""Settlement and symmetry checks for Asian research prices."""
import unittest
from fixture_asian_pricing import asian_market

class AsianPricingTests(unittest.TestCase):
    def test_half_goal_no_push(self):
        r=asian_market(1.4,1.1,"total",2.5,"over")
        self.assertAlmostEqual(r["push_stake"],0,places=8)
        self.assertAlmostEqual(r["win_stake"]+r["lose_stake"],1,places=8)
    def test_integer_goal_push(self):
        r=asian_market(1.0,1.0,"total",2.0,"over")
        self.assertGreater(r["push_stake"],0)
        self.assertAlmostEqual(r["win_stake"]+r["lose_stake"]+r["push_stake"],1,places=8)
    def test_quarter_split(self):
        a=asian_market(1.2,1.3,"total",2.25,"over")
        b=asian_market(1.2,1.3,"total",2.0,"over")
        c=asian_market(1.2,1.3,"total",2.5,"over")
        for key in ("win_stake","lose_stake","push_stake"):
            self.assertAlmostEqual(a[key],(b[key]+c[key])/2,places=8)
    def test_handicap_opposites(self):
        home=asian_market(1.5,1.0,"handicap",-0.25,"home")
        away=asian_market(1.5,1.0,"handicap",0.25,"away")
        self.assertAlmostEqual(home["win_stake"],away["lose_stake"],places=8)
        self.assertAlmostEqual(home["lose_stake"],away["win_stake"],places=8)
    def test_reject_invalid(self):
        for kwargs in [
            dict(market="total",line=2.3,side="over"),
            dict(market="handicap",line=0,side="over"),
            dict(market="total",line=2.5,side="home")]:
            with self.assertRaises(ValueError):
                asian_market(1,1,**kwargs)

if __name__=="__main__":unittest.main()
