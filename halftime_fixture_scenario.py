"""Transparent independent-Poisson second-half scenario engine.

Uses user-supplied PRE-MATCH expected full-time goals as an optional prior.
Halftime xG influences the second-half rate only via an explicitly heuristic
adjustment. This is not fitted, calibrated, or a claim of market value.
"""
from math import exp,factorial

def poisson_pmf(mu,k):
    return exp(-mu)*mu**k/factorial(k)

def second_half_scenario(home_pre,away_pre,home_ht_xg,away_ht_xg,
                         home_ht_goals,away_ht_goals,remaining_share=0.50,
                         adjustment=0.0):
    if any(v<0 for v in [home_pre,away_pre,home_ht_xg,away_ht_xg,home_ht_goals,away_ht_goals]):
        raise ValueError("Negative input")
    if not 0<remaining_share<1 or not 0<=adjustment<=1:
        raise ValueError("Invalid second-half share or adjustment")
    if max(home_pre,away_pre)>8:raise ValueError("Expected goals outside supported range")
    # The pre-match expected full-time goals are the anchor. Optional adjustment
    # blends each team's share of the total attacking intensity towards HT xG share.
    total=home_pre+away_pre
    base_home=home_pre*remaining_share
    base_away=away_pre*remaining_share
    observed=home_ht_xg+away_ht_xg
    if observed>0 and total>0:
        share=home_ht_xg/observed
        home_mu=(1-adjustment)*base_home+adjustment*total*remaining_share*share
        away_mu=(1-adjustment)*base_away+adjustment*total*remaining_share*(1-share)
    else:
        home_mu,away_mu=base_home,base_away
    # Tail mass is retained by summing 0..30 goals each side.
    home=[poisson_pmf(home_mu,k) for k in range(31)]
    away=[poisson_pmf(away_mu,k) for k in range(31)]
    outcomes={"Home wins FT":0.0,"Draw FT":0.0,"Away wins FT":0.0,
              "Home wins 2H":0.0,"Draw 2H":0.0,"Away wins 2H":0.0,
              "Home scores 2H":1-home[0],"Away scores 2H":1-away[0],
              "Both score 2H":(1-home[0])*(1-away[0])}
    for h,hp in enumerate(home):
        for a,ap in enumerate(away):
            p=hp*ap
            ft_h=home_ht_goals+h;ft_a=away_ht_goals+a
            outcomes["Home wins FT" if ft_h>ft_a else "Away wins FT" if ft_h<ft_a else "Draw FT"]+=p
            outcomes["Home wins 2H" if h>a else "Away wins 2H" if h<a else "Draw 2H"]+=p
    total_mu=home_mu+away_mu
    # In an independent homogeneous Poisson race, the first scorer is
    # proportional to each team's intensity, conditional on a goal.
    # These are model-implied probabilities, NOT verified event-sequence rates.
    no_goal=exp(-total_mu)
    any_goal=1-no_goal
    outcomes["No second-half goal"]=no_goal
    outcomes["Home scores first in 2H (model)"]=any_goal*home_mu/total_mu if total_mu else 0.0
    outcomes["Away scores first in 2H (model)"]=any_goal*away_mu/total_mu if total_mu else 0.0
    for n in [1,2,3]:
        outcomes[f"2H at least {n} goals"]=1-sum(poisson_pmf(total_mu,k) for k in range(n))
    return {"home_2h_mu":home_mu,"away_2h_mu":away_mu,"probabilities":outcomes}
