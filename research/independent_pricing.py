"""Independent football pricing research. No market odds used for fitting.

Input CSV: date,home_team,away_team,home_goals,away_goals,home_xg,away_xg.
Chronological walk-forward evaluation; Dixon-Coles low-score adjustment.
"""
import argparse
import csv
import math
from datetime import date

def poisson(k, lam):
    return math.exp(-lam) * lam**k / math.factorial(k)

def probabilities(home_goals, away_goals, rho=-0.08, max_goals=12):
    """Dixon-Coles adjusted 1X2 probabilities, renormalized."""
    x, y = home_goals, away_goals
    p = [0., 0., 0.]
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            tau = 1.
            if i == j == 0: tau = 1 - x*y*rho
            elif i == 0 and j == 1: tau = 1 + x*rho
            elif i == 1 and j == 0: tau = 1 + y*rho
            elif i == j == 1: tau = 1 - rho
            v = max(0., tau) * poisson(i,x) * poisson(j,y)
            p[0 if i>j else 1 if i==j else 2] += v
    total = sum(p)
    return tuple(v/total for v in p)

def estimate(history, home, away, decay_days=240, prior_games=12, as_of=None):
    """Venue-sensitive shrinkage, league baseline, time decay; no future matches."""
    if not history:
        return (1.5, 1.2)
    now = as_of if as_of is not None else history[-1]["date"]
    baseline_h, baseline_a = 1.5, 1.2
    hgf=hga=agf=aga=hn=an=0.
    for m in history:
        w = math.exp(-math.log(2)*max(0,(now-m["date"]).days)/decay_days)
        if m["home_team"]==home:
            hgf+=w*m["home_xg"]; hga+=w*m["away_xg"]; hn+=w
        if m["away_team"]==away:
            agf+=w*m["away_xg"]; aga+=w*m["home_xg"]; an+=w
    hf=(hgf+prior_games*baseline_h)/(hn+prior_games)
    hd=(hga+prior_games*baseline_a)/(hn+prior_games)
    af=(agf+prior_games*baseline_a)/(an+prior_games)
    ad=(aga+prior_games*baseline_h)/(an+prior_games)
    return (max(.15, hf*ad/baseline_h), max(.15, af*hd/baseline_a))

def walk_forward(matches, minimum_train=300):
    """Pre-match estimates based strictly on earlier dated matches."""
    history=[]; results=[]; index=0
    while index<len(matches):
        day=matches[index]["date"]; today=[]
        while index<len(matches) and matches[index]["date"]==day:
            today.append(matches[index]); index+=1
        if len(history)>=minimum_train:
            for m in today:
                lh,la=estimate(history,m["home_team"],m["away_team"],as_of=day)
                p=probabilities(lh,la)
                outcome=0 if m["home_goals"]>m["away_goals"] else 1 if m["home_goals"]==m["away_goals"] else 2
                results.append((m,p,outcome,lh,la))
        history.extend(today)
    return results

def load(path):
    with open(path,newline="",encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    matches=[]
    for r in rows:
        try:
            matches.append(dict(date=date.fromisoformat(r["date"][:10]),home_team=r["home_team"],
                away_team=r["away_team"],home_goals=int(r["home_goals"]),
                away_goals=int(r["away_goals"]),home_xg=float(r["home_xg"]),away_xg=float(r["away_xg"])))
        except (KeyError,TypeError,ValueError):
            continue
    return sorted(matches,key=lambda m:m["date"])

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--minimum-train",type=int,default=300)
    args=parser.parse_args()
    rows=walk_forward(load(args.csv_path),args.minimum_train)
    if not rows:
        raise SystemExit("Not enough complete historical matches")
    logloss=sum(-math.log(max(1e-12,p[o])) for _,p,o,_,_ in rows)/len(rows)
    brier=sum(sum((v-(k==o))**2 for k,v in enumerate(p)) for _,p,o,_,_ in rows)/len(rows)
    print(f"Walk-forward: {len(rows)} matches | log loss={logloss:.4f} | multiclass Brier={brier:.4f}")
    print("These are predictive metrics, NOT betting profitability or proven calibration.")
    for label,idx in (("Home",0),("Draw",1),("Away",2)):
        predicted=sum(p[idx] for _,p,_,_,_ in rows)/len(rows)
        observed=sum(o==idx for _,_,o,_,_ in rows)/len(rows)
        print(f"{label}: predicted={predicted:.3f} observed={observed:.3f} difference={predicted-observed:+.3f}")
if __name__=="__main__":
    main()
