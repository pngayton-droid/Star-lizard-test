"""Halftime snapshot research pricing with chronological evaluation.

The historical segment is a descriptive conditional frequency, not a
calibrated fixture-specific fair probability. No next-goal ordering is inferred.
"""
from math import sqrt

OUTCOMES={
    "Second half: at least 1 goal":lambda r: int(r["home_second_half_goals"])+int(r["away_second_half_goals"])>=1,
    "Second half: at least 2 goals":lambda r: int(r["home_second_half_goals"])+int(r["away_second_half_goals"])>=2,
    "Second half: at least 3 goals":lambda r: int(r["home_second_half_goals"])+int(r["away_second_half_goals"])>=3,
    "Home scores in second half":lambda r: int(r["home_second_half_goals"])>=1,
    "Away scores in second half":lambda r: int(r["away_second_half_goals"])>=1,
    "Home wins second half":lambda r: int(r["home_second_half_goals"])>int(r["away_second_half_goals"]),
    "Away wins second half":lambda r: int(r["away_second_half_goals"])>int(r["home_second_half_goals"]),
    "Second half draw":lambda r: int(r["home_second_half_goals"])==int(r["away_second_half_goals"]),
    "Both teams score in second half":lambda r: int(r["home_second_half_goals"])>0 and int(r["away_second_half_goals"])>0,
    "Home wins full time":lambda r: int(r["home_goals"])>int(r["away_goals"]),
    "Draw full time":lambda r: int(r["home_goals"])==int(r["away_goals"]),
    "Away wins full time":lambda r: int(r["away_goals"])>int(r["home_goals"]),
}

def snapshot_research(rows,home_ht,away_ht,home_xg,away_xg,outcome,
                      xg_tolerance=0.4,min_train=80,min_later=30):
    if outcome not in OUTCOMES:raise ValueError("Unknown outcome")
    if min(home_ht,away_ht,home_xg,away_xg)<0:raise ValueError("Negative score or xG")
    if xg_tolerance<=0:raise ValueError("xG tolerance must be positive")
    # Use all matches for chronology, never randomly split correlated fixtures.
    ordered=sorted(rows,key=lambda r:str(r["match_date"]))
    dates=sorted({str(r["match_date"]) for r in ordered})
    if len(dates)<3:return {"status":"Insufficient distinct historical dates"}
    cut=dates[max(1,min(len(dates)-1,int(len(dates)*0.7)))]
    def qualifying(r):
        return (int(r["home_ht_goals"])==home_ht and
                int(r["away_ht_goals"])==away_ht and
                abs(float(r["home_ht_xg"])-home_xg)<=xg_tolerance and
                abs(float(r["away_ht_xg"])-away_xg)<=xg_tolerance)
    early=[r for r in ordered if str(r["match_date"])<cut and qualifying(r)]
    later=[r for r in ordered if str(r["match_date"])>=cut and qualifying(r)]
    if len(early)<min_train or len(later)<min_later:
        return {"status":"Insufficient matching historical observations",
                "train_n":len(early),"later_n":len(later),"cutoff":cut}
    f=OUTCOMES[outcome]
    hits=sum(bool(f(r)) for r in early)
    later_hits=sum(bool(f(r)) for r in later)
    p=hits/len(early)
    # Wilson descriptive 95% interval for training segment.
    n=len(early);z=1.959963984540054
    denom=1+z*z/n
    centre=(p+z*z/(2*n))/denom
    half=z*sqrt(p*(1-p)/n+z*z/(4*n*n))/denom
    return {"status":"Research estimate available","train_n":n,"train_hits":hits,
            "train_rate":p,"lower":max(0,centre-half),"upper":min(1,centre+half),
            "later_n":len(later),"later_hits":later_hits,
            "later_rate":later_hits/len(later),"cutoff":cut}

def quote_break_even(decimal_odds,commission_pct=0):
    if not 1<decimal_odds<=1000:raise ValueError("Invalid decimal odds")
    if not 0<=commission_pct<=30:raise ValueError("Invalid commission")
    return 1/(1+(decimal_odds-1)*(1-commission_pct/100))
