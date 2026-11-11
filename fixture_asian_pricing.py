"""Asian totals and handicap settlement probabilities from goal intensities.

Each market returns the probability of winning/losing each *unit of stake*
and the expected returned stake at decimal odds. Quarter lines split the
stake equally between adjacent half/integer lines. Research baseline only.
"""
from math import exp, factorial, isfinite

def _validate(mu):
    v=float(mu)
    if not isfinite(v) or not 0<=v<=8:
        raise ValueError("Goal intensity must be finite, between zero and eight")
    return v

def _legs(line):
    line=float(line)
    if not isfinite(line) or line*4!=round(line*4):
        raise ValueError("Asian line must be in quarter-goal increments")
    quarter=int(round(line*4))
    if quarter%2:
        return ((quarter-1)/4,(quarter+1)/4)
    return (line,)

def _distribution(home_mu,away_mu,cap=40):
    h,a=_validate(home_mu),_validate(away_mu)
    hp=[exp(-h)*h**i/factorial(i) for i in range(cap+1)]
    ap=[exp(-a)*a**i/factorial(i) for i in range(cap+1)]
    return ((i,j,pi*pj) for i,pi in enumerate(hp) for j,pj in enumerate(ap))

def asian_market(home_mu,away_mu,market,line,side):
    """Price a selected Asian line using expected stake settlement.

    market: 'total' (over/under) or 'handicap' (home/away).
    line: total goal threshold or handicap added to chosen team's goals.
    Return fair decimal odds = 1 + losing_stake_fraction / winning_stake_fraction.
    Pushes refund stakes; no commission or market calibration.
    """
    if market not in ("total","handicap"):
        raise ValueError("market must be total or handicap")
    if (market=="total" and side not in ("over","under")) or (
            market=="handicap" and side not in ("home","away")):
        raise ValueError("Invalid market side")
    legs=_legs(line)
    win=loss=push=0.0
    for h,a,p in _distribution(home_mu,away_mu):
        if p==0:continue
        for leg in legs:
            if market=="total":
                result=h+a-leg
                if side=="under":result=-result
            else:
                result=(h-a if side=="home" else a-h)+leg
            fraction=p/len(legs)
            if result>0:win+=fraction
            elif result<0:loss+=fraction
            else:push+=fraction
    mass=win+loss+push
    # A negligible Poisson grid tail is left explicit, never treated as a push.
    return {"market":market,"side":side,"line":float(line),
            "win_stake":win,"lose_stake":loss,"push_stake":push,
            "missing_mass":max(0.0,1-mass),
            "fair_decimal":1+loss/win if win>0 else None}
