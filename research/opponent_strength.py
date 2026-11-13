"""Opponent-adjusted xG with chronological time decay and Bayesian shrinkage.

Fits log-linear attack and defence strengths using historical xG, with a
league-specific home advantage. This does not use bookmaker odds.
"""
import math

def fit_strengths(history, as_of, half_life_days=240, prior=12, iterations=12):
    if not history:
        return {}, {}, 1.5, 1.2
    decay=math.log(2)/half_life_days
    games=[(m,math.exp(-decay*max(0,(as_of-m["date"]).days))) for m in history if m["date"]<as_of]
    if not games:
        return {}, {}, 1.5, 1.2
    sw=sum(w for _,w in games)
    home_base=sum(w*m["home_xg"] for m,w in games)/sw
    away_base=sum(w*m["away_xg"] for m,w in games)/sw
    home_base=max(.2,home_base);away_base=max(.2,away_base)
    teams={m[k] for m,_ in games for k in ("home_team","away_team")}
    appearances={t:[] for t in teams}
    for m,w in games:
        appearances[m["home_team"]].append((m,w,True))
        appearances[m["away_team"]].append((m,w,False))
    attack={t:1. for t in teams}
    defense={t:1. for t in teams}
    # Alternating updates: team attack compared to opponent defensive rating,
    # and team defence compared to opponent attack rating.
    for _ in range(iterations):
        new_attack={}
        for t in teams:
            observed=expected=0.
            for m,w,is_home in appearances[t]:
                if is_home:
                    observed+=w*m["home_xg"]
                    expected+=w*home_base*defense[m["away_team"]]
                else:
                    observed+=w*m["away_xg"]
                    expected+=w*away_base*defense[m["home_team"]]
            new_attack[t]=max(.25,min(4.,(observed+prior)/(expected+prior)))
        attack=new_attack
        new_defense={}
        for t in teams:
            observed=expected=0.
            for m,w,is_home in appearances[t]:
                if is_home:
                    observed+=w*m["away_xg"]
                    expected+=w*away_base*attack[m["away_team"]]
                else:
                    observed+=w*m["home_xg"]
                    expected+=w*home_base*attack[m["home_team"]]
            new_defense[t]=max(.25,min(4.,(observed+prior)/(expected+prior)))
        defense=new_defense
    return attack,defense,home_base,away_base

def predict(history,home,away,as_of):
    attack,defense,h,a=fit_strengths(history,as_of)
    return (max(.15,h*attack.get(home,1.)*defense.get(away,1.)),
            max(.15,a*attack.get(away,1.)*defense.get(home,1.)))
