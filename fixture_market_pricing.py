"""Reusable independent-Poisson pre-match market pricing.

Research baseline only: no Dixon-Coles adjustment, market calibration or bookmaker odds.
"""
from math import exp, factorial, isfinite

def _poisson(mu, cap):
    values=[exp(-mu)*mu**i/factorial(i) for i in range(cap+1)]
    return values

def price_goals(home_mu, away_mu, cap=18):
    """Return fair decimal research prices and probabilities.

    The final grid tail is not renormalised: report its missing mass explicitly.
    Totals and BTTS are computed analytically so they are not truncated.
    """
    home_mu=float(home_mu)
    away_mu=float(away_mu)
    if not all(isfinite(v) and 0<=v<=8 for v in (home_mu,away_mu)):
        raise ValueError("Goal intensities must be finite and between zero and eight")
    if not isinstance(cap,int) or cap<12 or cap>40:
        raise ValueError("cap must be an integer from 12 to 40")
    hp,ap=_poisson(home_mu,cap),_poisson(away_mu,cap)
    home=draw=away=0.0
    scores=[]
    for h,ph in enumerate(hp):
        for a,pa in enumerate(ap):
            p=ph*pa
            if h>a:home+=p
            elif h<a:away+=p
            else:draw+=p
            scores.append((h,a,p))
    total=home_mu+away_mu
    under15=exp(-total)*(1+total)
    under25=exp(-total)*(1+total+total**2/2)
    probs={"home_win":home,"draw":draw,"away_win":away,
           "over_1_5":1-under15,"under_1_5":under15,
           "over_2_5":1-under25,"under_2_5":under25,
           "btts_yes":(1-exp(-home_mu))*(1-exp(-away_mu)),
           "btts_no":1-(1-exp(-home_mu))*(1-exp(-away_mu))}
    top=sorted(scores,key=lambda row:row[2],reverse=True)[:8]
    return {"probabilities":probs,
            "decimal_prices":{k:(1/v if v>0 else None) for k,v in probs.items()},
            "top_scores":[{"score":f"{h}-{a}","probability":p,
                           "decimal_price":1/p if p>0 else None} for h,a,p in top],
            "grid_mass":home+draw+away,"missing_mass":max(0.0,1-home-draw-away)}
